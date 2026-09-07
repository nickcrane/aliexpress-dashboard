from __future__ import annotations

import sqlite3
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: confirmed live in production -- FastAPI's
    # sync `Depends(..., yield)` dependency (api/dependencies.py) and a
    # sync route body can run on *different* anyio threadpool worker
    # threads for the same request, which sqlite3's default same-thread
    # check rejects outright ("SQLite objects created in a thread can
    # only be used in that same thread"). Safe here because each request
    # still only ever uses its own connection sequentially -- there's no
    # actual concurrent access to one connection from two threads at
    # once, just a same-request handoff across a thread boundary.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
