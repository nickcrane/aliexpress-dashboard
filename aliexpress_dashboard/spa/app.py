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
from typing import AsyncIterator

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


@app.api_route("/api/{path:path}", methods=["GET", "POST", "DELETE"])
async def proxy(
    path: str,
    request: Request,
    email: str = Depends(require_firebase_login),
    backend: httpx.AsyncClient = Depends(get_backend_client),
) -> Response:
    body = await request.body()
    try:
        upstream = await backend.request(
            request.method,
            f"/{path}",
            params=request.query_params,
            content=body or None,
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
