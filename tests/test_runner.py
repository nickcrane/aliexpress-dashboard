import json
import time

import pytest

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.collector.runner import run_collection
from aliexpress_dashboard.config import Settings
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations

LAMP_ID = 1005006109529182


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(tmp_path / "test.db")
    run_migrations(connection)
    return connection


@pytest.fixture
def client():
    return AliClient(Settings(mode="fixture"))


def _add_search(conn, **kwargs):
    store.upsert_search(conn, **kwargs)
    return store.get_search_by_name(conn, kwargs["name"])


def test_run_collection_writes_products_and_observations(conn, client):
    saved = _add_search(conn, name="home-gadgets-under-15-gbp")
    summary = run_collection(conn, client, mode="fixture", searches=[saved])

    assert summary.searches_executed == 1
    assert summary.records_written == 3
    assert summary.errors == []
    assert len(conn.execute("SELECT * FROM products").fetchall()) == 3
    assert len(conn.execute("SELECT * FROM observations WHERE run_id = ?", (summary.run_id,)).fetchall()) == 3


def test_run_collection_isolates_failed_search(conn, client):
    good = _add_search(conn, name="home-gadgets-under-15-gbp")
    bad = _add_search(conn, name="totally-missing-fixture")

    summary = run_collection(conn, client, mode="fixture", searches=[good, bad])

    assert summary.searches_executed == 2
    assert summary.records_written == 3  # only the good search's products
    assert len(summary.errors) == 1
    assert summary.errors[0]["search_name"] == "totally-missing-fixture"

    run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (summary.run_id,)).fetchone()
    assert run_row["finished_at"] is not None
    assert run_row["searches_executed"] == 2
    assert run_row["records_written"] == 3
    errors = json.loads(run_row["errors_json"])
    assert errors[0]["search_name"] == "totally-missing-fixture"


def test_run_collection_dedupes_same_product_within_one_run(conn, client):
    # Both fixtures include product LAMP_ID -- must produce exactly one
    # observation row for it in this run, not two.
    search_a = _add_search(conn, name="home-gadgets-under-15-gbp")
    search_b = _add_search(conn, name="electronics-under-10-gbp")

    summary = run_collection(conn, client, mode="fixture", searches=[search_a, search_b])

    rows = conn.execute(
        "SELECT * FROM observations WHERE product_id = ? AND run_id = ?", (LAMP_ID, summary.run_id)
    ).fetchall()
    assert len(rows) == 1
    # electronics-under-10-gbp ran second, so its price is what should have stuck.
    assert rows[0]["sale_price"] == 5.99


def test_running_collector_twice_adds_history_not_duplicates(conn, client):
    saved = _add_search(conn, name="home-gadgets-under-15-gbp")

    first = run_collection(conn, client, mode="fixture", searches=[saved])
    second = run_collection(conn, client, mode="fixture", searches=[saved])

    assert first.run_id != second.run_id

    observations = conn.execute("SELECT * FROM observations WHERE product_id = ?", (LAMP_ID,)).fetchall()
    assert len(observations) == 2  # one per run: legitimate history, not a duplicate

    product = conn.execute("SELECT * FROM products WHERE product_id = ?", (LAMP_ID,)).fetchone()
    assert product["last_run_id"] == second.run_id


def test_product_first_seen_at_is_preserved_across_runs(conn, client):
    saved = _add_search(conn, name="home-gadgets-under-15-gbp")

    run_collection(conn, client, mode="fixture", searches=[saved])
    first_seen = conn.execute(
        "SELECT first_seen_at FROM products WHERE product_id = ?", (LAMP_ID,)
    ).fetchone()["first_seen_at"]

    time.sleep(0.01)
    run_collection(conn, client, mode="fixture", searches=[saved])
    row_after_second = conn.execute(
        "SELECT first_seen_at, last_seen_at FROM products WHERE product_id = ?", (LAMP_ID,)
    ).fetchone()

    assert row_after_second["first_seen_at"] == first_seen
    assert row_after_second["last_seen_at"] > first_seen


def test_run_collection_with_no_searches(conn, client):
    summary = run_collection(conn, client, mode="fixture", searches=[])
    assert summary.searches_executed == 0
    assert summary.records_written == 0
    assert summary.errors == []


def test_run_collection_follows_pagination_across_pages(conn, client):
    saved = _add_search(conn, name="paginated-search")
    summary = run_collection(conn, client, mode="fixture", searches=[saved])

    assert summary.searches_executed == 1
    assert summary.errors == []
    assert summary.records_written == 3  # 2 from page 1 + 1 from page 2

    products = conn.execute("SELECT product_id FROM products").fetchall()
    assert {row["product_id"] for row in products} == {
        1005010111222333,
        1005010222333444,
        1005010333444555,
    }


def test_run_collection_pagination_keeps_partial_results_on_later_page_failure(conn, client):
    # total_record_count says 3, but no page 2 fixture exists -- page 1's
    # single product must still be written, not discarded as a full failure.
    saved = _add_search(conn, name="paginated-search-missing-page2")
    summary = run_collection(conn, client, mode="fixture", searches=[saved])

    assert summary.searches_executed == 1
    assert summary.errors == []  # page 1 succeeded; the search as a whole didn't fail
    assert summary.records_written == 1

    products = conn.execute("SELECT product_id FROM products").fetchall()
    assert {row["product_id"] for row in products} == {1005010444555666}


def test_run_collection_pagination_stops_at_safety_cap(conn, client, monkeypatch):
    monkeypatch.setattr("aliexpress_dashboard.collector.runner.MAX_PAGES_PER_SEARCH", 1)

    saved = _add_search(conn, name="paginated-search")
    summary = run_collection(conn, client, mode="fixture", searches=[saved])

    # Capped after page 1 -- only 2 of the 3 available products, and no
    # attempt was made to fetch page 2.
    assert summary.records_written == 2
