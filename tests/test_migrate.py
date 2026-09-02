import sqlite3

import pytest

from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations


def test_migrations_apply_cleanly(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    applied = run_migrations(conn)
    assert applied == ["0001_initial.sql", "0002_shortlists.sql"]

    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"searches", "runs", "products", "observations", "shortlists", "shortlist_items"} <= tables


def test_migrations_are_idempotent(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)
    second_pass = run_migrations(conn)
    assert second_pass == []


def test_observations_unique_per_product_and_run(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn)

    conn.execute(
        "INSERT INTO runs (id, mode, started_at) VALUES (1, 'fixture', datetime('now'))"
    )
    conn.execute(
        """
        INSERT INTO products (product_id, first_seen_at, last_seen_at)
        VALUES (1001, datetime('now'), datetime('now'))
        """
    )
    conn.execute(
        "INSERT INTO observations (product_id, run_id, captured_at) VALUES (1001, 1, datetime('now'))"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO observations (product_id, run_id, captured_at) VALUES (1001, 1, datetime('now'))"
        )
