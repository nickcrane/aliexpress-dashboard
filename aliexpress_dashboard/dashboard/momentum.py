"""Momentum: how sales_volume is moving over time, per the observations
history table. Two figures per product:

- last-run change: latest observation vs. the one immediately before it.
- window change: latest observation vs. the oldest observation still within
  the last `window_days` (i.e. "change over the last N days"), distinct from
  the last-run figure whenever more than one observation falls in that
  window.

Both are None when there isn't a second data point to compare against
(brand new product, or the window contains only the latest observation) --
never a crash, and never a fabricated number.
"""

from __future__ import annotations

import sqlite3
from typing import List

import pandas as pd


def load_observations_for_momentum(conn: sqlite3.Connection, product_ids: List[int]) -> pd.DataFrame:
    columns = ["product_id", "captured_at", "sales_volume"]
    if not product_ids:
        return pd.DataFrame(columns=columns)

    placeholders = ",".join("?" for _ in product_ids)
    return pd.read_sql_query(
        f"""
        SELECT product_id, captured_at, sales_volume
        FROM observations
        WHERE product_id IN ({placeholders})
        ORDER BY product_id, captured_at
        """,
        conn,
        params=product_ids,
        parse_dates=["captured_at"],
    )


def _change(latest, previous):
    if pd.isna(latest) or pd.isna(previous):
        return None
    return latest - previous


def _pct_change(latest, previous):
    if pd.isna(latest) or pd.isna(previous) or previous == 0:
        return None
    return (latest - previous) / previous * 100


def compute_momentum(observations: pd.DataFrame, *, window_days: int = 14) -> pd.DataFrame:
    columns = [
        "product_id",
        "latest_volume",
        "latest_captured_at",
        "previous_volume",
        "volume_change",
        "volume_change_pct",
        "window_start_volume",
        "window_volume_change",
        "window_volume_change_pct",
    ]
    if observations.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for product_id, group in observations.groupby("product_id"):
        group = group.sort_values("captured_at")
        latest = group.iloc[-1]
        previous = group.iloc[-2] if len(group) >= 2 else None

        window_cutoff = latest["captured_at"] - pd.Timedelta(days=window_days)
        in_window = group[group["captured_at"] >= window_cutoff]
        window_start = in_window.iloc[0] if len(in_window) >= 1 else None
        if window_start is not None and window_start["captured_at"] == latest["captured_at"]:
            window_start = None  # the window only contains the latest observation itself

        rows.append(
            {
                "product_id": product_id,
                "latest_volume": None if pd.isna(latest["sales_volume"]) else latest["sales_volume"],
                "latest_captured_at": latest["captured_at"],
                "previous_volume": (
                    None
                    if previous is None or pd.isna(previous["sales_volume"])
                    else previous["sales_volume"]
                ),
                "volume_change": _change(latest["sales_volume"], previous["sales_volume"])
                if previous is not None
                else None,
                "volume_change_pct": _pct_change(latest["sales_volume"], previous["sales_volume"])
                if previous is not None
                else None,
                "window_start_volume": (
                    None
                    if window_start is None or pd.isna(window_start["sales_volume"])
                    else window_start["sales_volume"]
                ),
                "window_volume_change": _change(latest["sales_volume"], window_start["sales_volume"])
                if window_start is not None
                else None,
                "window_volume_change_pct": _pct_change(latest["sales_volume"], window_start["sales_volume"])
                if window_start is not None
                else None,
            }
        )

    return pd.DataFrame(rows, columns=columns)
