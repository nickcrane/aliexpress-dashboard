"""SQLite access for the collector: saved searches, runs, and the
products/observations upsert that's the whole point of the history table.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from ..client.models import NormalizedProduct, SearchParams


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SavedSearch:
    id: int
    is_active: bool
    params: SearchParams


def _row_to_saved_search(row: sqlite3.Row) -> SavedSearch:
    params = SearchParams(
        name=row["name"],
        keywords=row["keywords"],
        category_id=row["category_id"],
        min_price=row["min_price"],
        max_price=row["max_price"],
        price_currency=row["price_currency"],
        sort=row["sort"],
        ship_to_country=row["ship_to_country"],
        selection_name=row["selection_name"],
    )
    return SavedSearch(id=row["id"], is_active=bool(row["is_active"]), params=params)


def upsert_search(
    conn: sqlite3.Connection,
    *,
    name: str,
    keywords: Optional[str] = None,
    category_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    price_currency: Optional[str] = None,
    sort: Optional[str] = None,
    ship_to_country: Optional[str] = None,
    selection_name: Optional[str] = None,
    is_active: bool = True,
) -> None:
    # Validated the same way the client validates it, so a bad price band
    # or sort value never makes it into the database in the first place.
    SearchParams(
        name=name,
        keywords=keywords,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        price_currency=price_currency,
        sort=sort,
        ship_to_country=ship_to_country,
        selection_name=selection_name,
    )
    conn.execute(
        """
        INSERT INTO searches (
            name, keywords, category_id, min_price, max_price,
            price_currency, sort, ship_to_country, selection_name, is_active
        ) VALUES (
            :name, :keywords, :category_id, :min_price, :max_price,
            :price_currency, :sort, :ship_to_country, :selection_name, :is_active
        )
        ON CONFLICT(name) DO UPDATE SET
            keywords=excluded.keywords,
            category_id=excluded.category_id,
            min_price=excluded.min_price,
            max_price=excluded.max_price,
            price_currency=excluded.price_currency,
            sort=excluded.sort,
            ship_to_country=excluded.ship_to_country,
            selection_name=excluded.selection_name,
            is_active=excluded.is_active
        """,
        {
            "name": name,
            "keywords": keywords,
            "category_id": category_id,
            "min_price": min_price,
            "max_price": max_price,
            "price_currency": price_currency,
            "sort": sort,
            "ship_to_country": ship_to_country,
            "selection_name": selection_name,
            "is_active": 1 if is_active else 0,
        },
    )
    conn.commit()


def get_search_by_name(conn: sqlite3.Connection, name: str) -> Optional[SavedSearch]:
    row = conn.execute("SELECT * FROM searches WHERE name = ?", (name,)).fetchone()
    return _row_to_saved_search(row) if row else None


def load_active_searches(conn: sqlite3.Connection) -> List[SavedSearch]:
    rows = conn.execute("SELECT * FROM searches WHERE is_active = 1 ORDER BY id").fetchall()
    return [_row_to_saved_search(row) for row in rows]


def list_all_searches(conn: sqlite3.Connection) -> List[SavedSearch]:
    rows = conn.execute("SELECT * FROM searches ORDER BY id").fetchall()
    return [_row_to_saved_search(row) for row in rows]


def create_run(conn: sqlite3.Connection, *, mode: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs (mode, started_at) VALUES (?, ?)",
        (mode, now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    searches_executed: int,
    records_written: int,
    errors: List[dict],
) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, searches_executed = ?, records_written = ?, errors_json = ? WHERE id = ?",
        (now_iso(), searches_executed, records_written, json.dumps(errors), run_id),
    )
    conn.commit()


_PRODUCT_COLUMNS = (
    "product_id",
    "product_title",
    "product_url",
    "product_main_image_url",
    "product_small_image_urls",
    "product_video_url",
    "category_id",
    "sale_price",
    "sale_price_currency",
    "original_price",
    "original_price_currency",
    "target_sale_price",
    "target_sale_price_currency",
    "discount",
    "evaluate_rate",
    "review_count",
    "avg_rating",
    "sales_volume",
    "sales_volume_display",
)

_OBSERVATION_COLUMNS = (
    "sale_price",
    "sale_price_currency",
    "original_price",
    "original_price_currency",
    "target_sale_price",
    "target_sale_price_currency",
    "discount",
    "evaluate_rate",
    "review_count",
    "avg_rating",
    "sales_volume",
    "sales_volume_display",
)


def upsert_product_and_observation(
    conn: sqlite3.Connection,
    product: NormalizedProduct,
    *,
    run_id: int,
    search_id: Optional[int],
    captured_at: str,
) -> None:
    values = {col: getattr(product, col) for col in _PRODUCT_COLUMNS}
    values["product_small_image_urls"] = json.dumps(product.product_small_image_urls)
    values["captured_at"] = captured_at
    values["run_id"] = run_id

    product_set_clause = ",\n            ".join(
        f"{col}=excluded.{col}" for col in _PRODUCT_COLUMNS if col != "product_id"
    )
    conn.execute(
        f"""
        INSERT INTO products (
            {", ".join(_PRODUCT_COLUMNS)}, first_seen_at, last_seen_at, last_run_id
        ) VALUES (
            {", ".join(f":{col}" for col in _PRODUCT_COLUMNS)}, :captured_at, :captured_at, :run_id
        )
        ON CONFLICT(product_id) DO UPDATE SET
            {product_set_clause},
            last_seen_at=excluded.last_seen_at,
            last_run_id=excluded.last_run_id
        """,
        values,
    )
    # first_seen_at is deliberately absent from the UPDATE SET above, so a
    # product already on file keeps the timestamp of its first collection.

    observation_values = {col: getattr(product, col) for col in _OBSERVATION_COLUMNS}
    observation_values.update(
        product_id=product.product_id,
        run_id=run_id,
        search_id=search_id,
        captured_at=captured_at,
    )
    observation_set_clause = ",\n            ".join(f"{col}=excluded.{col}" for col in _OBSERVATION_COLUMNS)
    conn.execute(
        f"""
        INSERT INTO observations (
            product_id, run_id, search_id, captured_at, {", ".join(_OBSERVATION_COLUMNS)}
        ) VALUES (
            :product_id, :run_id, :search_id, :captured_at, {", ".join(f":{col}" for col in _OBSERVATION_COLUMNS)}
        )
        ON CONFLICT(product_id, run_id) DO UPDATE SET
            search_id=excluded.search_id,
            captured_at=excluded.captured_at,
            {observation_set_clause}
        """,
        observation_values,
    )
