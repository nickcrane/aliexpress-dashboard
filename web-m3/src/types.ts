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

export interface CategoryOption {
  category_id: number;
  category_name: string | null;
  category_path: string | null;
}

export interface FilterOptions {
  categories: CategoryOption[];
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
