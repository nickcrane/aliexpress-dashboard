"""Mobile-first Bootstrap web app -- a pure HTTP client of
aliexpress_dashboard/api/, via dashboard/api_client.py.

Auth is real Google OAuth via Authlib plus Starlette's signed-cookie
SessionMiddleware for session state. Authorization (the email allowlist)
is shared via ../authz.py.

Run locally:

    uvicorn aliexpress_dashboard.web.app:app --reload --port 8502
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional

import numpy as np
import pandas as pd
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ..authz import is_authorized
from ..config import Settings, get_settings
from ..dashboard.api_client import ApiClient
from ..dashboard.queries import ProductFilters
from ..dashboard.scoring import ScoreWeights, compute_composite_score

settings = get_settings()

app = FastAPI(title="AliExpress Dashboard (Web)")
app.add_middleware(SessionMiddleware, secret_key=settings.web_session_secret or "dev-only-insecure-secret")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


class NotAuthenticated(Exception):
    pass


class NotAuthorized(Exception):
    def __init__(self, email: Optional[str]) -> None:
        self.email = email


@app.exception_handler(NotAuthenticated)
async def _handle_not_authenticated(request: Request, exc: NotAuthenticated) -> RedirectResponse:
    return RedirectResponse(url="/login")


@app.exception_handler(NotAuthorized)
async def _handle_not_authorized(request: Request, exc: NotAuthorized) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "unauthorized.html", {"email": exc.email}, status_code=403
    )


def require_login(request: Request, settings: Settings = Depends(get_settings)) -> str:
    email = request.session.get("email")
    if not email:
        raise NotAuthenticated()
    if not is_authorized(email, settings.dashboard_allowed_emails):
        raise NotAuthorized(email)
    return email


def get_api_client(settings: Settings = Depends(get_settings)) -> Iterator[ApiClient]:
    client = ApiClient(base_url=settings.api_base_url, api_key=settings.api_key)
    try:
        yield client
    finally:
        client.close()


def _records(df: pd.DataFrame) -> list:
    """DataFrame -> template-safe records. NaN is truthy in Python, so an
    unconverted NaN would make `{% if product.field %}` checks in templates
    misbehave -- same reasoning as api/app.py's identical helper."""
    return df.replace({np.nan: None}).to_dict(orient="records")


# ---------------------------------------------------------------- auth ----


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if request.session.get("email"):
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/login/google")
async def login_google(request: Request):
    return await oauth.google.authorize_redirect(request, settings.web_redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request, settings: Settings = Depends(get_settings)):
    token = await oauth.google.authorize_access_token(request)
    email = (token.get("userinfo") or {}).get("email")
    if not is_authorized(email, settings.dashboard_allowed_emails):
        return templates.TemplateResponse(request, "unauthorized.html", {"email": email}, status_code=403)
    request.session["email"] = email
    return RedirectResponse(url="/")


@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login")


# ------------------------------------------------------------- products ---


@app.get("/", response_class=HTMLResponse)
def products_page(
    request: Request,
    email: str = Depends(require_login),
    client: ApiClient = Depends(get_api_client),
    category_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    price_currency: Optional[str] = None,
    min_rating: Optional[float] = None,
    min_volume: Optional[int] = None,
    ship_to_country: Optional[str] = None,
    weight_volume: float = 25.0,
    weight_rating: float = 25.0,
    weight_review_count: float = 25.0,
    weight_price_fit: float = 25.0,
) -> HTMLResponse:
    error = None
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
        error = str(exc)
        filters = ProductFilters()

    df = client.load_current_products(filters)
    weights = ScoreWeights(
        volume=weight_volume, rating=weight_rating, review_count=weight_review_count, price_fit=weight_price_fit
    )
    if not df.empty:
        df = df.assign(score=compute_composite_score(df, weights))
    filter_options = client.get_filters()
    price_ceiling = client.max_target_price(price_currency) if price_currency else None

    return templates.TemplateResponse(
        request,
        "products.html",
        {
            "email": email,
            "active_page": "products",
            "products": _records(df),
            "filter_options": filter_options,
            "filters": filters,
            "weights": weights,
            "price_ceiling": price_ceiling,
            "error": error,
        },
    )


# ------------------------------------------------------------- momentum ---


@app.get("/momentum", response_class=HTMLResponse)
def momentum_page(
    request: Request,
    email: str = Depends(require_login),
    client: ApiClient = Depends(get_api_client),
    window_days: int = 14,
) -> HTMLResponse:
    products = client.load_current_products(ProductFilters())
    product_ids = products["product_id"].tolist() if not products.empty else []
    momentum = client.get_momentum(product_ids, window_days=window_days)

    if not momentum.empty and not products.empty:
        momentum = momentum.merge(
            products[["product_id", "product_title", "product_main_image_url", "product_url"]],
            on="product_id",
            how="left",
        )

    return templates.TemplateResponse(
        request,
        "momentum.html",
        {
            "email": email,
            "active_page": "momentum",
            "momentum": _records(momentum),
            "window_days": window_days,
        },
    )


# ----------------------------------------------------------- shortlists ---


@app.get("/shortlists", response_class=HTMLResponse)
def shortlists_page(
    request: Request,
    email: str = Depends(require_login),
    client: ApiClient = Depends(get_api_client),
    shortlist_id: Optional[int] = None,
) -> HTMLResponse:
    shortlists = client.list_shortlists()
    selected_id = shortlist_id or (shortlists[0].id if shortlists else None)
    products = _records(client.load_shortlist_products(selected_id)) if selected_id else []

    return templates.TemplateResponse(
        request,
        "shortlists.html",
        {
            "email": email,
            "active_page": "shortlists",
            "shortlists": shortlists,
            "selected_id": selected_id,
            "products": products,
        },
    )


@app.post("/shortlists")
def save_shortlist_route(
    email: str = Depends(require_login),
    client: ApiClient = Depends(get_api_client),
    name: str = Form(...),
    product_ids: List[int] = Form(default=[]),
) -> RedirectResponse:
    client.save_shortlist(name, product_ids)
    return RedirectResponse(url="/", status_code=303)


@app.post("/shortlists/{shortlist_id}/remove/{product_id}")
def remove_shortlist_product_route(
    shortlist_id: int,
    product_id: int,
    email: str = Depends(require_login),
    client: ApiClient = Depends(get_api_client),
) -> RedirectResponse:
    client.remove_product_from_shortlist(shortlist_id, product_id)
    return RedirectResponse(url=f"/shortlists?shortlist_id={shortlist_id}", status_code=303)


@app.post("/shortlists/{shortlist_id}/delete")
def delete_shortlist_route(
    shortlist_id: int,
    email: str = Depends(require_login),
    client: ApiClient = Depends(get_api_client),
) -> RedirectResponse:
    client.delete_shortlist(shortlist_id)
    return RedirectResponse(url="/shortlists", status_code=303)
