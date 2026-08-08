"""The gold-standard anti-lookahead test: features computed on data truncated
at date t must equal features computed on the full sample, at date t.

If any feature function peeks forward (centered windows, full-sample scalers,
backfills), this test fails.
"""
import numpy as np
import pandas as pd
import pytest

from stocklab.data.synthetic import make_synthetic_market
from stocklab.features.technical import compute_stock_features, compute_market_features
from stocklab.labels import forward_returns


@pytest.fixture(scope="module")
def panel():
    return make_synthetic_market(n_days=420, n_tickers=12, seed=3)


def test_stock_features_point_in_time(panel):
    t = panel.dates[400]
    full = compute_stock_features(panel)
    trunc = compute_stock_features(panel.truncate_before(t))
    for name, wide in full.items():
        a = wide.loc[t]
        b = trunc[name].loc[t]
        pd.testing.assert_series_equal(a, b, check_names=False, atol=1e-10, rtol=1e-8)


def test_market_features_point_in_time(panel):
    t = panel.dates[400]
    full = compute_market_features(panel)
    trunc = compute_market_features(panel.truncate_before(t))
    pd.testing.assert_series_equal(full.loc[t], trunc.loc[t], check_names=False, atol=1e-10, rtol=1e-8)


def test_label_timing_exact(panel):
    """label(t) must equal close(t+lag+horizon)/close(t+lag) - 1, verified by hand."""
    horizon, lag = 5, 1
    fwd = forward_returns(panel, horizon, lag)
    t_pos = 100
    t = panel.dates[t_pos]
    tk = panel.tickers[0]
    expected = (
        panel.close.iloc[t_pos + lag + horizon][tk] / panel.close.iloc[t_pos + lag][tk] - 1.0
    )
    assert np.isclose(fwd.loc[t, tk], expected)


def test_label_is_nan_at_tail(panel):
    horizon, lag = 5, 1
    fwd = forward_returns(panel, horizon, lag)
    assert fwd.iloc[-(horizon + lag):].isna().all().all()


# ---------------------------------------------------------------------------
# Dataset-level point-in-time test (review finding M1): the WHOLE feature
# assembly — eligibility mask, cross-sectional ranks, trailing z-scores,
# stacking — must be reproducible from truncated data, including on a panel
# with staggered listings (NaN heads), at multiple dates.
# ---------------------------------------------------------------------------

def _staggered_panel():
    from stocklab.data.panel import Panel
    p = make_synthetic_market(n_days=520, n_tickers=16, seed=13)
    close = p.close.copy()
    volume = p.volume.copy()
    for i, tkr in enumerate(close.columns):
        start = (i % 4) * 30            # listings staggered by 0/30/60/90 days
        if start:
            close.iloc[:start, i] = np.nan
            volume.iloc[:start, i] = np.nan
    return Panel(close=close, volume=volume)


def test_build_dataset_point_in_time():
    from stocklab.config import ExperimentConfig, UniverseConfig
    from stocklab.features.pipeline import build_dataset

    panel = _staggered_panel()
    cfg = ExperimentConfig(
        universe=UniverseConfig(min_history=280, min_price=0.0, min_dollar_volume=0.0)
    )
    full = build_dataset(panel, cfg)
    for pos in (470, 500, 519):
        t = panel.dates[pos]
        trunc = build_dataset(panel.truncate_before(t), cfg)
        a = full.X.xs(t, level="date")
        b = trunc.X.xs(t, level="date")
        common = a.index.intersection(b.index)
        assert len(common) > 0, f"no common tickers at {t}"
        pd.testing.assert_frame_equal(
            a.loc[common], b.loc[common], atol=1e-10, rtol=1e-8
        )


def test_build_dataset_point_in_time_with_liquidity_filters():
    """Same PIT property with the trailing price/liquidity screens active."""
    from stocklab.config import ExperimentConfig, UniverseConfig
    from stocklab.features.pipeline import build_dataset

    panel = _staggered_panel()
    cfg = ExperimentConfig(
        universe=UniverseConfig(min_history=280, min_price=5.0, min_dollar_volume=1e5)
    )
    full = build_dataset(panel, cfg)
    t = panel.dates[500]
    trunc = build_dataset(panel.truncate_before(t), cfg)
    a = full.X.xs(t, level="date")
    b = trunc.X.xs(t, level="date")
    common = a.index.intersection(b.index)
    assert len(common) > 0
    pd.testing.assert_frame_equal(a.loc[common], b.loc[common], atol=1e-10, rtol=1e-8)
