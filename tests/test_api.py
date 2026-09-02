import pytest
from fastapi.testclient import TestClient

from aliexpress_dashboard.api.app import app
from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.config import Settings, get_settings

API_KEY = "test-api-key"


def _settings(tmp_path, *, api_key=API_KEY) -> Settings:
    return Settings(mode="fixture", token_path=tmp_path / "token.json", api_key=api_key)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client_with_settings(settings: Settings) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_requires_no_api_key(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_route_without_key_configured_fails_closed(tmp_path):
    client = _client_with_settings(_settings(tmp_path, api_key=None))
    response = client.post("/refresh-token")
    assert response.status_code == 503


def test_protected_route_without_header_is_rejected(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    response = client.post("/refresh-token")
    assert response.status_code == 401


def test_protected_route_with_wrong_key_is_rejected(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    response = client.post("/refresh-token", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


def test_refresh_token_with_no_token_on_file_returns_409(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    response = client.post("/refresh-token", headers={"X-API-Key": API_KEY})
    assert response.status_code == 409


def test_refresh_token_success(tmp_path):
    settings = _settings(tmp_path)
    # Seed a token on disk the way the CLI's authorize step would.
    AliClient(settings).exchange_code_for_token("fixture-code")

    client = _client_with_settings(settings)
    response = client.post("/refresh-token", headers={"X-API-Key": API_KEY})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["expires_in"] == 86400
    assert body["refresh_expires_in"] == 172800
    assert "obtained_at" in body


def test_root_requires_api_key(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"X-API-Key": API_KEY}).status_code == 200
