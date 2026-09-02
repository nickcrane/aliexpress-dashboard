"""Composite suitability score: a weighted blend of sales volume, rating,
review count, and price-band fit, each min-max normalized to 0-1 within
the currently filtered/displayed set of products -- so "score" is always a
relative ranking among what you're looking at right now, not an absolute
number that means anything on its own.

review_count replaces commission_rate as the 4th input: the ds.* API family
has no commission concept at all (you're sourcing to fulfil your own orders,
not earning affiliate commission on someone else's) -- but it does have a
genuine review count on the per-product detail lookup, which the original
affiliate-based build never had. A higher review count is treated as more
evidence the sales history is real, not a fluke.

price-band fit is modeled as "cheaper is better within your filtered price
band" (1 - normalized price): a defensible default for a dropshipping
sourcing tool where lower cost of goods generally means better margin, but
it IS a modeling choice -- worth revisiting once real SKU-level cost data
(available on the detail lookup) is being collected, since actual margin
would be a more direct signal than raw price.

A missing rating or review count is scored as 0 (worst), not dropped or
averaged in -- consistent with never fabricating data for a product
AliExpress didn't return one for: it's genuinely unproven, and should rank
behind a product with a confirmed track record.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ScoreWeights:
    volume: float = 25.0
    rating: float = 25.0
    review_count: float = 25.0
    price_fit: float = 25.0

    @property
    def total(self) -> float:
        return self.volume + self.rating + self.review_count + self.price_fit


def _minmax_normalize(series: pd.Series) -> pd.Series:
    min_v, max_v = series.min(), series.max()
    if pd.isna(min_v) or pd.isna(max_v) or max_v == min_v:
        # No discriminating signal in this set (all equal, all missing, or a
        # single row) -- score everyone the same rather than dividing by zero.
        return pd.Series(0.5, index=series.index)
    return (series - min_v) / (max_v - min_v)


def compute_composite_score(df: pd.DataFrame, weights: ScoreWeights) -> pd.Series:
    """Returns a 0-100 score per row of df. df must have sales_volume,
    evaluate_rate, review_count, and target_sale_price columns."""
    if df.empty:
        return pd.Series(dtype="float64")

    if weights.total <= 0:
        return pd.Series(None, index=df.index, dtype="float64")

    volume_score = _minmax_normalize(df["sales_volume"].fillna(0))
    rating_score = _minmax_normalize(df["evaluate_rate"].fillna(0))
    review_count_score = _minmax_normalize(df["review_count"].fillna(0))
    price_fit_score = 1 - _minmax_normalize(df["target_sale_price"])

    blended = (
        weights.volume * volume_score
        + weights.rating * rating_score
        + weights.review_count * review_count_score
        + weights.price_fit * price_fit_score
    ) / weights.total

    return blended * 100
