// Mirrors aliexpress_dashboard/dashboard/scoring.py's compute_composite_score
// exactly (same min-max normalization, same NaN-poisons-the-row semantics
// for a missing price), reimplemented client-side since there's no Python
// process in this app.
import type { Product, ScoreWeights } from "./types";

function minmaxNormalize(values: (number | null)[]): (number | null)[] {
  const present = values.filter((v): v is number => v !== null && !Number.isNaN(v));
  if (present.length === 0) {
    return values.map(() => 0.5);
  }
  const min = Math.min(...present);
  const max = Math.max(...present);
  if (min === max) {
    return values.map(() => 0.5);
  }
  return values.map((v) => (v === null || Number.isNaN(v) ? null : (v - min) / (max - min)));
}

export function computeCompositeScore(products: Product[], weights: ScoreWeights): (number | null)[] {
  if (products.length === 0) return [];
  const total = weights.volume + weights.rating + weights.review_count + weights.price_fit;
  if (total <= 0) return products.map(() => null);

  const volumeScore = minmaxNormalize(products.map((p) => p.sales_volume ?? 0));
  const ratingScore = minmaxNormalize(products.map((p) => p.evaluate_rate ?? 0));
  const reviewCountScore = minmaxNormalize(products.map((p) => p.review_count ?? 0));
  const priceFitScore = minmaxNormalize(products.map((p) => p.target_sale_price)).map((v) =>
    v === null ? null : 1 - v,
  );

  return products.map((_, i) => {
    const terms = [
      [weights.volume, volumeScore[i]],
      [weights.rating, ratingScore[i]],
      [weights.review_count, reviewCountScore[i]],
      [weights.price_fit, priceFitScore[i]],
    ] as const;
    if (terms.some(([, score]) => score === null)) return null;
    const blended = terms.reduce((sum, [w, score]) => sum + w * (score as number), 0) / total;
    return blended * 100;
  });
}
