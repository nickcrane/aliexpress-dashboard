-- Business plans become versioned: a user can keep multiple saved plans
-- and switch which one is "active" (the one driving Products page
-- defaults), and edit a specific version in place rather than only ever
-- overwriting a single row -- see dashboard/business_profiles.py.
--
-- SQLite can't drop a UNIQUE constraint via ALTER TABLE, so this rebuilds
-- the table. Safe to disable FK checks for the duration: onboarding_messages
-- references business_profiles but nothing writes to it yet (reserved for
-- a future conversational onboarding phase), so there's no real data at risk.
PRAGMA foreign_keys = OFF;

CREATE TABLE business_profiles_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    seller_type TEXT,
    product_niche TEXT,
    target_market TEXT,
    sales_channels TEXT,
    marketing_approach TEXT,
    budget_stage TEXT,
    experience_level TEXT,
    primary_category_id INTEGER REFERENCES categories(category_id),
    summary TEXT,
    status TEXT NOT NULL DEFAULT 'in_progress',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Whatever existed under the old one-profile-per-user constraint becomes
-- that user's first version, and stays active.
INSERT INTO business_profiles_new (
    id, user_email, seller_type, product_niche, target_market, sales_channels,
    marketing_approach, budget_stage, experience_level, primary_category_id,
    summary, status, is_active, created_at, updated_at
)
SELECT
    id, user_email, seller_type, product_niche, target_market, sales_channels,
    marketing_approach, budget_stage, experience_level, primary_category_id,
    summary, status, 1, created_at, updated_at
FROM business_profiles;

DROP TABLE business_profiles;
ALTER TABLE business_profiles_new RENAME TO business_profiles;

CREATE INDEX IF NOT EXISTS idx_business_profiles_user_email ON business_profiles (user_email);

-- DB-enforced invariant: at most one active version per user. Application
-- code must clear the old active row before setting a new one active,
-- in the same transaction, or this rejects the write.
CREATE UNIQUE INDEX IF NOT EXISTS idx_business_profiles_one_active_per_user
    ON business_profiles (user_email) WHERE is_active = 1;

PRAGMA foreign_keys = ON;
