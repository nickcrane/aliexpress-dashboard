import pytest
from fastapi.testclient import TestClient

from aliexpress_dashboard.api.app import app
from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.client.models import NormalizedProduct
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.config import Settings, get_settings
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations

API_KEY = "test-api-key"


def _settings(tmp_path, *, api_key=API_KEY) -> Settings:
    return Settings(
        mode="fixture", token_path=tmp_path / "token.json", db_path=tmp_path / "test.db", api_key=api_key
    )


def _seed_product(tmp_path, **overrides) -> None:
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    defaults = dict(
        product_id=1,
        product_title="Widget",
        sale_price=9.99,
        sale_price_currency="GBP",
        target_sale_price=9.99,
        target_sale_price_currency="GBP",
        evaluate_rate=90.0,
        sales_volume=100,
    )
    defaults.update(overrides)
    run_id = store.create_run(conn, mode="fixture")
    store.upsert_product_and_observation(
        conn, NormalizedProduct(**defaults), run_id=run_id, search_id=None, captured_at="2026-01-01T00:00:00+00:00"
    )
    conn.commit()
    conn.close()


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


def _auth(client: TestClient, method: str, path: str, **kwargs):
    return getattr(client, method)(path, headers={"X-API-Key": API_KEY}, **kwargs)


def test_collect_with_no_active_searches_returns_zero_summary(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "post", "/collect")
    assert response.status_code == 200
    assert response.json() == {"run_id": None, "searches_executed": 0, "records_written": 0, "errors": []}


def test_collect_with_unknown_named_search_returns_404(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "post", "/collect", params={"search": "does-not-exist"})
    assert response.status_code == 404


def test_collect_runs_active_searches(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    store.upsert_search(conn, name="home-gadgets-under-15-gbp")
    conn.close()

    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "post", "/collect")
    assert response.status_code == 200
    body = response.json()
    assert body["searches_executed"] == 1
    assert body["records_written"] > 0


def test_products_returns_seeded_product(tmp_path):
    _seed_product(tmp_path)
    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "get", "/products")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["product_id"] == 1
    assert body[0]["product_title"] == "Widget"


def test_products_price_band_requires_currency(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "get", "/products", params={"min_price": 1})
    assert response.status_code == 422


def test_products_price_history(tmp_path):
    _seed_product(tmp_path)
    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "get", "/products/price-history", params={"product_ids": "1"})
    assert response.status_code == 200
    # One observation isn't enough history to draw a sparkline (min_points=2).
    assert response.json() == {}


def test_filters_reflects_seeded_data(tmp_path):
    _seed_product(tmp_path)
    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "get", "/filters")
    assert response.status_code == 200
    assert response.json()["currencies"] == ["GBP"]


def test_filters_max_price(tmp_path):
    _seed_product(tmp_path)
    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "get", "/filters/max-price", params={"currency": "GBP"})
    assert response.status_code == 200
    assert response.json() == {"max_price": 9.99}


def test_momentum_with_no_observations(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    response = _auth(client, "get", "/momentum", params={"product_ids": "1"})
    assert response.status_code == 200
    assert response.json() == []


def test_shortlist_round_trip(tmp_path):
    _seed_product(tmp_path)
    client = _client_with_settings(_settings(tmp_path))

    create = _auth(client, "post", "/shortlists", json={"name": "Q1 candidates", "product_ids": [1]})
    assert create.status_code == 200
    shortlist_id = create.json()["id"]

    listed = _auth(client, "get", "/shortlists").json()
    assert listed == [{"id": shortlist_id, "name": "Q1 candidates", "created_at": listed[0]["created_at"], "item_count": 1}]

    products = _auth(client, "get", f"/shortlists/{shortlist_id}/products").json()
    assert [p["product_id"] for p in products] == [1]

    remove = _auth(client, "delete", f"/shortlists/{shortlist_id}/products/1")
    assert remove.status_code == 200
    assert _auth(client, "get", f"/shortlists/{shortlist_id}/products").json() == []

    delete = _auth(client, "delete", f"/shortlists/{shortlist_id}")
    assert delete.status_code == 200
    assert _auth(client, "get", "/shortlists").json() == []


def test_data_routes_require_api_key(tmp_path):
    client = _client_with_settings(_settings(tmp_path))
    assert client.get("/products").status_code == 401
    assert client.get("/filters").status_code == 401
    assert client.post("/collect").status_code == 401
