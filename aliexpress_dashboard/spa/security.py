"""Firebase login check for the M3 SPA's API proxy (app.py).

Verifies the ID token Firebase's client SDK issues after a successful
Google/Facebook/email sign-in -- via google-auth against Google's public
certs, not the heavier firebase-admin SDK, so no service-account
credentials are needed server-side. Login only proves *who* signed in;
is_authorized (shared with the Bootstrap web app, ../authz.py) then
decides whether that person is actually allowed to see the dashboard.

Fails closed: if AE_FIREBASE_PROJECT_ID isn't configured, every request
is rejected rather than the proxy accepting tokens from any Firebase
project -- same reasoning as api/security.py's AE_API_KEY check.
"""

from __future__ import annotations

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from fastapi import Depends, HTTPException, Request

from ..authz import is_authorized
from ..config import Settings, get_settings

# Reused across requests so google-auth can cache Google's public certs
# instead of re-fetching them on every login check.
_google_request = google_requests.Request()


def require_firebase_login(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    if not settings.firebase_project_id:
        raise HTTPException(
            status_code=503, detail="Firebase project not configured on the server (AE_FIREBASE_PROJECT_ID unset)"
        )

    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header[len("bearer ") :].strip()

    try:
        claims = google_id_token.verify_firebase_token(token, _google_request, audience=settings.firebase_project_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = claims.get("email")
    # Google/Facebook sign-in always yields a verified email; email/password
    # sign-up doesn't until Firebase's verification link is clicked -- an
    # unverified email can't be trusted to actually belong to the signer-upper.
    if not claims.get("email_verified"):
        raise HTTPException(status_code=403, detail="Verify your email address before continuing")
    if not is_authorized(email, settings.dashboard_allowed_emails):
        raise HTTPException(status_code=403, detail=f"{email} is not authorized for this dashboard")

    return email
