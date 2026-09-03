"""Email-allowlist authorization, shared by anything that gates access
behind a login -- currently just the Bootstrap web app (web/app.py).
Login proves *who* you are; this decides whether that person is actually
allowed in.
"""

from __future__ import annotations


def is_authorized(email: str | None, allowed_emails: str) -> bool:
    if not email:
        return False
    allowed = {e.strip().lower() for e in allowed_emails.split(",") if e.strip()}
    return email.strip().lower() in allowed
