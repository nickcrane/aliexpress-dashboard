"""Hard monthly spend cap for the onboarding LLM (Claude Haiku 4.5) --
checked before every call, updated after every call, so a runaway month
fails closed instead of producing a surprise bill. See
spa/app.py:onboarding routes for where this gets enforced.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

# claude-haiku-4-5, confirmed current pricing (USD per token, not per
# million) -- see aliexpress_dashboard/client/llm_client.py for the one
# call site this feeds. Update both together if the model changes.
INPUT_COST_PER_TOKEN = 1.00 / 1_000_000
OUTPUT_COST_PER_TOKEN = 5.00 / 1_000_000


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def current_month_cost_usd(conn: sqlite3.Connection) -> float:
    row = conn.execute("SELECT cost_usd FROM llm_usage WHERE month = ?", (current_month(),)).fetchone()
    return row["cost_usd"] if row else 0.0


def is_over_cap(conn: sqlite3.Connection, *, cap_usd: float) -> bool:
    return current_month_cost_usd(conn) >= cap_usd


def record_usage(conn: sqlite3.Connection, *, input_tokens: int, output_tokens: int) -> float:
    """Adds this call's cost to the current month's running total (creating
    the row if this is the month's first call). Returns the cost of just
    this call, in case a caller wants to log/display it."""
    cost = input_tokens * INPUT_COST_PER_TOKEN + output_tokens * OUTPUT_COST_PER_TOKEN
    conn.execute(
        """
        INSERT INTO llm_usage (month, input_tokens, output_tokens, cost_usd, updated_at)
        VALUES (:month, :input_tokens, :output_tokens, :cost_usd, datetime('now'))
        ON CONFLICT(month) DO UPDATE SET
            input_tokens = input_tokens + excluded.input_tokens,
            output_tokens = output_tokens + excluded.output_tokens,
            cost_usd = cost_usd + excluded.cost_usd,
            updated_at = datetime('now')
        """,
        {
            "month": current_month(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
        },
    )
    conn.commit()
    return cost
