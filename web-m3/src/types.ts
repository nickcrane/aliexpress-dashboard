// Mirrors the JSON shapes aliexpress_dashboard/api/app.py returns.

export interface Product {
  product_id: number;
  product_title: string;
  product_main_image_url: string | null;
  product_url: string;
  category_id: number | null;
  category_name: string | null;
  category_path: string | null;
  target_sale_price: number | null;
  target_sale_price_currency: string | null;
  discount: number | null;
  evaluate_rate: number | null;
  review_count: number | null;
  avg_rating: number | null;
  sales_volume: number | null;
  sales_volume_display: string | null;
  first_seen_at: string;
  last_seen_at: string;
  ship_to_country: string | null;
  score?: number;
}

export interface CategoryTreeChild {
  category_id: number;
  category_name: string;
}

export interface CategoryTreeNode {
  category_id: number;
  category_name: string;
  children: CategoryTreeChild[];
}

export interface FilterOptions {
  // Flat category list also exists on the API response but isn't used
  // by this app -- see the cascading picker built from category_tree.
  category_tree: CategoryTreeNode[];
  currencies: string[];
  ship_to_countries: string[];
}

export interface ProductFilters {
  category_id?: number;
  min_price?: number;
  max_price?: number;
  price_currency?: string;
  min_rating?: number;
  min_volume?: number;
  ship_to_country?: string;
}

export interface ScoreWeights {
  volume: number;
  rating: number;
  review_count: number;
  price_fit: number;
}

export interface MomentumRow {
  product_id: number;
  latest_volume: number | null;
  latest_captured_at: string | null;
  previous_volume: number | null;
  volume_change: number | null;
  volume_change_pct: number | null;
  window_start_volume: number | null;
  window_volume_change: number | null;
  window_volume_change_pct: number | null;
  product_title?: string;
  product_main_image_url?: string | null;
  product_url?: string;
}

export interface ShortlistSummary {
  id: number;
  name: string;
  created_at: string;
  item_count: number;
}

export interface CategoryPriceBand {
  price_low: number;
  price_high: number;
  product_count: number;
  avg_positive_feedback_pct: number | null;
  median_sales_volume: number | null;
}

// A frozen dashboard.queries.category_market_stats() result -- see
// BusinessProfile.category_stats_snapshot below.
export interface CategoryMarketStats {
  category_id: number;
  product_count: number;
  price_currency?: string | null;
  price_min?: number | null;
  price_median?: number | null;
  price_max?: number | null;
  avg_discount_pct?: number | null;
  avg_positive_feedback_pct?: number | null;
  median_sales_volume?: number | null;
  price_bands: CategoryPriceBand[];
}

export interface BusinessProfile {
  id: number;
  user_email: string;
  seller_type: string | null;
  product_niche: string | null;
  target_market: string | null;
  sales_channels: string[];
  marketing_approach: string[];
  budget_stage: string | null;
  experience_level: string | null;
  primary_category_id: number | null;
  summary: string | null;
  market_gap_analysis: string | null;
  // Frozen at the moment market_gap_analysis was written -- see
  // spa/app.py's onboarding route -- so the numbers shown next to that
  // prose never drift from what it actually describes.
  category_stats_snapshot: CategoryMarketStats | null;
  // General TikTok Shop content/commerce commentary -- deliberately never
  // cites real companies/creators/figures (no such data source is wired
  // up); see llm_client.py's system prompt.
  tiktok_shop_angle: string | null;
  status: "in_progress" | "complete";
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
