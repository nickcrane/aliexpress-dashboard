import pandas as pd
import pytest

from aliexpress_dashboard.dashboard.momentum import compute_momentum

BASE = pd.Timestamp("2026-09-02")


def _obs(product_id, days_ago, volume):
    return {"product_id": product_id, "captured_at": BASE - pd.Timedelta(days=days_ago), "sales_volume": volume}


def test_compute_momentum_empty_input():
    result = compute_momentum(pd.DataFrame(columns=["product_id", "captured_at", "sales_volume"]))
    assert result.empty


def test_compute_momentum_single_observation_has_no_change():
    df = pd.DataFrame([_obs(1, 0, 100)])
    row = compute_momentum(df).iloc[0]
    assert row["latest_volume"] == 100
    assert row["previous_volume"] is None
    assert row["volume_change"] is None
    assert row["volume_change_pct"] is None


def test_compute_momentum_last_run_change():
    df = pd.DataFrame([_obs(1, 5, 100), _obs(1, 0, 150)])
    row = compute_momentum(df).iloc[0]
    assert row["previous_volume"] == 100
    assert row["latest_volume"] == 150
    assert row["volume_change"] == 50
    assert row["volume_change_pct"] == pytest.approx(50.0)


def test_compute_momentum_zero_previous_volume_avoids_division_by_zero():
    df = pd.DataFrame([_obs(1, 5, 0), _obs(1, 0, 20)])
    row = compute_momentum(df).iloc[0]
    assert row["volume_change"] == 20
    assert row["volume_change_pct"] is None


def test_compute_momentum_window_uses_oldest_point_within_window():
    df = pd.DataFrame(
        [
            _obs(1, 30, 10),  # outside a 14-day window
            _obs(1, 10, 50),  # oldest point inside the window
            _obs(1, 5, 80),
            _obs(1, 0, 100),  # latest
        ]
    )
    row = compute_momentum(df, window_days=14).iloc[0]
    assert row["latest_volume"] == 100
    assert row["window_start_volume"] == 50
    assert row["window_volume_change"] == 50


def test_compute_momentum_window_with_only_latest_point_is_none():
    df = pd.DataFrame([_obs(1, 30, 10), _obs(1, 0, 100)])
    row = compute_momentum(df, window_days=14).iloc[0]
    assert row["window_start_volume"] is None
    assert row["window_volume_change"] is None


def test_compute_momentum_handles_multiple_products_independently():
    df = pd.DataFrame([_obs(1, 5, 100), _obs(1, 0, 150), _obs(2, 0, 999)])
    result = compute_momentum(df)
    assert set(result["product_id"]) == {1, 2}
    product_2 = result[result["product_id"] == 2].iloc[0]
    # Mixed with product 1's real float previous_volume, pandas coerces this
    # column to float64, so the missing value comes back as NaN, not None.
    assert pd.isna(product_2["previous_volume"])
