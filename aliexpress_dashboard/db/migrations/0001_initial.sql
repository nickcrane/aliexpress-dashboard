-- Saved search definitions the collector runs, against aliexpress.ds.text.search.
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    keywords TEXT,
    category_id INTEGER,        -- a single ds.* category id; the API has no two-level category param
    min_price REAL,             -- major currency units (e.g. GBP pounds); ds.* prices are plain decimals, no minor-unit conversion needed
    max_price REAL,
    price_currency TEXT,        -- currency the price band above is denominated in
    sort TEXT,                  -- one of: min_price,asc|desc  orders,asc|desc  comments,asc|desc
    ship_to_country TEXT,       -- overrides the default ship-to country for this search; NULL = use the default
    selection_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per collector invocation.
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,                      -- 'fixture' or 'live'
    started_at TEXT NOT NULL,
    finished_at TEXT,
    searches_executed INTEGER NOT NULL DEFAULT 0,
    records_written INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT NOT NULL DEFAULT '[]'   -- JSON array of {"search_name": ..., "error": ...}
);

-- One row per product_id, holding its most recently observed attributes.
-- target_sale_price/target_sale_price_currency is the canonical price for
-- comparisons and scoring: target_currency is set once in the client config,
-- so that field is guaranteed uniform across every product regardless of the
-- currency a given listing's seller priced it in. sale_price/original_price
-- are kept alongside as the seller's/SKU's native-currency reference values.
--
-- evaluate_rate (positive-feedback %) is only ever populated from a search
-- result; review_count and avg_rating (1-5 stars) are only ever populated
-- from a per-product detail lookup (aliexpress.ds.product.get) -- getting
-- them is an extra API call per product, not a free column from browsing.
--
-- category_name has no source at all: neither ds.* endpoint this app calls
-- returns one, only category_id. It's left for a future join against
-- get_categories() (itself unverified -- see AliClient.get_categories) and
-- is not stored directly on the product.
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    product_title TEXT,
    product_url TEXT,
    product_main_image_url TEXT,
    product_small_image_urls TEXT,     -- JSON array
    product_video_url TEXT,
    category_id INTEGER,
    sale_price REAL,
    sale_price_currency TEXT,
    original_price REAL,
    original_price_currency TEXT,
    target_sale_price REAL,
    target_sale_price_currency TEXT,
    discount REAL,                     -- percent, e.g. 40.0 for 40%
    evaluate_rate REAL,                -- percent positive feedback; search results only
    review_count INTEGER,              -- detail lookups only
    avg_rating REAL,                   -- 1-5 scale; detail lookups only
    sales_volume INTEGER,              -- best-effort parsed; see sales_volume_display
    sales_volume_display TEXT,         -- raw text -- ds.* counts can be bucketed ("1000+"), not exact
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_run_id INTEGER REFERENCES runs(id)
);

-- One row per product per collection run. This is the history table the
-- momentum view and price sparklines are built from.
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    run_id INTEGER NOT NULL REFERENCES runs(id),
    search_id INTEGER REFERENCES searches(id),
    captured_at TEXT NOT NULL,
    sale_price REAL,
    sale_price_currency TEXT,
    original_price REAL,
    original_price_currency TEXT,
    target_sale_price REAL,
    target_sale_price_currency TEXT,
    discount REAL,
    evaluate_rate REAL,
    review_count INTEGER,
    avg_rating REAL,
    sales_volume INTEGER,
    sales_volume_display TEXT,
    -- Prevents a single run from writing two observation rows for the same
    -- product (e.g. the product matches two searches in one run, or a
    -- crashed run is resumed). The collector upserts on this key rather than
    -- inserting blindly. Running the collector twice in one calendar day is
    -- allowed and intentional -- it just adds a second, legitimate data point.
    UNIQUE (product_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_observations_product_captured
    ON observations (product_id, captured_at);

CREATE INDEX IF NOT EXISTS idx_products_category
    ON products (category_id);
