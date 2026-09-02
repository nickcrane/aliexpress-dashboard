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

from fastapi import Depends, FastAPI, HTTPException

from aliexpress_api.errors.exceptions import ApiRequestException, ApiRequestResponseException

from ..client.ali_client import AliClient
from ..client.errors import TokenMissingError
from ..config import Settings, get_settings
from .security import require_api_key

app = FastAPI(title="AliExpress Dashboard API", version="0.1.0")


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
