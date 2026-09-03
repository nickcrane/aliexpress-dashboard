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
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from aliexpress_api.errors.exceptions import ApiRequestException, ApiRequestResponseException

from ..client.ali_client import AliClient
from ..client.errors import TokenMissingError
from ..collector import store
from ..collector.runner import run_collection
from ..config import Settings, get_settings
from ..dashboard.momentum import compute_momentum, load_observations_for_momentum
from ..dashboard.queries import (
    ProductFilters,
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
        "currencies": distinct_target_currencies(conn),
        "ship_to_countries": distinct_ship_to_countries(conn),
    }


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
