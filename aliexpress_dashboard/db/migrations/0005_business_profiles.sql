-- Multi-tenant business-plan onboarding. Keyed by Firebase email (the
-- only user identity this app has -- see spa/security.py), not a
-- separate users table, since nothing else about a "user" is tracked.
CREATE TABLE IF NOT EXISTS business_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL UNIQUE,
    seller_type TEXT,
    product_niche TEXT,
    target_market TEXT,
    sales_channels TEXT,        -- JSON array, same convention as products.category_ancestor_ids
    marketing_approach TEXT,    -- JSON array
    budget_stage TEXT,
    experience_level TEXT,
    primary_category_id INTEGER REFERENCES categories(category_id),
    summary TEXT,                -- LLM-written plain-English summary, shown back to the user for review
    status TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | complete
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Raw wizard/conversation transcript. Not read by v1's fixed-wizard flow
-- (which sends all answers in one synthesize call), but cheap to have in
-- place before Phase 2 makes the flow conversational/adaptive, when it
-- becomes necessary for multi-turn context.
CREATE TABLE IF NOT EXISTS onboarding_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES business_profiles(id) ON DELETE CASCADE,
    role TEXT NOT NULL,         -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per calendar month, updated after every LLM call, checked
-- before the next one -- see dashboard/llm_usage.py. Tracks actual USD
-- cost (computed from token counts at call time), not just token
-- counts, since the hard monthly cap is a dollar figure.
CREATE TABLE IF NOT EXISTS llm_usage (
    month TEXT PRIMARY KEY,     -- 'YYYY-MM'
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
