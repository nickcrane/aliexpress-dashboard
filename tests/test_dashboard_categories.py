import pytest

from aliexpress_dashboard.client.models import NormalizedCategory
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.dashboard.categories import category_display, load_category_paths
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(tmp_path / "test.db")
    run_migrations(connection)
    return connection


def test_load_category_paths_builds_full_lineage(conn):
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=509, category_name="Consumer Electronics", parent_category_id=None),
            NormalizedCategory(category_id=200002395, category_name="Smart Electronics", parent_category_id=509),
            NormalizedCategory(
                category_id=200003814, category_name="Smart Wearable Devices", parent_category_id=200002395
            ),
        ],
    )
    paths = load_category_paths(conn)
    assert paths[509].path == "Consumer Electronics"
    assert paths[200002395].path == "Consumer Electronics > Smart Electronics"
    assert paths[200003814].path == "Consumer Electronics > Smart Electronics > Smart Wearable Devices"


def test_load_category_paths_top_level_has_no_ancestors(conn):
    store.upsert_categories(conn, [NormalizedCategory(category_id=1501, category_name="Home & Garden")])
    paths = load_category_paths(conn)
    assert paths[1501].name == "Home & Garden"
    assert paths[1501].path == "Home & Garden"


def test_load_category_paths_tolerates_a_cycle(conn):
    # Shouldn't happen with real AliExpress data, but a malformed/cyclic
    # parent chain must not hang -- confirms the `seen` guard actually works.
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=1, category_name="A", parent_category_id=2),
            NormalizedCategory(category_id=2, category_name="B", parent_category_id=1),
        ],
    )
    paths = load_category_paths(conn)
    assert paths[1].path in ("A > B", "B > A")


def test_category_display_falls_back_for_unknown_id(conn):
    paths = load_category_paths(conn)  # empty -- nothing synced
    assert category_display(1503, paths) == ("Category 1503", "Category 1503")


def test_category_display_none_for_none_id(conn):
    paths = load_category_paths(conn)
    assert category_display(None, paths) == (None, None)


def test_category_display_resolves_known_id(conn):
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=15, category_name="Home & Garden"),
            NormalizedCategory(category_id=1503, category_name="Lighting", parent_category_id=15),
        ],
    )
    paths = load_category_paths(conn)
    assert category_display(1503, paths) == ("Lighting", "Home & Garden > Lighting")


def test_category_display_falls_back_through_ancestor_chain(conn):
    # The realistic case this whole thing exists for: AliExpress's
    # category lookup covers the root (30 "Security & Protection") but
    # not the deep leaf id a real product is actually tagged with.
    store.upsert_categories(conn, [NormalizedCategory(category_id=30, category_name="Security & Protection")])
    paths = load_category_paths(conn)
    ancestor_ids = [30, 202245601, 200004311, 200332166]  # leaf (200332166) unresolved
    assert category_display(200332166, paths, ancestor_ids) == (
        "Security & Protection",
        "Security & Protection",
    )


def test_category_display_prefers_the_most_specific_resolvable_ancestor(conn):
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=44, category_name="Consumer Electronics"),
            NormalizedCategory(category_id=200003803, category_name="Smart Electronics", parent_category_id=44),
        ],
    )
    paths = load_category_paths(conn)
    ancestor_ids = [44, 200003803, 200099999]  # leaf (200099999) unresolved, its parent is
    assert category_display(200099999, paths, ancestor_ids) == (
        "Smart Electronics",
        "Consumer Electronics > Smart Electronics",
    )


def test_category_display_tries_leaf_before_ancestors(conn):
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=44, category_name="Consumer Electronics"),
            NormalizedCategory(category_id=1503, category_name="Lighting", parent_category_id=44),
        ],
    )
    paths = load_category_paths(conn)
    assert category_display(1503, paths, [44, 1503]) == ("Lighting", "Consumer Electronics > Lighting")


def test_category_display_falls_back_when_no_ancestor_resolves_either(conn):
    paths = load_category_paths(conn)  # nothing synced at all
    assert category_display(200332166, paths, [30, 202245601, 200332166]) == (
        "Category 200332166",
        "Category 200332166",
    )


def test_upsert_categories_is_idempotent_and_updates_in_place(conn):
    store.upsert_categories(conn, [NormalizedCategory(category_id=15, category_name="Home & Garden")])
    store.upsert_categories(conn, [NormalizedCategory(category_id=15, category_name="Home & Garden (renamed)")])
    paths = load_category_paths(conn)
    assert paths[15].name == "Home & Garden (renamed)"
    assert conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"] == 1
