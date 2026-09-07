"""Unit tests for spa/security.py's require_firebase_login. Mocks
verify_firebase_token instead of minting real Firebase JWTs -- what's
under test is the allowlist/verification wiring, not google-auth's own
signature checking."""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from aliexpress_dashboard.config import Settings
from aliexpress_dashboard.spa import security


def _request(token: str | None) -> Request:
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    scope = {"type": "http", "headers": headers}
    return Request(scope)


def _settings(**overrides) -> Settings:
    defaults = dict(
        mode="fixture",
        firebase_project_id="test-project",
        dashboard_allowed_emails="allowed@example.com",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_fails_closed_when_firebase_project_id_unset():
    with pytest.raises(HTTPException) as exc_info:
        security.require_firebase_login(_request("some-token"), _settings(firebase_project_id=None))
    assert exc_info.value.status_code == 503


def test_missing_bearer_token_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        security.require_firebase_login(_request(None), _settings())
    assert exc_info.value.status_code == 401


def test_invalid_token_is_rejected(monkeypatch):
    def _raise(*args, **kwargs):
        raise ValueError("Token expired")

    monkeypatch.setattr(security.google_id_token, "verify_firebase_token", _raise)
    with pytest.raises(HTTPException) as exc_info:
        security.require_firebase_login(_request("bad-token"), _settings())
    assert exc_info.value.status_code == 401


def test_unverified_email_is_rejected(monkeypatch):
    monkeypatch.setattr(
        security.google_id_token,
        "verify_firebase_token",
        lambda *a, **k: {"email": "allowed@example.com", "email_verified": False},
    )
    with pytest.raises(HTTPException) as exc_info:
        security.require_firebase_login(_request("token"), _settings())
    assert exc_info.value.status_code == 403


def test_verified_but_not_allowlisted_is_rejected(monkeypatch):
    monkeypatch.setattr(
        security.google_id_token,
        "verify_firebase_token",
        lambda *a, **k: {"email": "stranger@example.com", "email_verified": True},
    )
    with pytest.raises(HTTPException) as exc_info:
        security.require_firebase_login(_request("token"), _settings())
    assert exc_info.value.status_code == 403


def test_verified_and_allowlisted_returns_email(monkeypatch):
    monkeypatch.setattr(
        security.google_id_token,
        "verify_firebase_token",
        lambda *a, **k: {"email": "allowed@example.com", "email_verified": True},
    )
    assert security.require_firebase_login(_request("token"), _settings()) == "allowed@example.com"
