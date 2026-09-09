"""Read queries backing the dashboard. Shared by api/app.py (the data API)
and web/app.py (via api_client.py), kept separate so the filtering logic
can be unit tested without going through either.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .categories import category_display, load_category_paths, resolve_category_id


@dataclass
class ProductFilters:
    category_id: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    price_currency: Optional[str] = None  # required whenever min_price/max_price is set
    min_rating: Optional[float] = None  # filters on evaluate_rate (%), the field populated by every search result
    min_volume: Optional[int] = None
    ship_to_country: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.min_price is not None or self.max_price is not None) and not self.price_currency:
            raise ValueError("price_currency is required when min_price/max_price is set")


# ship_to_country isn't a product attribute the API returns -- it's a search
# parameter. We attach it via the search that produced each product's most
# recent observation (products.last_run_id), which is the same "last writer
# wins" attribution documented in the collector for products matched by more
# than one search in a single run.
_CURRENT_PRODUCTS_SQL = """
    SELECT
        p.product_id,
        p.product_title,
        p.product_main_image_url,
        p.product_url,
        p.category_id,
        p.category_ancestor_ids,
        p.target_sale_price,
        p.target_sale_price_currency,
        p.discount,
        p.evaluate_rate,
        p.review_count,
        p.avg_rating,
        p.sales_volume,
        p.sales_volume_display,
        p.first_seen_at,
        p.last_seen_at,
        s.ship_to_country
    FROM products p
    LEFT JOIN observations o ON o.product_id = p.product_id AND o.run_id = p.last_run_id
    LEFT JOIN searches s ON s.id = o.search_id
"""


def distinct_categories(conn: sqlite3.Connection) -> List[dict]:
    """Category ids seen in collected products, each paired with its name
    and full parent lineage via the `categories` table (see
    dashboard/categories.py) -- falls back to a synthetic "Category <id>"
    label for any id (and its ancestors) categories hasn't been synced
    for yet. One representative row's category_ancestor_ids per distinct
    id is enough -- it's the same product-side path regardless of which
    row happens to be picked."""
    rows = conn.execute(
        """
        SELECT category_id, MIN(category_ancestor_ids) AS category_ancestor_ids
        FROM products
        WHERE category_id IS NOT NULL
        GROUP BY category_id
        ORDER BY category_id
        """
    ).fetchall()
    paths = load_category_paths(conn)
    result = []
    for row in rows:
        category_id = row["category_id"]
        ancestor_ids = json.loads(row["category_ancestor_ids"]) if row["category_ancestor_ids"] else ()
        name, path = category_display(category_id, paths, ancestor_ids)
        result.append({"category_id": category_id, "category_name": name, "category_path": path})
    return result


def category_tree(conn: sqlite3.Connection) -> List[dict]:
    """Two-level {parent -> children} structure for a cascading category
    filter (pick a parent, then a child scoped to it), restricted to
    categories actually reachable by at least one collected product --
    via that product's *resolved* category id (see category_display),
    which might be an ancestor of its true leaf, not the leaf itself.
    A resolved id that's already top-level becomes a parent with no
    children of its own (still directly selectable)."""
    rows = conn.execute(
        """
        SELECT category_id, MIN(category_ancestor_ids) AS category_ancestor_ids
        FROM products
        WHERE category_id IS NOT NULL
        GROUP BY category_id
        """
    ).fetchall()
    paths = load_category_paths(conn)

    resolved_ids = set()
    for row in rows:
        category_id = row["category_id"]
        ancestor_ids = json.loads(row["category_ancestor_ids"]) if row["category_ancestor_ids"] else ()
        resolved = resolve_category_id(category_id, paths, ancestor_ids)
        if resolved is not None:
            resolved_ids.add(resolved)

    tree: Dict[int, dict] = {}
    for resolved_id in resolved_ids:
        info = paths[resolved_id]
        parent_node = tree.setdefault(
            info.root_id, {"category_id": info.root_id, "category_name": info.root_name, "children": []}
        )
        if resolved_id != info.root_id:
            parent_node["children"].append({"category_id": resolved_id, "category_name": info.name})

    for node in tree.values():
        node["children"].sort(key=lambda c: c["category_name"])
    return sorted(tree.values(), key=lambda n: n["category_name"])


def category_tree_coverage(conn: sqlite3.Connection) -> dict:
    """How much of the synced `categories` table category_tree's parent
    dropdown actually shows, vs. the full set sync-categories pulled
    from AliExpress -- explains why the picker's parent list is usually
    much shorter than AliExpress's real top-level category count: only
    categories reachable by at least one *collected* product show up
    (see category_tree), and this app's collector has typically only
    run a handful of searches, not exhaustively covered the catalog.
    Grows on its own as more/broader collector runs bring in products
    from categories not seen yet -- no action needed beyond collecting
    more, if a wider parent list is wanted."""
    total_parents = conn.execute(
        "SELECT COUNT(*) AS n FROM categories WHERE parent_category_id IS NULL"
    ).fetchone()["n"]
    total_categories = conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
    tree = category_tree(conn)
    return {
        "parent_categories_shown": len(tree),
        "parent_categories_synced_total": total_parents,
        "child_categories_shown": sum(len(node["children"]) for node in tree),
        "categories_synced_total": total_categories,
    }


def distinct_ship_to_countries(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT DISTINCT ship_to_country FROM searches "
        "WHERE ship_to_country IS NOT NULL ORDER BY ship_to_country"
    ).fetchall()
    return [row["ship_to_country"] for row in rows]


def distinct_target_currencies(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT DISTINCT target_sale_price_currency FROM products "
        "WHERE target_sale_price_currency IS NOT NULL ORDER BY target_sale_price_currency"
    ).fetchall()
    return [row["target_sale_price_currency"] for row in rows]


def load_price_history(conn: sqlite3.Connection, product_ids: List[int], *, min_points: int = 2) -> Dict[int, List[float]]:
    """One list of target_sale_price values per product, oldest first, for
    the sparkline column. A product needs at least `min_points` observations
    with a usable price to appear -- with only one, there's no history to
    draw, so it's omitted rather than shown as a flat, meaningless line."""
    if not product_ids:
        return {}

    placeholders = ",".join("?" for _ in product_ids)
    rows = conn.execute(
        f"""
        SELECT product_id, target_sale_price, captured_at
        FROM observations
        WHERE product_id IN ({placeholders}) AND target_sale_price IS NOT NULL
        ORDER BY product_id, captured_at
        """,
        product_ids,
    ).fetchall()

    history: Dict[int, List[float]] = {}
    for row in rows:
        history.setdefault(row["product_id"], []).append(row["target_sale_price"])

    return {product_id: prices for product_id, prices in history.items() if len(prices) >= min_points}


def max_target_price(conn: sqlite3.Connection, currency: str) -> Optional[float]:
    row = conn.execute(
        "SELECT MAX(target_sale_price) AS max_price FROM products WHERE target_sale_price_currency = ?",
        (currency,),
    ).fetchone()
    return row["max_price"] if row and row["max_price"] is not None else None


def _safe_round(value, ndigits: int = 2) -> Optional[float]:
    return None if value is None or pd.isna(value) else round(float(value), ndigits)


def category_market_stats(conn: sqlite3.Connection, category_id: int, *, price_bands: int = 4) -> dict:
    """Aggregate signal for one category's currently-collected products --
    feeds the onboarding LLM's market gap analysis (spa/app.py). Reuses
    load_current_products so a parent category id picks up every child
    under it, exactly like the Products page filter does.

    avg_rating/review_count are deliberately excluded: this collector
    only ever populates them via per-product detail lookups, which
    nothing here currently runs, so they're 0% populated on real data
    (confirmed against the live DB) -- evaluate_rate (positive-feedback
    %) is the rating signal search results actually carry.
    """
    df = load_current_products(conn, ProductFilters(category_id=category_id))
    if df.empty:
        return {"category_id": category_id, "product_count": 0, "price_bands": []}

    # Price stats only make sense within one currency -- collected
    # products can mix currencies across searches run with different
    # settings, and averaging across them would be meaningless. Use
    # whichever currency most of this category's products were priced in.
    currency_counts = df["target_sale_price_currency"].value_counts()
    dominant_currency = str(currency_counts.index[0]) if not currency_counts.empty else None
    priced = df[df["target_sale_price_currency"] == dominant_currency] if dominant_currency else df.iloc[0:0]
    prices = priced["target_sale_price"].dropna()

    bands: List[dict] = []
    if len(prices) > 0:
        low, high = float(prices.min()), float(prices.max())
        width = (high - low) / price_bands if high > low else 0
        for i in range(price_bands):
            band_low = low + width * i
            band_high = high if i == price_bands - 1 else low + width * (i + 1)
            if i == price_bands - 1:
                in_band = priced[(priced["target_sale_price"] >= band_low) & (priced["target_sale_price"] <= band_high)]
            else:
                in_band = priced[(priced["target_sale_price"] >= band_low) & (priced["target_sale_price"] < band_high)]
            if in_band.empty:
                continue
            bands.append(
                {
                    "price_low": round(band_low, 2),
                    "price_high": round(band_high, 2),
                    "product_count": int(len(in_band)),
                    "avg_positive_feedback_pct": _safe_round(in_band["evaluate_rate"].mean()),
                    "median_sales_volume": _safe_round(in_band["sales_volume"].median(), 0),
                }
            )

    return {
        "category_id": category_id,
        "product_count": int(len(df)),
        "price_currency": dominant_currency,
        "price_min": _safe_round(prices.min()) if len(prices) else None,
        "price_median": _safe_round(prices.median()) if len(prices) else None,
        "price_max": _safe_round(prices.max()) if len(prices) else None,
        "avg_discount_pct": _safe_round(df["discount"].mean()),
        "avg_positive_feedback_pct": _safe_round(df["evaluate_rate"].mean()),
        "median_sales_volume": _safe_round(df["sales_volume"].median(), 0),
        "price_bands": bands,
    }


def load_current_products(conn: sqlite3.Connection, filters: ProductFilters) -> pd.DataFrame:
    clauses = []
    params: dict = {}

    if filters.category_id is not None:
        # Matches the exact leaf id, or any product whose full category
        # path (category_ancestor_ids) passes through this id -- so
        # filtering by a parent from the cascading category picker
        # correctly includes every child under it, not just products
        # whose leaf id happens to equal the parent's exactly.
        clauses.append(
            "(p.category_id = :category_id OR EXISTS "
            "(SELECT 1 FROM json_each(p.category_ancestor_ids) WHERE json_each.value = :category_id))"
        )
        params["category_id"] = filters.category_id
    if filters.price_currency is not None:
        clauses.append("p.target_sale_price_currency = :price_currency")
        params["price_currency"] = filters.price_currency
    if filters.min_price is not None:
        clauses.append("p.target_sale_price >= :min_price")
        params["min_price"] = filters.min_price
    if filters.max_price is not None:
        clauses.append("p.target_sale_price <= :max_price")
        params["max_price"] = filters.max_price
    if filters.min_rating is not None:
        # evaluate_rate IS NULL fails this comparison in SQL, which is the
        # right call: a product with an unknown rating shouldn't pass a
        # minimum-rating filter.
        clauses.append("p.evaluate_rate >= :min_rating")
        params["min_rating"] = filters.min_rating
    if filters.min_volume is not None:
        clauses.append("p.sales_volume >= :min_volume")
        params["min_volume"] = filters.min_volume
    if filters.ship_to_country is not None:
        clauses.append("s.ship_to_country = :ship_to_country")
        params["ship_to_country"] = filters.ship_to_country

    sql = _CURRENT_PRODUCTS_SQL
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY p.last_seen_at DESC"

    df = pd.read_sql_query(sql, conn, params=params)
    paths = load_category_paths(conn)

    def _resolve(row: pd.Series) -> Tuple[Optional[str], Optional[str]]:
        # A nullable INTEGER column comes back from pandas as float64 (NaN
        # for NULL rows), so category_id here can be e.g. 1503.0 --
        # normalize back to a plain int (or None) before using it as a
        # categories dict key.
        category_id = int(row["category_id"]) if pd.notna(row["category_id"]) else None
        raw_ancestors = row["category_ancestor_ids"]
        ancestor_ids = json.loads(raw_ancestors) if isinstance(raw_ancestors, str) and raw_ancestors else ()
        return category_display(category_id, paths, ancestor_ids)

    if df.empty:
        # DataFrame.apply(axis=1) on zero rows can't infer that _resolve
        # returns a 2-tuple (it returns an empty DataFrame instead of a
        # Series of tuples in that case), so handle it directly instead.
        df["category_name"] = pd.Series(dtype=object)
        df["category_path"] = pd.Series(dtype=object)
    else:
        resolved = df.apply(_resolve, axis=1)
        df["category_name"] = resolved.apply(lambda pair: pair[0])
        df["category_path"] = resolved.apply(lambda pair: pair[1])
    return df.drop(columns=["category_ancestor_ids"])
