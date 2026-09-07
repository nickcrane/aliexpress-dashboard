-- Full AliExpress category tree (id -> name/parent), populated by
-- collector/cli.py's sync-categories command (or POST /sync-categories) --
-- see AliClient.get_categories(). Independent of the products table since
-- categories change far less often than collected product data; a
-- product row's category_id may reference a category not yet in this
-- table if sync hasn't run yet (dashboard/categories.py falls back
-- gracefully in that case).
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL,
    parent_category_id INTEGER
);
