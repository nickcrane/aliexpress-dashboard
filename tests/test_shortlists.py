import pytest

from aliexpress_dashboard.client.models import NormalizedProduct
from aliexpress_dashboard.collector import store as collector_store
from aliexpress_dashboard.dashboard import shortlists
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(tmp_path / "test.db")
    run_migrations(connection)
    return connection


def _seed_product(conn, product_id, title):
    run_id = collector_store.create_run(conn, mode="fixture")
    product = NormalizedProduct(
        product_id=product_id,
        product_title=title,
        target_sale_price=9.99,
        target_sale_price_currency="GBP",
    )
    collector_store.upsert_product_and_observation(
        conn, product, run_id=run_id, search_id=None, captured_at="2026-01-01T00:00:00+00:00"
    )


def test_get_or_create_shortlist_is_idempotent(conn):
    id1 = shortlists.get_or_create_shortlist(conn, "my-list")
    id2 = shortlists.get_or_create_shortlist(conn, "my-list")
    assert id1 == id2


def test_add_products_and_load(conn):
    _seed_product(conn, 1, "Widget")
    _seed_product(conn, 2, "Gadget")

    shortlist_id = shortlists.get_or_create_shortlist(conn, "my-list")
    shortlists.add_products_to_shortlist(conn, shortlist_id, [1, 2])

    products = shortlists.load_shortlist_products(conn, shortlist_id)
    assert set(products["product_id"]) == {1, 2}


def test_add_products_is_idempotent_no_duplicate_rows(conn):
    _seed_product(conn, 1, "Widget")
    shortlist_id = shortlists.get_or_create_shortlist(conn, "my-list")

    shortlists.add_products_to_shortlist(conn, shortlist_id, [1])
    shortlists.add_products_to_shortlist(conn, shortlist_id, [1])

    assert len(shortlists.load_shortlist_products(conn, shortlist_id)) == 1


def test_remove_product_from_shortlist(conn):
    _seed_product(conn, 1, "Widget")
    shortlist_id = shortlists.get_or_create_shortlist(conn, "my-list")
    shortlists.add_products_to_shortlist(conn, shortlist_id, [1])

    shortlists.remove_product_from_shortlist(conn, shortlist_id, 1)

    assert shortlists.load_shortlist_products(conn, shortlist_id).empty


def test_list_shortlists_reports_item_counts(conn):
    _seed_product(conn, 1, "Widget")
    _seed_product(conn, 2, "Gadget")
    shortlist_id = shortlists.get_or_create_shortlist(conn, "my-list")
    shortlists.add_products_to_shortlist(conn, shortlist_id, [1, 2])

    summaries = shortlists.list_shortlists(conn)
    assert len(summaries) == 1
    assert summaries[0].name == "my-list"
    assert summaries[0].item_count == 2


def test_delete_shortlist_removes_items_too(conn):
    _seed_product(conn, 1, "Widget")
    shortlist_id = shortlists.get_or_create_shortlist(conn, "my-list")
    shortlists.add_products_to_shortlist(conn, shortlist_id, [1])

    shortlists.delete_shortlist(conn, shortlist_id)

    assert shortlists.list_shortlists(conn) == []
    assert conn.execute("SELECT * FROM shortlist_items").fetchall() == []
