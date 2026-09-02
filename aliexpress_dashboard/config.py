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

    def __post_init__(self) -> None:
        if self.mode not in ("fixture", "live"):
            raise ValueError(f"AE_MODE must be 'fixture' or 'live', got {self.mode!r}")
        if self.mode == "live" and not (self.app_key and self.app_secret):
            raise ValueError("AE_APP_KEY and AE_APP_SECRET are required when AE_MODE=live")


def get_settings() -> Settings:
    return Settings()
