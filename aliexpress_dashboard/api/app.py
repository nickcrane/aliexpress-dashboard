"""HTTP API for triggering aliexpress_dashboard tasks remotely -- built so
multiple OpenClaw (or any other) assistants can call into one shared,
stable surface instead of each needing shell/file-system access to this
project. Starts with just the token refresh task; more endpoints (run a
saved search, list shortlists, etc.) are expected to follow the same
pattern: a route, an X-API-Key-gated dependency, and a typed JSON response.

Run locally:

    uvicorn aliexpress_dashboard.api.app:app --reload --port 8000

Every route except /health requires the X-API-Key header, checked in
security.py against AE_API_KEY -- see that module for why this fails closed
rather than open when the key isn't configured.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aliexpress_api.errors.exceptions import ApiRequestException, ApiRequestResponseException

from ..client.ali_client import AliClient
from ..client.errors import TokenMissingError
from ..collector import store
from ..collector.runner import run_collection, sync_categories
from ..config import Settings, get_settings
from ..dashboard import llm_usage
from ..dashboard.business_profiles import (
    BusinessProfile,
    create_business_profile,
    delete_business_profile,
    get_active_business_profile,
    get_business_profile_by_id,
    list_business_profiles,
    set_active_business_profile,
    update_business_profile,
)
from ..dashboard.momentum import compute_momentum, load_observations_for_momentum
from ..dashboard.queries import (
    ProductFilters,
    category_market_stats,
    category_tree,
    category_tree_coverage,
    distinct_categories,
    distinct_ship_to_countries,
    distinct_target_currencies,
    load_current_products,
    load_price_history,
    max_target_price,
)
from ..dashboard.shortlists import (
    add_products_to_shortlist,
    delete_shortlist,
    get_or_create_shortlist,
    list_shortlists,
    load_shortlist_products,
    remove_product_from_shortlist,
)
from .dependencies import get_db_connection
from .security import require_api_key

app = FastAPI(title="AliExpress Dashboard API", version="0.1.0")

_cors_origins = [origin.strip() for origin in get_settings().cors_allowed_origins.split(",") if origin.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _records(df: pd.DataFrame) -> list:
    """DataFrame -> JSON-safe records; NaN isn't valid JSON."""
    return df.replace({np.nan: None}).to_dict(orient="records")


def _parse_ids(product_ids: str) -> List[int]:
    return [int(pid) for pid in product_ids.split(",") if pid]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", dependencies=[Depends(require_api_key)])
def root() -> dict:
    return {"service": "aliexpress-dashboard-api", "status": "ok"}


@app.post("/refresh-token", dependencies=[Depends(require_api_key)])
def refresh_token(settings: Settings = Depends(get_settings)) -> dict:
    client = AliClient(settings)
    try:
        token = client.refresh_access_token()
    except TokenMissingError as exc:
        # No refresh token on file at all -- refreshing can't fix this, a
        # human needs to run the interactive authorize flow again.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ApiRequestException, ApiRequestResponseException) as exc:
        raise HTTPException(status_code=502, detail=f"AliExpress API error: {exc}") from exc

    return {
        "status": "ok",
        "expires_in": token.expires_in,
        "refresh_expires_in": token.refresh_expires_in,
        "obtained_at": token.obtained_at,
    }


@app.post("/collect", dependencies=[Depends(require_api_key)])
def collect(
    search: Optional[str] = None,
    settings: Settings = Depends(get_settings),
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    if search:
        saved = store.get_search_by_name(conn, search)
        if saved is None:
            raise HTTPException(status_code=404, detail=f"No saved search named {search!r}")
        searches = [saved]
    else:
        searches = store.load_active_searches(conn)
        if not searches:
            return {"run_id": None, "searches_executed": 0, "records_written": 0, "errors": []}

    client = AliClient(settings)
    summary = run_collection(conn, client, mode=settings.mode, searches=searches)
    return {
        "run_id": summary.run_id,
        "searches_executed": summary.searches_executed,
        "records_written": summary.records_written,
        "errors": summary.errors,
    }


@app.post("/sync-categories", dependencies=[Depends(require_api_key)])
def sync_categories_route(
    settings: Settings = Depends(get_settings),
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    client = AliClient(settings)
    count = sync_categories(conn, client)
    return {"status": "ok", "categories_synced": count}


@app.get("/products", dependencies=[Depends(require_api_key)])
def products(
    category_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    price_currency: Optional[str] = None,
    min_rating: Optional[float] = None,
    min_volume: Optional[int] = None,
    ship_to_country: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> list:
    try:
        filters = ProductFilters(
            category_id=category_id,
            min_price=min_price,
            max_price=max_price,
            price_currency=price_currency,
            min_rating=min_rating,
            min_volume=min_volume,
            ship_to_country=ship_to_country,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _records(load_current_products(conn, filters))


@app.get("/products/price-history", dependencies=[Depends(require_api_key)])
def products_price_history(
    product_ids: str = Query(...),
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    return load_price_history(conn, _parse_ids(product_ids))


@app.get("/filters", dependencies=[Depends(require_api_key)])
def filters(conn: sqlite3.Connection = Depends(get_db_connection)) -> dict:
    return {
        "categories": distinct_categories(conn),
        # {parent -> children} for a cascading category filter -- see
        # dashboard/queries.py:category_tree. "categories" above stays as
        # the flat list for the legacy Bootstrap app's single dropdown.
        "category_tree": category_tree(conn),
        # How many of the fully-synced categories table's parents actually
        # show up above, vs. the total -- see category_tree_coverage.
        "category_tree_coverage": category_tree_coverage(conn),
        "currencies": distinct_target_currencies(conn),
        "ship_to_countries": distinct_ship_to_countries(conn),
    }


@app.get("/categories/{category_id}/market-stats", dependencies=[Depends(require_api_key)])
def category_market_stats_route(
    category_id: int,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    return category_market_stats(conn, category_id)


@app.get("/filters/max-price", dependencies=[Depends(require_api_key)])
def filters_max_price(
    currency: str = Query(...),
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    return {"max_price": max_target_price(conn, currency)}


@app.get("/momentum", dependencies=[Depends(require_api_key)])
def momentum(
    product_ids: str = Query(...),
    window_days: int = 14,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> list:
    observations = load_observations_for_momentum(conn, _parse_ids(product_ids))
    return _records(compute_momentum(observations, window_days=window_days))


@app.get("/shortlists", dependencies=[Depends(require_api_key)])
def shortlists(conn: sqlite3.Connection = Depends(get_db_connection)) -> list:
    return [
        {"id": s.id, "name": s.name, "created_at": s.created_at, "item_count": s.item_count}
        for s in list_shortlists(conn)
    ]


@app.get("/shortlists/{shortlist_id}/products", dependencies=[Depends(require_api_key)])
def shortlist_products(
    shortlist_id: int,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> list:
    return _records(load_shortlist_products(conn, shortlist_id))


class SaveShortlistRequest(BaseModel):
    name: str
    product_ids: List[int]


@app.post("/shortlists", dependencies=[Depends(require_api_key)])
def save_shortlist(
    body: SaveShortlistRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    shortlist_id = get_or_create_shortlist(conn, body.name)
    add_products_to_shortlist(conn, shortlist_id, body.product_ids)
    return {"id": shortlist_id, "name": body.name}


@app.delete("/shortlists/{shortlist_id}", dependencies=[Depends(require_api_key)])
def delete_shortlist_route(
    shortlist_id: int,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    delete_shortlist(conn, shortlist_id)
    return {"status": "ok"}


@app.delete("/shortlists/{shortlist_id}/products/{product_id}", dependencies=[Depends(require_api_key)])
def remove_shortlist_product_route(
    shortlist_id: int,
    product_id: int,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    remove_product_from_shortlist(conn, shortlist_id, product_id)
    return {"status": "ok"}


# ------------------------------------------------- onboarding / LLM ---
# This service owns all persistent data (including this new state), same
# as everything above -- the Firebase-auth-gated caller lives in
# spa/app.py, which verifies the user and calls the routes below with
# their real email attached server-side. See dashboard/business_profiles.py
# and dashboard/llm_usage.py.


@app.get("/business-profile", dependencies=[Depends(require_api_key)])
def get_active_business_profile_route(
    user_email: str = Query(...),
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    """The one version currently driving Products page defaults -- see
    list/business-profiles below for every saved version."""
    profile = get_active_business_profile(conn, user_email)
    if profile is None:
        raise HTTPException(status_code=404, detail="No active business profile for this user yet")
    return asdict(profile)


@app.get("/business-profiles", dependencies=[Depends(require_api_key)])
def list_business_profiles_route(
    user_email: str = Query(...),
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> list:
    return [asdict(p) for p in list_business_profiles(conn, user_email)]


class CreateBusinessProfileRequest(BaseModel):
    user_email: str
    seller_type: Optional[str] = None
    product_niche: Optional[str] = None
    target_market: Optional[str] = None
    sales_channels: List[str] = []
    marketing_approach: List[str] = []
    budget_stage: Optional[str] = None
    experience_level: Optional[str] = None
    primary_category_id: Optional[int] = None
    summary: Optional[str] = None
    market_gap_analysis: Optional[str] = None
    status: str = "in_progress"
    make_active: bool = True


@app.post("/business-profiles", dependencies=[Depends(require_api_key)])
def create_business_profile_route(
    body: CreateBusinessProfileRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    """Always a new version -- never overwrites an existing row (unlike
    the old single-profile-per-user PUT this replaced)."""
    fields = body.model_dump(exclude={"make_active"})
    profile = BusinessProfile(**fields)
    profile_id = create_business_profile(conn, profile, make_active=body.make_active)
    return asdict(get_business_profile_by_id(conn, profile_id))


class UpdateBusinessProfileRequest(BaseModel):
    user_email: str  # ownership check -- must match the profile being edited
    seller_type: Optional[str] = None
    product_niche: Optional[str] = None
    target_market: Optional[str] = None
    sales_channels: List[str] = []
    marketing_approach: List[str] = []
    budget_stage: Optional[str] = None
    experience_level: Optional[str] = None
    primary_category_id: Optional[int] = None
    summary: Optional[str] = None
    market_gap_analysis: Optional[str] = None
    status: str = "in_progress"


def _require_owned_profile(conn: sqlite3.Connection, profile_id: int, user_email: str) -> BusinessProfile:
    """404s (not 403) on a mismatch -- doesn't confirm to a caller whether
    a profile id belonging to someone else even exists."""
    existing = get_business_profile_by_id(conn, profile_id)
    if existing is None or existing.user_email != user_email:
        raise HTTPException(status_code=404, detail="No business profile with this id for this user")
    return existing


@app.put("/business-profiles/{profile_id}", dependencies=[Depends(require_api_key)])
def update_business_profile_route(
    profile_id: int,
    body: UpdateBusinessProfileRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    """Edits this specific version in place -- doesn't change which
    version is active."""
    _require_owned_profile(conn, profile_id, body.user_email)
    profile = BusinessProfile(**body.model_dump())
    update_business_profile(conn, profile_id, profile)
    return asdict(get_business_profile_by_id(conn, profile_id))


class ActivateBusinessProfileRequest(BaseModel):
    user_email: str


@app.post("/business-profiles/{profile_id}/activate", dependencies=[Depends(require_api_key)])
def activate_business_profile_route(
    profile_id: int,
    body: ActivateBusinessProfileRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    _require_owned_profile(conn, profile_id, body.user_email)
    set_active_business_profile(conn, profile_id)
    return asdict(get_business_profile_by_id(conn, profile_id))


@app.delete("/business-profiles/{profile_id}", dependencies=[Depends(require_api_key)])
def delete_business_profile_route(
    profile_id: int,
    user_email: str = Query(...),
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    _require_owned_profile(conn, profile_id, user_email)
    delete_business_profile(conn, profile_id)
    return {"status": "ok"}


@app.get("/llm-usage/current-month", dependencies=[Depends(require_api_key)])
def llm_usage_current_month_route(conn: sqlite3.Connection = Depends(get_db_connection)) -> dict:
    return {"cost_usd": llm_usage.current_month_cost_usd(conn)}


class RecordUsageRequest(BaseModel):
    input_tokens: int
    output_tokens: int


@app.post("/llm-usage/record", dependencies=[Depends(require_api_key)])
def llm_usage_record_route(
    body: RecordUsageRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),
) -> dict:
    cost = llm_usage.record_usage(conn, input_tokens=body.input_tokens, output_tokens=body.output_tokens)
    return {"cost_usd": cost}
