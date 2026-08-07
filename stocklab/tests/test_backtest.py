"""Backtest engine sanity: timing, costs, turnover accounting."""
import numpy as np
import pandas as pd

from stocklab.backtest.engine import backtest_long_short, _target_weights
from stocklab.backtest.metrics import newey_west_tstat, perf_stats, deflated_sharpe
from stocklab.data.synthetic import make_synthetic_market


def _score_series(panel, values_wide):
    s = values_wide.stack()
    s.index.names = ["date", "ticker"]
    return s


def test_perfect_foresight_makes_money_and_lag_matters():
    """A (deliberately cheating) score = future return must earn hugely with
    the engine's lag; that same score built on PAST returns must not."""
    panel = make_synthetic_market(n_days=300, n_tickers=40, seed=5)
    horizon, lag = 5, 1
    fwd = panel.close.shift(-(lag + horizon)) / panel.close.shift(-lag) - 1.0

    cheat = _score_series(panel, fwd.iloc[:-10])
    bt = backtest_long_short("cheat", cheat, panel.close, horizon=horizon, lag=lag,
                             n_quantiles=5, cost_bps=0.0)
    assert bt.stats_gross["sharpe"] > 3.0, "engine failed to reward true foresight"

    past = _score_series(panel, panel.close.pct_change(5))
    bt2 = backtest_long_short("past", past, panel.close, horizon=horizon, lag=lag,
                              n_quantiles=5, cost_bps=0.0)
    assert bt2.stats_gross["sharpe"] < bt.stats_gross["sharpe"] / 3


def test_costs_reduce_returns_by_turnover():
    panel = make_synthetic_market(n_days=300, n_tickers=40, seed=6)
    score = _score_series(panel, panel.close.pct_change(21))
    bt0 = backtest_long_short("c0", score, panel.close, cost_bps=0.0)
    bt25 = backtest_long_short("c25", score, panel.close, cost_bps=25.0)
    # identical gross, lower net
    assert np.isclose(bt0.stats_gross["ann_return"], bt25.stats_gross["ann_return"])
    expected_drag = bt25.daily["turnover"].mean() * 25 / 1e4 * 252
    actual_drag = bt25.stats_gross["ann_return"] - bt25.stats_net["ann_return"]
    assert np.isclose(actual_drag, expected_drag, rtol=0.05)


def test_weights_are_dollar_neutral_and_leg_sized():
    panel = make_synthetic_market(n_days=120, n_tickers=50, seed=7)
    scores = panel.close.pct_change(21)
    w = _target_weights(scores, n_quantiles=5)
    row = w.iloc[90]
    assert np.isclose(row.sum(), 0.0, atol=1e-9)          # dollar neutral
    assert np.isclose(row[row > 0].sum(), 1.0, atol=1e-9)  # long leg = 100%
    assert np.isclose(row[row < 0].sum(), -1.0, atol=1e-9)


def test_no_positions_before_first_signal_plus_lag():
    """P&L must be exactly zero until the first executable day."""
    panel = make_synthetic_market(n_days=200, n_tickers=30, seed=8)
    scores_wide = panel.close.pct_change(21)
    scores_wide.iloc[:100] = np.nan  # signals only exist from day 100
    s = _score_series(panel, scores_wide)
    bt = backtest_long_short("late", s, panel.close, horizon=5, lag=1, cost_bps=0.0)
    # first possible P&L day = signal day + lag + 1
    early = bt.daily.loc[: panel.dates[100]]
    assert (early["gross_ret"].abs() < 1e-12).all()


def test_newey_west_penalizes_autocorrelation():
    rng = np.random.default_rng(0)
    x = rng.normal(0.01, 0.1, 500)
    smooth = pd.Series(x).rolling(5).mean().dropna()  # overlapping -> autocorrelated
    iid = pd.Series(x[: len(smooth)])
    t_naive = smooth.mean() / (smooth.std() / np.sqrt(len(smooth)))
    t_nw = newey_west_tstat(smooth, lags=5)
    assert abs(t_nw) < abs(t_naive), "NW must shrink t-stats of autocorrelated series"


def test_deflated_sharpe_penalizes_trials():
    p1 = deflated_sharpe(1.0, n_obs=500, n_trials=1, sr_std_across_trials=0.5)
    p20 = deflated_sharpe(1.0, n_obs=500, n_trials=20, sr_std_across_trials=0.5)
    assert p20 < p1, "more trials must reduce DSR probability"
