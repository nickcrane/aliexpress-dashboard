-- The onboarding LLM's written opportunity analysis for the plan's chosen
-- category (dashboard/queries.py:category_market_stats feeds the prompt;
-- see llm_client.py and spa/app.py's onboarding route), saved alongside
-- the rest of the plan so it's versioned the same way as everything else.
ALTER TABLE business_profiles ADD COLUMN market_gap_analysis TEXT;
