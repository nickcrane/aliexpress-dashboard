"""Local storage for the OAuth access/refresh token.

AliExpress's authorization-strategy docs implied a self-developed app's
token is valid ~365 days (refresh ~730) -- confirmed against a real account
that this is wrong (or doesn't apply the way the docs suggest): the actual
access token lasts 24 hours, refresh token 48. So this needs refreshing
roughly daily, well within the docs, not once a year. Stored as a small
JSON file rather than in .env, since it's written programmatically (by the
authorize/refresh flow) rather than hand-edited.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import TokenSet

logger = logging.getLogger(__name__)


def load_token(path: Path) -> Optional[TokenSet]:
    if not path.exists():
        return None
    return TokenSet(**json.loads(path.read_text()))


def seed_token_from_env(path: Path, seed_json: Optional[str]) -> None:
    """Writes `seed_json` to `path`, but only if `path` doesn't already
    exist -- for bootstrapping a fresh deployment (e.g. a new Railway
    volume) with a token obtained locally via the interactive `authorize`
    step, which can't run on a host with no browser.

    Never overwrites an existing file. Once the token has been refreshed on
    disk even once, that copy is newer than whatever the seed captured at
    deploy time -- clobbering it on every restart would undo real refreshes
    and eventually leave the deployment holding an expired token.

    Malformed seed JSON is logged and skipped, not raised -- a bad env var
    shouldn't crash the whole app on startup.
    """
    if path.exists() or not seed_json:
        return
    try:
        TokenSet(**json.loads(seed_json))  # validate shape before writing
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("AE_TOKEN_SEED is not valid token JSON, ignoring: %s", exc)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(seed_json)
    logger.info("Seeded %s from AE_TOKEN_SEED", path)


def save_token(path: Path, token: TokenSet) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(token), indent=2))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_access_token_expired(token: TokenSet, *, safety_margin_seconds: int = 1800) -> bool:
    """True if the access token is expired, or expiring within safety_margin_seconds."""
    if token.expires_in is None:
        return False  # unknown validity -- assume still good rather than force a refresh loop
    obtained_at = datetime.fromisoformat(token.obtained_at)
    age_seconds = (datetime.now(timezone.utc) - obtained_at).total_seconds()
    return age_seconds >= (token.expires_in - safety_margin_seconds)


def is_refresh_token_expired(token: TokenSet) -> bool:
    if token.refresh_expires_in is None or not token.refresh_token:
        return True
    obtained_at = datetime.fromisoformat(token.obtained_at)
    age_seconds = (datetime.now(timezone.utc) - obtained_at).total_seconds()
    return age_seconds >= token.refresh_expires_in
