"""Google login gate for the dashboard, via Streamlit's native OIDC support
(st.login/st.logout/st.user, Streamlit >=1.42) -- not a third-party proxy.

Login proves *who* you are; it doesn't by itself decide whether that person
should see this dashboard (any Google account could sign in). Pair it with
an email allowlist, checked after login succeeds.
"""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from ..config import PROJECT_ROOT, Settings

logger = logging.getLogger(__name__)

SECRETS_PATH = PROJECT_ROOT / ".streamlit" / "secrets.toml"


def ensure_secrets_file(settings: Settings, path: Path = SECRETS_PATH) -> None:
    """Writes `path` (Streamlit's [auth] config) from env vars, but only if
    it doesn't already exist -- same bootstrap pattern as
    client/tokens.py:seed_token_from_env, for the same reason: Railway has
    no way to hand Streamlit a secrets file directly, so this generates one
    from env vars at container startup. Locally, hand-create the file
    instead and this becomes a no-op.
    """
    if path.exists():
        return
    if not (settings.google_client_id and settings.google_client_secret and settings.auth_cookie_secret):
        logger.warning(
            "AE_GOOGLE_CLIENT_ID/AE_GOOGLE_CLIENT_SECRET/AE_AUTH_COOKIE_SECRET not all set; "
            "skipping %s bootstrap",
            path,
        )
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[auth]\n"
        f'redirect_uri = "{settings.auth_redirect_uri}"\n'
        f'cookie_secret = "{settings.auth_cookie_secret}"\n'
        f'client_id = "{settings.google_client_id}"\n'
        f'client_secret = "{settings.google_client_secret}"\n'
        'server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"\n'
    )
    logger.info("Seeded %s from AE_GOOGLE_* / AE_AUTH_* env vars", path)


def _is_authorized(email: str | None, allowed_emails: str) -> bool:
    if not email:
        return False
    allowed = {e.strip().lower() for e in allowed_emails.split(",") if e.strip()}
    return email.strip().lower() in allowed


def require_login(settings: Settings) -> None:
    """Gates the whole dashboard. Call first thing in main(), before
    building the ApiClient or rendering anything else. Stops script
    execution (st.stop()) whenever the viewer isn't logged in and
    authorized, so nothing past this point ever renders for them."""
    if not (settings.google_client_id and settings.google_client_secret and settings.auth_cookie_secret):
        # st.user.is_logged_in raises AttributeError (not just False) when
        # [auth] isn't configured in secrets.toml at all -- confirmed live.
        # Fail with a clear setup message instead of an unhandled crash.
        st.title("AliExpress Product Research")
        st.error(
            "Login isn't configured yet -- set AE_GOOGLE_CLIENT_ID, "
            "AE_GOOGLE_CLIENT_SECRET, and AE_AUTH_COOKIE_SECRET (see README)."
        )
        st.stop()

    if not st.user.is_logged_in:
        st.title("AliExpress Product Research")
        st.write("Sign in to continue.")
        if st.button("Log in with Google"):
            st.login()
        st.stop()

    if not _is_authorized(st.user.email, settings.dashboard_allowed_emails):
        st.title("AliExpress Product Research")
        st.error(f"{st.user.email} isn't authorized to view this dashboard.")
        if st.button("Log out"):
            st.logout()
        st.stop()

    st.sidebar.caption(f"Signed in as {st.user.email}")
    if st.sidebar.button("Log out"):
        st.logout()
