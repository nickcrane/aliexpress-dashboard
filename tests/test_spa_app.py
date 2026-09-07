"""Tests for spa/app.py: the /api/* proxy (auth enforced, then forwarded
to a real API server with the key attached) and the static SPA fallback."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.collector.runner import run_collection
from aliexpress_dashboard.config import Settings, get_settings
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations
from aliexpress_dashboard.spa import app as spa_app_module
from aliexpress_dashboard.spa.app import app
from aliexpress_dashboard.spa.security import require_firebase_login

API_KEY = "test-spa-key"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    run_migrations(conn)
    store.upsert_search(conn, name="home-gadgets-under-15-gbp")
    saved = store.get_search_by_name(conn, "home-gadgets-under-15-gbp")
    client = AliClient(Settings(mode="fixture"))
    run_collection(conn, client, mode="fixture", searches=[saved])
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(live_api_base_url, seeded_db, monkeypatch):
    monkeypatch.setenv("AE_MODE", "fixture")
    monkeypatch.setenv("AE_DB_PATH", str(seeded_db))
    monkeypatch.setenv("AE_API_KEY", API_KEY)
    settings = Settings(
        mode="fixture",
        db_path=seeded_db,
        api_key=API_KEY,
        api_base_url=live_api_base_url,
        firebase_project_id="test-project",
        dashboard_allowed_emails="allowed@example.com",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_needs_no_auth(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_proxy_without_login_is_rejected(client):
    response = client.get("/api/filters")
    assert response.status_code == 401


def test_proxy_forwards_to_real_backend_once_logged_in(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    response = client.get("/api/filters")
    assert response.status_code == 200
    assert "categories" in response.json()


def test_proxy_forwards_query_params_and_status(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    # No currency param -> the real API 422s; confirms errors pass through too.
    response = client.get("/api/filters/max-price")
    assert response.status_code == 422


def test_spa_fallback_reports_missing_build_when_dist_absent(client, tmp_path, monkeypatch):
    monkeypatch.setattr(spa_app_module, "DIST_DIR", tmp_path / "nonexistent-dist")
    response = client.get("/momentum")
    assert response.status_code == 503
    assert "npm run build" in response.text


def test_spa_fallback_serves_index_html_for_router_paths(client, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>the app shell</html>")
    monkeypatch.setattr(spa_app_module, "DIST_DIR", dist)

    response = client.get("/momentum")
    assert response.status_code == 200
    assert "the app shell" in response.text


def test_spa_fallback_serves_real_files_directly(client, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>the app shell</html>")
    (dist / "vite.svg").write_text("<svg>icon</svg>")
    monkeypatch.setattr(spa_app_module, "DIST_DIR", dist)

    response = client.get("/vite.svg")
    assert response.status_code == 200
    assert "icon" in response.text
