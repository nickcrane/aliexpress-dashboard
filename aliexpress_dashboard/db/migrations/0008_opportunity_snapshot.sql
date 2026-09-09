-- Two more onboarding-LLM outputs, saved alongside market_gap_analysis so
-- the plan view can show real numbers next to the niche/target-market
-- sentence without re-querying live data (which could drift from what
-- market_gap_analysis's prose describes -- see spa/app.py's onboarding
-- route) and a general, non-specific note on why the product could suit
-- TikTok Shop's format -- see llm_client.py for why this is deliberately
-- barred from naming real companies/creators/figures as fact.
ALTER TABLE business_profiles ADD COLUMN category_stats_snapshot TEXT;
ALTER TABLE business_profiles ADD COLUMN tiktok_shop_angle TEXT;
