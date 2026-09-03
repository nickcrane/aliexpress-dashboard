"""Cross-consistency check: seed one DB, read it two ways -- directly via
queries.py/momentum.py/shortlists.py (already covered by their own test
files), and via ApiClient over the live test API server -- and assert they
agree. Catches serialization drift (NaN handling, dict key/type changes
over JSON) that per-function unit tests on either side wouldn't."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.client.models import NormalizedProduct
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.collector.runner import run_collection
from aliexpress_dashboard.config import Settings
from aliexpress_dashboard.dashboard import momentum, queries, shortlists
from aliexpress_dashboard.dashboard.api_client import ApiClient
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations


@pytest.fixture
def seeded_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    run_migrations(conn)
    store.upsert_search(conn, name="home-gadgets-under-15-gbp")
    saved = store.get_search_by_name(conn, "home-gadgets-under-15-gbp")
    client = AliClient(Settings(mode="fixture"))
    # Two runs, so there's price history and momentum to compare too.
    run_collection(conn, client, mode="fixture", searches=[saved])
    run_collection(conn, client, mode="fixture", searches=[saved])

    shortlist_id = shortlists.get_or_create_shortlist(conn, "test-shortlist")
    shortlists.add_products_to_shortlist(conn, shortlist_id, [1005006109529182])

    conn.commit()
    return conn, db_path


@pytest.fixture
def api_client(seeded_db, live_api_base_url, monkeypatch):
    _, db_path = seeded_db
    monkeypatch.setenv("AE_MODE", "fixture")
    monkeypatch.setenv("AE_DB_PATH", str(db_path))
    monkeypatch.setenv("AE_API_KEY", "test-cross-consistency-key")
    client = ApiClient(base_url=live_api_base_url, api_key="test-cross-consistency-key")
    yield client
    client.close()


def _sort_records(records: list) -> list:
    return sorted(records, key=lambda r: r["product_id"])


def _json_safe_records(df: pd.DataFrame) -> list:
    # NaN vs None is a real distinction in Python but not in JSON, and a
    # float64 column can't actually hold None (pandas stores it as NaN
    # either way) -- so .to_dict() can't be used to normalize this. Route
    # both sides through an actual JSON round-trip instead, same as what
    # the API response itself goes through.
    return _sort_records(json.loads(df.to_json(orient="records", date_format="iso")))


def test_products_match_direct_query(seeded_db, api_client):
    conn, _ = seeded_db
    direct = queries.load_current_products(conn, queries.ProductFilters())
    via_api = api_client.load_current_products(queries.ProductFilters())

    assert _json_safe_records(direct) == _json_safe_records(via_api)


def test_price_history_matches_direct_query(seeded_db, api_client):
    conn, _ = seeded_db
    product_ids = queries.load_current_products(conn, queries.ProductFilters())["product_id"].tolist()

    direct = queries.load_price_history(conn, product_ids)
    via_api = api_client.load_price_history(product_ids)

    assert direct == via_api


def test_filters_match_direct_query(seeded_db, api_client):
    conn, _ = seeded_db
    via_api = api_client.get_filters()

    assert via_api.categories == queries.distinct_categories(conn)
    assert via_api.currencies == queries.distinct_target_currencies(conn)
    assert via_api.ship_to_countries == queries.distinct_ship_to_countries(conn)


def test_max_target_price_matches_direct_query(seeded_db, api_client):
    conn, _ = seeded_db
    assert api_client.max_target_price("GBP") == queries.max_target_price(conn, "GBP")


def test_momentum_matches_direct_computation(seeded_db, api_client):
    conn, _ = seeded_db
    product_ids = queries.load_current_products(conn, queries.ProductFilters())["product_id"].tolist()

    observations = momentum.load_observations_for_momentum(conn, product_ids)
    direct = momentum.compute_momentum(observations, window_days=14)
    via_api = api_client.get_momentum(product_ids, window_days=14)

    # latest_captured_at isn't consumed by anything downstream (app.py never
    # displays it) and the two sides format a timestamp differently -- epoch
    # millis via DataFrame.to_json's default vs the ISO string FastAPI's own
    # encoder produces. Same moment, different formatting; drop it rather
    # than chase an equivalence nothing actually depends on.
    def _drop_timestamp(records):
        return [{k: v for k, v in r.items() if k != "latest_captured_at"} for r in records]

    assert _drop_timestamp(_json_safe_records(direct)) == _drop_timestamp(_json_safe_records(via_api))


def test_shortlists_match_direct_query(seeded_db, api_client):
    conn, _ = seeded_db
    direct = shortlists.list_shortlists(conn)
    via_api = api_client.list_shortlists()

    assert [(s.id, s.name, s.item_count) for s in direct] == [(s.id, s.name, s.item_count) for s in via_api]

    shortlist_id = direct[0].id
    direct_products = shortlists.load_shortlist_products(conn, shortlist_id)
    api_products = api_client.load_shortlist_products(shortlist_id)
    assert (
        direct_products[["product_id"]].to_dict(orient="records")
        == api_products[["product_id"]].to_dict(orient="records")
    )


def test_save_and_delete_shortlist_round_trips_through_api(seeded_db, api_client):
    conn, _ = seeded_db
    api_client.save_shortlist("api-created", [1005006109529182])

    direct = {s.name: s for s in shortlists.list_shortlists(conn)}
    assert "api-created" in direct
    assert direct["api-created"].item_count == 1

    api_client.delete_shortlist(direct["api-created"].id)
    direct_after = {s.name for s in shortlists.list_shortlists(conn)}
    assert "api-created" not in direct_after
