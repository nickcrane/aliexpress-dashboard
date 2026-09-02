"""API key check for the HTTP API.

Fails closed: if AE_API_KEY isn't configured, every request is rejected
rather than the API running wide open. This service will eventually sit
behind a public Railway URL in front of real AliExpress credentials, so an
unset key should never silently mean "no auth required."
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Depends, Header, HTTPException

from ..config import Settings, get_settings


def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="API key not configured on the server (AE_API_KEY unset)")

    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")
