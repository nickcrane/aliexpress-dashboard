import pytest
from fastapi.testclient import TestClient

from aliexpress_dashboard.web.app import NotAuthorized, app, require_login


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_unauthenticated_request_redirects_to_login():
    client = TestClient(app, follow_redirects=False)
    response = client.get("/")
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/login"


def test_login_page_renders_without_a_session():
    client = TestClient(app)
    response = client.get("/login")
    assert response.status_code == 200
    assert "Log in with Google" in response.text


def _raise_not_authorized():
    raise NotAuthorized("blocked@example.com")


def test_unauthorized_session_shows_unauthorized_page():
    app.dependency_overrides[require_login] = _raise_not_authorized
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 403
    assert "blocked@example.com" in response.text
