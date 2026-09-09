"""Serves the M3 SPA (web-m3/dist, built separately -- see Dockerfile.spa)
and proxies its API calls server-side, so the AliExpress API key never
reaches the browser -- unlike hitting aliexpress_dashboard/api/ directly
with a build-time-baked VITE_API_KEY, which is fine for a local test build
but not for a real deployment (see web-m3/README.md).

Every /api/* request must carry a Firebase ID token that decodes to an
allowlisted email (require_firebase_login, security.py); the underlying
AliExpress API key is attached here, server-side, from AE_API_KEY.

Run locally (after `npm run build` in web-m3):

    uvicorn aliexpress_dashboard.spa.app:app --reload --port 8503
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Dict, Optional

import anthropic
import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..client.llm_client import synthesize_business_plan
from ..config import Settings, get_settings
from .security import require_firebase_login

app = FastAPI(title="AliExpress Dashboard (M3 SPA)")

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "web-m3" / "dist"

if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


async def get_backend_client(settings: Settings = Depends(get_settings)) -> AsyncIterator[httpx.AsyncClient]:
    client = httpx.AsyncClient(
        base_url=settings.api_base_url,
        headers={"X-API-Key": settings.api_key} if settings.api_key else {},
    )
    try:
        yield client
    finally:
        await client.aclose()


async def _proxy_json(upstream: httpx.Response) -> Response:
    return Response(content=upstream.content, status_code=upstream.status_code, media_type="application/json")


# Registered ahead of the generic catch-all proxy below (FastAPI matches
# routes in registration order) because these two need the caller's
# *verified* email attached server-side -- the generic proxy forwards
# whatever the client's own request body/query says verbatim, which is
# fine for AliExpress data (nothing user-scoped) but would let a client
# read or overwrite another user's business_profiles row just by naming
# their email if these went through it instead.


@app.get("/api/business-profile")
async def get_active_business_profile_proxy(
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
) -> Response:
    """The one version currently driving Products page defaults."""
    upstream = await backend.get("/business-profile", params={"user_email": email})
    return await _proxy_json(upstream)


@app.get("/api/business-profiles")
async def list_business_profiles_proxy(
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
) -> Response:
    """Every saved version, for the plan-history / switch-version UI."""
    upstream = await backend.get("/business-profiles", params={"user_email": email})
    return await _proxy_json(upstream)


@app.post("/api/business-profiles")
async def create_business_profile_proxy(
    request: Request,
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
) -> Response:
    """Always a new version -- never overwrites an existing one."""
    body = await request.json()
    body["user_email"] = email  # never trust the client's own claim
    upstream = await backend.post("/business-profiles", json=body)
    return await _proxy_json(upstream)


@app.put("/api/business-profiles/{profile_id}")
async def update_business_profile_proxy(
    profile_id: int,
    request: Request,
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
) -> Response:
    """Edits this specific version in place."""
    body = await request.json()
    body["user_email"] = email
    upstream = await backend.put(f"/business-profiles/{profile_id}", json=body)
    return await _proxy_json(upstream)


@app.post("/api/business-profiles/{profile_id}/activate")
async def activate_business_profile_proxy(
    profile_id: int,
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
) -> Response:
    upstream = await backend.post(f"/business-profiles/{profile_id}/activate", json={"user_email": email})
    return await _proxy_json(upstream)


@app.delete("/api/business-profiles/{profile_id}")
async def delete_business_profile_proxy(
    profile_id: int,
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
) -> Response:
    upstream = await backend.delete(f"/business-profiles/{profile_id}", params={"user_email": email})
    return await _proxy_json(upstream)


class OnboardingRequest(BaseModel):
    answers: Dict[str, str]
    # Picked directly by the user from the real category_tree (Material
    # Web chips in the wizard) -- not something the LLM is asked to
    # infer. Confirmed live that asking it to match free-text
    # product_niche against category names frequently returned null even
    # for a clear case, silently breaking Products page defaults.
    primary_category_id: Optional[int] = None
    # Editing an existing version in place vs. creating a new one -- see
    # onboarding_synthesize below.
    profile_id: Optional[int] = None


@app.post("/api/onboarding/synthesize")
async def onboarding_synthesize(
    body: OnboardingRequest,
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not settings.anthropic_api_key:
        return JSONResponse(
            status_code=503, content={"detail": "Business plan assistant not configured (AE_ANTHROPIC_API_KEY unset)"}
        )

    usage_resp = await backend.get("/llm-usage/current-month")
    if usage_resp.status_code != 200:
        return JSONResponse(status_code=502, content={"detail": "Could not check this month's usage cap"})
    if usage_resp.json()["cost_usd"] >= settings.llm_monthly_cap_usd:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The business plan assistant has hit this month's spending cap -- try again next month."
            },
        )

    try:
        plan = await synthesize_business_plan(api_key=settings.anthropic_api_key, wizard_answers=body.answers)
    except anthropic.RateLimitError as exc:
        return JSONResponse(status_code=429, content={"detail": f"Business plan assistant is busy: {exc}"})
    except anthropic.APIStatusError as exc:
        return JSONResponse(status_code=502, content={"detail": f"Business plan assistant error: {exc}"})
    except anthropic.APIConnectionError as exc:
        return JSONResponse(status_code=502, content={"detail": f"Business plan assistant unreachable: {exc}"})

    await backend.post(
        "/llm-usage/record", json={"input_tokens": plan.input_tokens, "output_tokens": plan.output_tokens}
    )

    profile_fields = {
        "user_email": email,
        "seller_type": plan.seller_type,
        "product_niche": plan.product_niche,
        "target_market": plan.target_market,
        "sales_channels": plan.sales_channels,
        "marketing_approach": plan.marketing_approach,
        "budget_stage": plan.budget_stage,
        "primary_category_id": body.primary_category_id,
        "summary": plan.summary,
        "status": "complete",
    }
    if body.profile_id is not None:
        # Editing an existing version in place -- doesn't change which
        # version is active.
        save_resp = await backend.put(f"/business-profiles/{body.profile_id}", json=profile_fields)
    else:
        # A fresh submission or an explicit "create new version" --
        # becomes the active plan driving Products page defaults.
        save_resp = await backend.post("/business-profiles", json={**profile_fields, "make_active": True})
    return await _proxy_json(save_resp)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "DELETE"])
async def proxy(
    path: str,
    request: Request,
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
) -> Response:
    body = await request.body()
    # Confirmed live: without forwarding Content-Type, the backend
    # receives a bodyless-looking POST and 422s trying to parse it --
    # this was silently broken for every JSON-bodied route proxied here
    # (e.g. POST /shortlists) until a test on the new onboarding routes
    # happened to exercise a POST body through this path for the first time.
    content_type = request.headers.get("content-type")
    try:
        upstream = await backend.request(
            request.method,
            f"/{path}",
            params=request.query_params,
            content=body or None,
            headers={"content-type": content_type} if content_type else None,
        )
    except httpx.TransportError as exc:
        return JSONResponse(status_code=502, content={"detail": f"Backend API unreachable: {exc}"})

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/{full_path:path}")
def spa(full_path: str) -> Response:
    if not DIST_DIR.is_dir():
        return HTMLResponse(
            "<p>web-m3 hasn't been built yet -- run <code>npm run build</code> in web-m3/ "
            "(see Dockerfile.spa for how the production image does this).</p>",
            status_code=503,
        )
    candidate = DIST_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(DIST_DIR / "index.html")
