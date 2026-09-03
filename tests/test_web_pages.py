import pytest
from fastapi.testclient import TestClient

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.collector.runner import run_collection
from aliexpress_dashboard.config import Settings
from aliexpress_dashboard.dashboard import shortlists
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations
from aliexpress_dashboard.web.app import app, get_settings, require_login

SEEDED_PRODUCT_ID = 1005006109529182
SEEDED_PRODUCT_TITLE = "Mini USB Rechargeable LED Reading Light Clip-On Book Lamp"


@pytest.fixture
def seeded_db_path(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    run_migrations(conn)
    store.upsert_search(conn, name="home-gadgets-under-15-gbp")
    saved = store.get_search_by_name(conn, "home-gadgets-under-15-gbp")
    ali_client = AliClient(Settings(mode="fixture"))
    # Two runs, so Momentum has something to show.
    run_collection(conn, ali_client, mode="fixture", searches=[saved])
    run_collection(conn, ali_client, mode="fixture", searches=[saved])

    shortlist_id = shortlists.get_or_create_shortlist(conn, "test-shortlist")
    shortlists.add_products_to_shortlist(conn, shortlist_id, [SEEDED_PRODUCT_ID])
    conn.commit()
    return db_path


@pytest.fixture
def client(seeded_db_path, live_api_base_url, monkeypatch):
    # live_api_base_url (tests/conftest.py) runs the real api/app.py, which
    # resolves its own Settings() fresh per request from these env vars --
    # they need to match what the web app's Settings override below sends.
    monkeypatch.setenv("AE_MODE", "fixture")
    monkeypatch.setenv("AE_DB_PATH", str(seeded_db_path))
    monkeypatch.setenv("AE_API_KEY", "test-web-api-key")

    def _settings() -> Settings:
        return Settings(
            mode="fixture",
            db_path=seeded_db_path,
            api_base_url=live_api_base_url,
            api_key="test-web-api-key",
        )

    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[require_login] = lambda: "test@example.com"
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_products_page_shows_seeded_products(client):
    response = client.get("/")
    assert response.status_code == 200
    assert SEEDED_PRODUCT_TITLE in response.text
    assert "test@example.com" in response.text


def test_products_page_tolerates_blank_filter_form_fields(client):
    # An unset <select>/<input> in the filter form submits "", not an
    # omitted param -- confirmed live this crashed with a 422 before
    # category_id/min_price/etc. were parsed manually instead of relying
    # on FastAPI's automatic Optional[int]/Optional[float] coercion.
    response = client.get(
        "/",
        params={
            "category_id": "",
            "min_price": "",
            "max_price": "",
            "price_currency": "",
            "min_rating": "",
            "min_volume": "",
            "ship_to_country": "",
        },
    )
    assert response.status_code == 200
    assert SEEDED_PRODUCT_TITLE in response.text


def test_products_page_price_band_without_currency_shows_error_not_500(client):
    response = client.get("/", params={"min_price": 1})
    assert response.status_code == 200
    assert "price_currency is required" in response.text


def test_momentum_page_renders_with_history(client):
    response = client.get("/momentum")
    assert response.status_code == 200
    assert SEEDED_PRODUCT_TITLE in response.text


def test_shortlists_page_shows_seeded_shortlist(client):
    response = client.get("/shortlists")
    assert response.status_code == 200
    assert "test-shortlist" in response.text
    assert SEEDED_PRODUCT_TITLE in response.text


def test_save_shortlist_round_trips_through_the_real_api(client):
    response = client.post(
        "/shortlists",
        data={"name": "web-created-shortlist", "product_ids": [str(SEEDED_PRODUCT_ID)]},
        follow_redirects=False,
    )
    assert response.status_code == 303

    follow_up = client.get("/shortlists")
    assert "web-created-shortlist" in follow_up.text


def test_unauthenticated_page_does_not_leak_product_data():
    app.dependency_overrides.clear()
    client = TestClient(app, follow_redirects=False)
    response = client.get("/")
    assert SEEDED_PRODUCT_TITLE not in response.text
