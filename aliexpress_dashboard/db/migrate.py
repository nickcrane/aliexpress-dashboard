from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    _ensure_migrations_table(conn)
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {row["filename"] for row in rows}


def pending_migrations(conn: sqlite3.Connection) -> list[Path]:
    already_applied = applied_migrations(conn)
    all_migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [path for path in all_migrations if path.name not in already_applied]


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Applies pending migrations in filename order. Returns the filenames applied."""
    applied = []
    for path in pending_migrations(conn):
        conn.executescript(path.read_text())
        conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
        conn.commit()
        applied.append(path.name)
    return applied
