from aliexpress_dashboard.config import Settings
from aliexpress_dashboard.dashboard.auth import _is_authorized, ensure_secrets_file


def _settings(**overrides) -> Settings:
    defaults = dict(
        mode="fixture",
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
        auth_cookie_secret="test-cookie-secret",
        auth_redirect_uri="http://localhost:8501/oauth2callback",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_ensure_secrets_file_writes_file_when_missing(tmp_path):
    path = tmp_path / "secrets.toml"
    ensure_secrets_file(_settings(), path)

    content = path.read_text()
    assert "[auth]" in content
    assert 'client_id = "test-client-id"' in content
    assert 'client_secret = "test-client-secret"' in content
    assert 'cookie_secret = "test-cookie-secret"' in content
    assert 'redirect_uri = "http://localhost:8501/oauth2callback"' in content
    assert "accounts.google.com/.well-known/openid-configuration" in content


def test_ensure_secrets_file_never_overwrites_an_existing_file(tmp_path):
    path = tmp_path / "secrets.toml"
    path.write_text("existing content")

    ensure_secrets_file(_settings(), path)

    assert path.read_text() == "existing content"


def test_ensure_secrets_file_skips_when_credentials_missing(tmp_path):
    path = tmp_path / "secrets.toml"
    ensure_secrets_file(_settings(google_client_id=None), path)
    assert not path.exists()


def test_is_authorized_matches_allowed_email():
    assert _is_authorized("nic.crane@gmail.com", "nic.crane@gmail.com")


def test_is_authorized_is_case_insensitive():
    assert _is_authorized("Nic.Crane@Gmail.com", "nic.crane@gmail.com")


def test_is_authorized_rejects_email_not_on_list():
    assert not _is_authorized("someone-else@gmail.com", "nic.crane@gmail.com")


def test_is_authorized_supports_multiple_allowed_emails():
    allowed = "nic.crane@gmail.com, teammate@example.com"
    assert _is_authorized("teammate@example.com", allowed)


def test_is_authorized_rejects_when_email_is_none():
    assert not _is_authorized(None, "nic.crane@gmail.com")


def test_is_authorized_rejects_when_allowlist_is_empty():
    assert not _is_authorized("nic.crane@gmail.com", "")
