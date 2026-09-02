from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass
class ShortlistSummary:
    id: int
    name: str
    created_at: str
    item_count: int


def get_or_create_shortlist(conn: sqlite3.Connection, name: str) -> int:
    conn.execute("INSERT INTO shortlists (name) VALUES (?) ON CONFLICT(name) DO NOTHING", (name,))
    conn.commit()
    row = conn.execute("SELECT id FROM shortlists WHERE name = ?", (name,)).fetchone()
    return row["id"]


def add_products_to_shortlist(conn: sqlite3.Connection, shortlist_id: int, product_ids: List[int]) -> None:
    if not product_ids:
        return
    conn.executemany(
        "INSERT OR IGNORE INTO shortlist_items (shortlist_id, product_id) VALUES (?, ?)",
        [(shortlist_id, product_id) for product_id in product_ids],
    )
    conn.commit()


def remove_product_from_shortlist(conn: sqlite3.Connection, shortlist_id: int, product_id: int) -> None:
    conn.execute(
        "DELETE FROM shortlist_items WHERE shortlist_id = ? AND product_id = ?",
        (shortlist_id, product_id),
    )
    conn.commit()


def delete_shortlist(conn: sqlite3.Connection, shortlist_id: int) -> None:
    conn.execute("DELETE FROM shortlist_items WHERE shortlist_id = ?", (shortlist_id,))
    conn.execute("DELETE FROM shortlists WHERE id = ?", (shortlist_id,))
    conn.commit()


def list_shortlists(conn: sqlite3.Connection) -> List[ShortlistSummary]:
    rows = conn.execute(
        """
        SELECT s.id, s.name, s.created_at, COUNT(si.product_id) AS item_count
        FROM shortlists s
        LEFT JOIN shortlist_items si ON si.shortlist_id = s.id
        GROUP BY s.id
        ORDER BY s.created_at DESC
        """
    ).fetchall()
    return [
        ShortlistSummary(id=row["id"], name=row["name"], created_at=row["created_at"], item_count=row["item_count"])
        for row in rows
    ]


def load_shortlist_products(conn: sqlite3.Connection, shortlist_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            p.product_id,
            p.product_title,
            p.product_main_image_url,
            p.product_url,
            p.target_sale_price,
            p.target_sale_price_currency,
            p.evaluate_rate,
            p.review_count,
            p.avg_rating,
            p.sales_volume,
            p.discount,
            si.added_at
        FROM shortlist_items si
        JOIN products p ON p.product_id = si.product_id
        WHERE si.shortlist_id = :shortlist_id
        ORDER BY si.added_at DESC
        """,
        conn,
        params={"shortlist_id": shortlist_id},
    )
