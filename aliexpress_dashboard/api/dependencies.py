"""Shared FastAPI dependencies for the data-serving routes in app.py."""

from __future__ import annotations

import sqlite3
from typing import Iterator

from fastapi import Depends

from ..config import Settings, get_settings
from ..db.connection import get_connection
from ..db.migrate import run_migrations


def get_db_connection(settings: Settings = Depends(get_settings)) -> Iterator[sqlite3.Connection]:
    conn = get_connection(settings.db_path)
    run_migrations(conn)
    try:
        yield conn
    finally:
        conn.close()
