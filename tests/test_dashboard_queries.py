import pytest

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.client.models import NormalizedCategory
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.collector.runner import run_collection
from aliexpress_dashboard.config import Settings
from aliexpress_dashboard.dashboard.queries import (
    ProductFilters,
    category_tree,
    category_tree_coverage,
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
    assert {c["category_id"] for c in distinct_categories(seeded_conn)} == {1503, 1509, 1512, 1520}


def test_distinct_categories_falls_back_when_unsynced(seeded_conn):
    # None of these ids have been synced into the categories table (no
    # sync-categories run in this fixture) -- each still gets a usable
    # label instead of erroring or coming back empty.
    for c in distinct_categories(seeded_conn):
        assert c["category_name"] == f"Category {c['category_id']}"
        assert c["category_path"] == c["category_name"]


def test_distinct_categories_resolves_name_and_lineage_once_synced(seeded_conn):
    store.upsert_categories(
        seeded_conn,
        [
            NormalizedCategory(category_id=15, category_name="Home & Garden", parent_category_id=None),
            NormalizedCategory(category_id=1509, category_name="Kitchen Fixtures", parent_category_id=15),
        ],
    )
    resolved = {c["category_id"]: c for c in distinct_categories(seeded_conn)}
    assert resolved[1509]["category_name"] == "Kitchen Fixtures"
    assert resolved[1509]["category_path"] == "Home & Garden > Kitchen Fixtures"
    # Still unsynced -- unaffected by the sync above.
    assert resolved[1503]["category_name"] == "Category 1503"


def test_load_current_products_includes_category_name_and_path(seeded_conn):
    store.upsert_categories(
        seeded_conn,
        [
            NormalizedCategory(category_id=15, category_name="Home & Garden", parent_category_id=None),
            NormalizedCategory(category_id=1509, category_name="Kitchen Fixtures", parent_category_id=15),
        ],
    )
    df = load_current_products(seeded_conn, ProductFilters(category_id=1509))
    assert (df["category_name"] == "Kitchen Fixtures").all()


def _upsert_product_with_ancestors(conn, *, product_id, category_id, category_ancestor_ids):
    from aliexpress_dashboard.client.models import NormalizedProduct

    run_id = store.create_run(conn, mode="fixture")
    product = NormalizedProduct(
        product_id=product_id,
        product_title="Deep-leaf product",
        category_id=category_id,
        category_ancestor_ids=category_ancestor_ids,
        target_sale_price=9.99,
        target_sale_price_currency="GBP",
    )
    store.upsert_product_and_observation(conn, product, run_id=run_id, search_id=None, captured_at="2026-01-01T00:00:00+00:00")
    conn.commit()


def test_category_resolution_falls_back_through_a_products_own_ancestor_path(tmp_path):
    """The realistic production case: AliExpress's category-name lookup
    only covers a broad/shallow tree, so a real product's specific leaf
    category id usually isn't in it -- but an ancestor a level or two up
    (present in the product's own cateId path, not derivable from the
    categories table alone) usually is."""
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    store.upsert_categories(conn, [NormalizedCategory(category_id=44, category_name="Consumer Electronics")])
    _upsert_product_with_ancestors(
        conn, product_id=1, category_id=200332166, category_ancestor_ids=[44, 200003803, 200332166]
    )

    resolved = {c["category_id"]: c for c in distinct_categories(conn)}
    assert resolved[200332166]["category_name"] == "Consumer Electronics"

    df = load_current_products(conn, ProductFilters())
    assert df.loc[df["product_id"] == 1, "category_name"].iloc[0] == "Consumer Electronics"
    assert "category_ancestor_ids" not in df.columns  # internal detail, not part of the public shape


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


def test_category_tree_groups_resolved_categories_by_root(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=44, category_name="Consumer Electronics"),
            NormalizedCategory(category_id=200003803, category_name="Smart Electronics", parent_category_id=44),
            NormalizedCategory(category_id=200001103, category_name="Games & Accessories", parent_category_id=44),
        ],
    )
    _upsert_product_with_ancestors(conn, product_id=1, category_id=200003803, category_ancestor_ids=[44, 200003803])
    _upsert_product_with_ancestors(conn, product_id=2, category_id=200001103, category_ancestor_ids=[44, 200001103])

    tree = category_tree(conn)
    assert len(tree) == 1
    parent = tree[0]
    assert parent["category_id"] == 44
    assert parent["category_name"] == "Consumer Electronics"
    child_names = {c["category_name"] for c in parent["children"]}
    assert child_names == {"Smart Electronics", "Games & Accessories"}


def test_category_tree_top_level_resolved_id_has_no_children(tmp_path):
    # A product whose deepest resolvable category IS a root -- still a
    # valid, directly-selectable parent, just with nothing under it.
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    store.upsert_categories(conn, [NormalizedCategory(category_id=30, category_name="Security & Protection")])
    _upsert_product_with_ancestors(
        conn, product_id=1, category_id=200332166, category_ancestor_ids=[30, 202245601, 200332166]
    )

    tree = category_tree(conn)
    assert tree == [{"category_id": 30, "category_name": "Security & Protection", "children": []}]


def test_category_tree_excludes_products_with_nothing_resolvable(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    # No categories synced at all -- nothing can resolve.
    _upsert_product_with_ancestors(conn, product_id=1, category_id=999, category_ancestor_ids=[999])
    assert category_tree(conn) == []


def test_load_current_products_filter_by_parent_matches_all_descendants(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=44, category_name="Consumer Electronics"),
            NormalizedCategory(category_id=200003803, category_name="Smart Electronics", parent_category_id=44),
        ],
    )
    _upsert_product_with_ancestors(conn, product_id=1, category_id=200003803, category_ancestor_ids=[44, 200003803])
    _upsert_product_with_ancestors(conn, product_id=2, category_id=1509, category_ancestor_ids=[1509])

    df = load_current_products(conn, ProductFilters(category_id=44))
    assert df["product_id"].tolist() == [1]


def test_load_current_products_filter_by_child_matches_only_that_child(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=44, category_name="Consumer Electronics"),
            NormalizedCategory(category_id=200003803, category_name="Smart Electronics", parent_category_id=44),
            NormalizedCategory(category_id=200001103, category_name="Games & Accessories", parent_category_id=44),
        ],
    )
    _upsert_product_with_ancestors(conn, product_id=1, category_id=200003803, category_ancestor_ids=[44, 200003803])
    _upsert_product_with_ancestors(conn, product_id=2, category_id=200001103, category_ancestor_ids=[44, 200001103])

    df = load_current_products(conn, ProductFilters(category_id=200003803))
    assert df["product_id"].tolist() == [1]


def test_load_current_products_filter_tolerates_null_ancestor_ids(tmp_path):
    # Real production scenario: rows collected before 0004 added this
    # column have category_ancestor_ids as a genuine SQL NULL, not "[]"
    # -- json_each(NULL) must not error out of the whole query.
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    _upsert_product_with_ancestors(conn, product_id=1, category_id=1509, category_ancestor_ids=[1509])
    conn.execute("UPDATE products SET category_ancestor_ids = NULL WHERE product_id = 1")
    conn.commit()

    df = load_current_products(conn, ProductFilters(category_id=1509))
    assert df["product_id"].tolist() == [1]  # still matches via the plain category_id equality branch


def test_category_tree_coverage_compares_shown_against_full_synced_set(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    # Three synced top-level categories, only one reachable by a product.
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=44, category_name="Consumer Electronics"),
            NormalizedCategory(category_id=200003803, category_name="Smart Electronics", parent_category_id=44),
            NormalizedCategory(category_id=15, category_name="Home & Garden"),
            NormalizedCategory(category_id=30, category_name="Security & Protection"),
        ],
    )
    _upsert_product_with_ancestors(conn, product_id=1, category_id=200003803, category_ancestor_ids=[44, 200003803])

    coverage = category_tree_coverage(conn)
    assert coverage == {
        "parent_categories_shown": 1,
        "parent_categories_synced_total": 3,
        "child_categories_shown": 1,
        "categories_synced_total": 4,
    }


def test_category_tree_coverage_on_empty_database(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    assert category_tree_coverage(conn) == {
        "parent_categories_shown": 0,
        "parent_categories_synced_total": 0,
        "child_categories_shown": 0,
        "categories_synced_total": 0,
    }
