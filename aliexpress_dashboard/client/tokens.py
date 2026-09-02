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
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import TokenSet


def load_token(path: Path) -> Optional[TokenSet]:
    if not path.exists():
        return None
    return TokenSet(**json.loads(path.read_text()))


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
