import pandas as pd
import pytest

from aliexpress_dashboard.dashboard.scoring import ScoreWeights, compute_composite_score


def _df(rows):
    return pd.DataFrame(rows)


def test_compute_composite_score_empty_df():
    assert compute_composite_score(pd.DataFrame(), ScoreWeights()).empty


def test_compute_composite_score_all_weights_zero_returns_none():
    df = _df([{"sales_volume": 10, "evaluate_rate": 90, "review_count": 5, "target_sale_price": 10}])
    result = compute_composite_score(df, ScoreWeights(volume=0, rating=0, review_count=0, price_fit=0))
    assert result.isna().all()


def test_compute_composite_score_single_row_is_neutral_fifty():
    df = _df([{"sales_volume": 10, "evaluate_rate": 90, "review_count": 5, "target_sale_price": 10}])
    result = compute_composite_score(df, ScoreWeights())
    assert result.iloc[0] == pytest.approx(50.0)


def test_compute_composite_score_ranks_higher_volume_higher():
    df = _df(
        [
            {"sales_volume": 0, "evaluate_rate": 90, "review_count": 5, "target_sale_price": 10},
            {"sales_volume": 1000, "evaluate_rate": 90, "review_count": 5, "target_sale_price": 10},
        ]
    )
    result = compute_composite_score(df, ScoreWeights(volume=100, rating=0, review_count=0, price_fit=0))
    assert result.iloc[1] > result.iloc[0]


def test_compute_composite_score_price_fit_rewards_cheaper():
    df = _df(
        [
            {"sales_volume": 10, "evaluate_rate": 90, "review_count": 5, "target_sale_price": 100},
            {"sales_volume": 10, "evaluate_rate": 90, "review_count": 5, "target_sale_price": 5},
        ]
    )
    result = compute_composite_score(df, ScoreWeights(volume=0, rating=0, review_count=0, price_fit=100))
    assert result.iloc[1] > result.iloc[0]


def test_compute_composite_score_missing_rating_scores_as_worst():
    df = _df(
        [
            {"sales_volume": 10, "evaluate_rate": None, "review_count": 5, "target_sale_price": 10},
            {"sales_volume": 10, "evaluate_rate": 95, "review_count": 5, "target_sale_price": 10},
        ]
    )
    result = compute_composite_score(df, ScoreWeights(volume=0, rating=100, review_count=0, price_fit=0))
    assert result.iloc[0] < result.iloc[1]


def test_score_weights_total_property():
    assert ScoreWeights(volume=10, rating=20, review_count=30, price_fit=40).total == 100
