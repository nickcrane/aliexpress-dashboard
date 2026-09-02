import pytest

from aliexpress_dashboard.client.models import NormalizedProduct
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(tmp_path / "test.db")
    run_migrations(connection)
    return connection


def test_upsert_search_creates_then_updates_in_place(conn):
    store.upsert_search(conn, name="s1", keywords="lamp")
    saved = store.get_search_by_name(conn, "s1")
    assert saved.params.keywords == "lamp"

    store.upsert_search(conn, name="s1", keywords="usb lamp")
    saved = store.get_search_by_name(conn, "s1")
    assert saved.params.keywords == "usb lamp"
    assert len(store.list_all_searches(conn)) == 1


def test_upsert_search_requires_currency_with_price_band(conn):
    with pytest.raises(ValueError):
        store.upsert_search(conn, name="s2", min_price=5.0)


def test_load_active_searches_excludes_inactive(conn):
    store.upsert_search(conn, name="active", is_active=True)
    store.upsert_search(conn, name="inactive", is_active=False)

    assert [s.params.name for s in store.load_active_searches(conn)] == ["active"]
    assert {s.params.name for s in store.list_all_searches(conn)} == {"active", "inactive"}


def _product(**overrides):
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
    return NormalizedProduct(**defaults)


def _new_run(conn):
    return store.create_run(conn, mode="fixture")


def test_upsert_product_and_observation_creates_row(conn):
    run_id = _new_run(conn)
    store.upsert_product_and_observation(
        conn, _product(), run_id=run_id, search_id=None, captured_at="2026-01-01T00:00:00+00:00"
    )
    row = conn.execute("SELECT * FROM products WHERE product_id = 1").fetchone()
    assert row["sale_price"] == 9.99
    assert row["first_seen_at"] == "2026-01-01T00:00:00+00:00"


def test_upsert_product_updates_attributes_but_preserves_first_seen_at(conn):
    run1 = _new_run(conn)
    store.upsert_product_and_observation(
        conn, _product(sale_price=9.99), run_id=run1, search_id=None, captured_at="2026-01-01T00:00:00+00:00"
    )

    run2 = _new_run(conn)
    store.upsert_product_and_observation(
        conn, _product(sale_price=7.99), run_id=run2, search_id=None, captured_at="2026-01-02T00:00:00+00:00"
    )

    row = conn.execute("SELECT * FROM products WHERE product_id = 1").fetchone()
    assert row["sale_price"] == 7.99
    assert row["first_seen_at"] == "2026-01-01T00:00:00+00:00"
    assert row["last_seen_at"] == "2026-01-02T00:00:00+00:00"
    assert row["last_run_id"] == run2

    observations = conn.execute("SELECT * FROM observations WHERE product_id = 1").fetchall()
    assert len(observations) == 2


def test_upsert_observation_same_run_id_does_not_duplicate(conn):
    run1 = _new_run(conn)
    store.upsert_product_and_observation(
        conn, _product(sale_price=9.99), run_id=run1, search_id=None, captured_at="2026-01-01T00:00:00+00:00"
    )
    store.upsert_product_and_observation(
        conn, _product(sale_price=8.49), run_id=run1, search_id=None, captured_at="2026-01-01T00:05:00+00:00"
    )

    observations = conn.execute(
        "SELECT * FROM observations WHERE product_id = 1 AND run_id = ?", (run1,)
    ).fetchall()
    assert len(observations) == 1
    assert observations[0]["sale_price"] == 8.49
