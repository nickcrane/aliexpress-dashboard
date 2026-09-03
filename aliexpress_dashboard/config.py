from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True)
class RateLimitConfig:
    min_request_interval_seconds: float = field(
        default_factory=lambda: _float_env("AE_MIN_REQUEST_INTERVAL_SECONDS", 1.0)
    )
    max_retries: int = field(default_factory=lambda: _int_env("AE_MAX_RETRIES", 5))
    backoff_base_seconds: float = field(
        default_factory=lambda: _float_env("AE_BACKOFF_BASE_SECONDS", 1.0)
    )
    backoff_max_seconds: float = field(
        default_factory=lambda: _float_env("AE_BACKOFF_MAX_SECONDS", 60.0)
    )


@dataclass(frozen=True)
class Settings:
    mode: str = field(default_factory=lambda: os.getenv("AE_MODE", "fixture"))
    app_key: str | None = field(default_factory=lambda: os.getenv("AE_APP_KEY") or None)
    app_secret: str | None = field(default_factory=lambda: os.getenv("AE_APP_SECRET") or None)
    # Where the one-time OAuth authorize step redirects to. Must be HTTPS.
    # Defaults to a neutral real domain you don't need to run anything on --
    # the authorization `code` shows up in the browser's address bar after
    # the redirect regardless of what page actually loads there. See README.
    callback_url: str = field(default_factory=lambda: os.getenv("AE_CALLBACK_URL", "https://example.com/callback"))
    target_currency: str = field(default_factory=lambda: os.getenv("AE_TARGET_CURRENCY", "GBP"))
    # aliexpress.ds.* endpoints call this `local` -- confirmed live that it
    # needs a full locale like "en_US", not a bare language code ("en" fails
    # the call outright, contradicting the docs' "en" example value).
    target_language: str = field(default_factory=lambda: os.getenv("AE_TARGET_LANGUAGE", "en_US"))
    # Destination/ship-to country, required by aliexpress.ds.text.search's countryCode param.
    ship_to_country: str = field(default_factory=lambda: os.getenv("AE_SHIP_TO_COUNTRY", "GB"))
    db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("AE_DB_PATH", str(PROJECT_ROOT / "data" / "aliexpress_dashboard.db"))
        )
    )
    fixtures_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("AE_FIXTURES_DIR", str(PROJECT_ROOT / "tests" / "fixtures"))
        )
    )
    # Where the OAuth access/refresh token is cached locally after the
    # one-time authorize step. Not .env -- this file is written
    # programmatically, .env is hand-edited. Gitignored.
    token_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("AE_TOKEN_PATH", str(PROJECT_ROOT / "data" / "token.json"))
        )
    )
    # One-time bootstrap for a fresh deployment with no token file yet (e.g.
    # a new Railway volume) -- the exact JSON contents of a local token.json,
    # obtained via the interactive `authorize` step somewhere with a
    # browser. Only ever used to create token_path if it doesn't already
    # exist; never overwrites it. See client/tokens.py:seed_token_from_env.
    token_seed: str | None = field(default_factory=lambda: os.getenv("AE_TOKEN_SEED") or None)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    # Shared secret the HTTP API (aliexpress_dashboard/api/) requires on every
    # request via the X-API-Key header. Unset means the API refuses all
    # requests (fail closed) rather than running open -- see api/security.py.
    api_key: str | None = field(default_factory=lambda: os.getenv("AE_API_KEY") or None)
    # Where the dashboard finds the HTTP API it reads/writes through instead
    # of touching AE_DB_PATH directly -- see dashboard/api_client.py. Not
    # consumed by the API service itself or the collector CLI.
    api_base_url: str = field(default_factory=lambda: os.getenv("AE_API_BASE_URL", "http://localhost:8000"))
    # Google OAuth client for the dashboard's login gate -- see
    # dashboard/auth.py. Only consumed by the dashboard.
    google_client_id: str | None = field(default_factory=lambda: os.getenv("AE_GOOGLE_CLIENT_ID") or None)
    google_client_secret: str | None = field(default_factory=lambda: os.getenv("AE_GOOGLE_CLIENT_SECRET") or None)
    # Signs the dashboard's session cookie. Must stay fixed across restarts
    # -- generate once the same way as AE_API_KEY (secrets.token_urlsafe(32)).
    auth_cookie_secret: str | None = field(default_factory=lambda: os.getenv("AE_AUTH_COOKIE_SECRET") or None)
    auth_redirect_uri: str = field(
        default_factory=lambda: os.getenv("AE_AUTH_REDIRECT_URI", "http://localhost:8501/oauth2callback")
    )
    # Comma-separated allowlist -- login proves *who* you are, this decides
    # whether that person is actually allowed to see the dashboard.
    dashboard_allowed_emails: str = field(
        default_factory=lambda: os.getenv("AE_DASHBOARD_ALLOWED_EMAILS", "nic.crane@gmail.com")
    )
    # Signs the Bootstrap web app's session cookie (web/app.py) -- a
    # separate secret from auth_cookie_secret since it's a different cookie
    # mechanism (Starlette SessionMiddleware vs. Streamlit's own auth).
    # Generate the same way as AE_API_KEY.
    web_session_secret: str | None = field(default_factory=lambda: os.getenv("AE_WEB_SESSION_SECRET") or None)
    # Reuses the same Google OAuth client as auth_redirect_uri, just a
    # different callback path -- both need registering in Google Cloud
    # Console. Different local port than Streamlit's 8501 so both can run
    # side by side during the transition.
    web_redirect_uri: str = field(
        default_factory=lambda: os.getenv("AE_WEB_REDIRECT_URI", "http://localhost:8502/auth/callback")
    )

    def __post_init__(self) -> None:
        if self.mode not in ("fixture", "live"):
            raise ValueError(f"AE_MODE must be 'fixture' or 'live', got {self.mode!r}")
        if self.mode == "live" and not (self.app_key and self.app_secret):
            raise ValueError("AE_APP_KEY and AE_APP_SECRET are required when AE_MODE=live")


def get_settings() -> Settings:
    return Settings()
