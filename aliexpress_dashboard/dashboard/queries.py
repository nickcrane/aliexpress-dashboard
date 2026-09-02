"""Read queries backing the dashboard. Kept separate from app.py so the
filtering logic can be unit tested without going through Streamlit.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd


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


def distinct_categories(conn: sqlite3.Connection) -> List[int]:
    """Category IDs seen in collected products. No name is available to
    show alongside them -- neither ds.* endpoint this app calls returns a
    category name, only category_id (see AliClient.get_categories)."""
    rows = conn.execute(
        "SELECT DISTINCT category_id FROM products WHERE category_id IS NOT NULL ORDER BY category_id"
    ).fetchall()
    return [row["category_id"] for row in rows]


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


def load_current_products(conn: sqlite3.Connection, filters: ProductFilters) -> pd.DataFrame:
    clauses = []
    params: dict = {}

    if filters.category_id is not None:
        clauses.append("p.category_id = :category_id")
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

    return pd.read_sql_query(sql, conn, params=params)
