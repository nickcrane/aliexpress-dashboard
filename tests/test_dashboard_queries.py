import pytest

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.collector.runner import run_collection
from aliexpress_dashboard.config import Settings
from aliexpress_dashboard.dashboard.queries import (
    ProductFilters,
    distinct_categories,
    distinct_ship_to_countries,
    distinct_target_currencies,
    load_current_products,
    load_price_history,
    max_target_price,
)
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations


@pytest.fixture
def seeded_conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)

    store.upsert_search(conn, name="home-gadgets-under-15-gbp", ship_to_country="GB")
    store.upsert_search(conn, name="trending-kitchen", ship_to_country="US")

    client = AliClient(Settings(mode="fixture"))
    searches = store.load_active_searches(conn)
    run_collection(conn, client, mode="fixture", searches=searches)
    return conn


def test_load_current_products_no_filters_returns_everything(seeded_conn):
    df = load_current_products(seeded_conn, ProductFilters())
    assert len(df) == 5  # 3 from home-gadgets + 2 from trending-kitchen, no overlap


def test_load_current_products_filters_by_category(seeded_conn):
    # category_id 1509 appears in both searches (the strainer and the slicer).
    df = load_current_products(seeded_conn, ProductFilters(category_id=1509))
    assert len(df) == 2
    assert (df["category_id"] == 1509).all()


def test_load_current_products_filters_by_price_band(seeded_conn):
    df = load_current_products(
        seeded_conn, ProductFilters(price_currency="GBP", min_price=5.0, max_price=7.0)
    )
    assert set(df["target_sale_price_currency"]) <= {"GBP"}
    assert (df["target_sale_price"] >= 5.0).all()
    assert (df["target_sale_price"] <= 7.0).all()


def test_load_current_products_min_price_requires_currency():
    with pytest.raises(ValueError):
        ProductFilters(min_price=5.0)


def test_load_current_products_min_rating_excludes_unknown_ratings(seeded_conn):
    # home-gadgets-under-15-gbp's second product has no evaluate_rate at all.
    df = load_current_products(seeded_conn, ProductFilters(min_rating=1.0))
    assert df["evaluate_rate"].notna().all()


def test_load_current_products_min_volume(seeded_conn):
    # home-gadgets-under-15-gbp's second product has sales_volume == 0.
    df = load_current_products(seeded_conn, ProductFilters(min_volume=1))
    assert (df["sales_volume"] >= 1).all()
    assert len(df) == 4


def test_load_current_products_filters_by_ship_to_country(seeded_conn):
    df = load_current_products(seeded_conn, ProductFilters(ship_to_country="US"))
    assert len(df) == 2
    assert set(df["ship_to_country"]) == {"US"}


def test_distinct_categories(seeded_conn):
    assert set(distinct_categories(seeded_conn)) == {1503, 1509, 1512, 1520}


def test_distinct_ship_to_countries(seeded_conn):
    assert distinct_ship_to_countries(seeded_conn) == ["GB", "US"]


def test_distinct_target_currencies(seeded_conn):
    assert distinct_target_currencies(seeded_conn) == ["GBP"]


def test_max_target_price(seeded_conn):
    assert max_target_price(seeded_conn, "GBP") == pytest.approx(11.45)
    assert max_target_price(seeded_conn, "JPY") is None


def test_queries_on_empty_database(tmp_path):
    conn = get_connection(tmp_path / "empty.db")
    run_migrations(conn)

    assert load_current_products(conn, ProductFilters()).empty
    assert distinct_categories(conn) == []
    assert distinct_ship_to_countries(conn) == []
    assert distinct_target_currencies(conn) == []
    assert max_target_price(conn, "GBP") is None


def test_load_price_history_omits_products_with_only_one_observation(seeded_conn):
    # seeded_conn has run the collector exactly once -- nothing has 2+ observations yet.
    product_ids = load_current_products(seeded_conn, ProductFilters())["product_id"].tolist()
    assert load_price_history(seeded_conn, product_ids) == {}


def test_load_price_history_returns_ordered_prices_after_a_second_run(tmp_path):
    conn = get_connection(tmp_path / "history.db")
    run_migrations(conn)
    store.upsert_search(conn, name="home-gadgets-under-15-gbp")
    saved = store.get_search_by_name(conn, "home-gadgets-under-15-gbp")
    client = AliClient(Settings(mode="fixture"))

    run_collection(conn, client, mode="fixture", searches=[saved])
    run_collection(conn, client, mode="fixture", searches=[saved])

    history = load_price_history(conn, [1005006109529182])
    assert history[1005006109529182] == [6.99, 6.99]


def test_load_price_history_empty_product_list(seeded_conn):
    assert load_price_history(seeded_conn, []) == {}
