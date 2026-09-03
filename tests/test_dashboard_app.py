import pytest
from streamlit.testing.v1 import AppTest

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.collector.runner import run_collection
from aliexpress_dashboard.config import PROJECT_ROOT, Settings
from aliexpress_dashboard.dashboard import auth, shortlists
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations

LAUNCHER = str(PROJECT_ROOT / "run_dashboard.py")


@pytest.fixture(autouse=True)
def _bypass_login_gate(monkeypatch):
    # These tests are about dashboard functionality, not the login gate
    # itself (that's tests/test_dashboard_auth.py, and needs no real Google
    # OAuth round trip to verify).
    monkeypatch.setattr(auth, "ensure_secrets_file", lambda settings: None)
    monkeypatch.setattr(auth, "require_login", lambda settings: None)


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch, live_api_base_url):
    # The dashboard now reads/writes through the HTTP API (live_api_base_url,
    # from conftest.py) instead of touching AE_DB_PATH directly -- but both
    # sides resolve Settings() from the same env vars, so pointing the API
    # server's AE_DB_PATH here and the dashboard's AE_API_BASE_URL at it is
    # enough to keep them talking about the same database.
    monkeypatch.setenv("AE_MODE", "fixture")
    monkeypatch.setenv("AE_DB_PATH", str(tmp_path / "dashboard-test.db"))
    monkeypatch.setenv("AE_API_KEY", "test-dashboard-api-key")
    monkeypatch.setenv("AE_API_BASE_URL", live_api_base_url)
    monkeypatch.delenv("AE_APP_KEY", raising=False)
    monkeypatch.delenv("AE_APP_SECRET", raising=False)
    return tmp_path


def _seed(db_path, *, runs: int = 1, with_shortlist: bool = False):
    conn = get_connection(db_path)
    run_migrations(conn)
    store.upsert_search(conn, name="home-gadgets-under-15-gbp")
    saved = store.get_search_by_name(conn, "home-gadgets-under-15-gbp")
    client = AliClient(Settings(mode="fixture"))
    for _ in range(runs):
        run_collection(conn, client, mode="fixture", searches=[saved])

    if with_shortlist:
        shortlist_id = shortlists.get_or_create_shortlist(conn, "test-shortlist")
        shortlists.add_products_to_shortlist(conn, shortlist_id, [1005006109529182])

    conn.close()


def test_dashboard_loads_with_data(_isolated_env):
    _seed(_isolated_env / "dashboard-test.db")

    at = AppTest.from_file(LAUNCHER)
    at.run(timeout=30)

    assert not at.exception
    assert any("3 product" in el.value for el in at.subheader)


def test_dashboard_momentum_tab_with_history(_isolated_env):
    # Two runs -- enough history for the momentum view to have something to show.
    _seed(_isolated_env / "dashboard-test.db", runs=2)

    at = AppTest.from_file(LAUNCHER)
    at.run(timeout=30)

    assert not at.exception


def test_dashboard_shortlists_tab_with_saved_shortlist(_isolated_env):
    _seed(_isolated_env / "dashboard-test.db", with_shortlist=True)

    at = AppTest.from_file(LAUNCHER)
    at.run(timeout=30)

    assert not at.exception


def test_dashboard_loads_with_empty_database(_isolated_env):
    at = AppTest.from_file(LAUNCHER)
    at.run(timeout=30)

    assert not at.exception
    assert any("0 product" in el.value for el in at.subheader)
