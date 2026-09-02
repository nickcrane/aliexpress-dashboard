CREATE TABLE IF NOT EXISTS shortlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shortlist_items (
    shortlist_id INTEGER NOT NULL REFERENCES shortlists(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (shortlist_id, product_id)
);
