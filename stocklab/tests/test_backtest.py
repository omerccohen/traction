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


def test_scripted_lifecycle_turnover_exact():
    """Independently hand-computed turnover for a scripted scenario.

    9 tickers, 3 quantiles (3 per leg), horizon=1, lag=1, constant prices.
    Scores constant for 10 days, then leg-reversing flip, then end.
      initial build:            |dw| = 2.0   (long 1 + short 1)
      flip day (both legs swap): |dw| = 4.0
      terminal unwind:          |dw| = 2.0
      every other day:          |dw| = 0.0   -> lifecycle total = 8.0
    (The old test derived cost from the engine's own identity — circular,
    review finding F14. This one pins the number from outside.)
    """
    dates = pd.bdate_range("2020-01-01", periods=40)
    tickers = [f"T{i}" for i in range(9)]
    close = pd.DataFrame(100.0, index=dates, columns=tickers)
    base = np.array([9, 8, 7, 6, 5, 4, 3, 2, 1], dtype=float)
    scores_wide = pd.DataFrame(np.nan, index=dates, columns=tickers)
    for i in range(0, 10):
        scores_wide.iloc[i] = base
    for i in range(10, 20):
        scores_wide.iloc[i] = -base
    s = scores_wide.stack()
    s.index.names = ["date", "ticker"]

    bt = backtest_long_short("scripted", s, close, horizon=1, lag=1,
                             n_quantiles=3, cost_bps=10.0)
    assert np.isclose(bt.daily["turnover"].sum(), 8.0, atol=1e-9)
    assert np.isclose(bt.daily["turnover"].max(), 4.0, atol=1e-9)
    # constant prices: gross exactly 0, net exactly -costs
    assert np.isclose(bt.daily["gross_ret"].abs().sum(), 0.0, atol=1e-12)
    assert np.isclose(bt.daily["net_ret"].sum(), -8.0 * 10.0 / 1e4, atol=1e-12)


def test_trailing_dead_capital_is_trimmed():
    """Scores ending early must not dilute stats with flat zeros (F1)."""
    panel = make_synthetic_market(n_days=400, n_tickers=40, seed=6)
    score_full = _score_series(panel, panel.close.pct_change(21))
    cut = panel.dates[200]
    score_cut = score_full[score_full.index.get_level_values("date") <= cut]
    bt = backtest_long_short("cut", score_cut, panel.close, horizon=5, lag=1, cost_bps=0.0)
    # active window ends ~ horizon+lag+1 days after the last signal, not at panel end
    assert bt.daily.index[-1] <= panel.dates[210]
    assert (bt.daily["gross_ret"].iloc[-3:] != 0).any() or bt.daily["turnover"].iloc[-1] > 0


def test_tied_scores_never_produce_one_sided_book():
    """Massive ties must not empty a leg (F2: ordinal ranks fix)."""
    dates = pd.bdate_range("2020-01-01", periods=30)
    tickers = [f"T{i}" for i in range(40)]
    close = pd.DataFrame(100.0, index=dates, columns=tickers)
    vals = np.ones(40)          # 12-way tie at the top would break avg-rank buckets
    vals[:5] = 2.0
    vals[30:] = 0.5
    scores_wide = pd.DataFrame(np.tile(vals, (30, 1)), index=dates, columns=tickers)
    w = _target_weights(scores_wide, n_quantiles=10)
    row = w.iloc[10]
    assert np.isclose(row[row > 0].sum(), 1.0, atol=1e-9)
    assert np.isclose(row[row < 0].sum(), -1.0, atol=1e-9)
    assert (row > 0).sum() == 4 and (row < 0).sum() == 4   # exactly n//q per leg


def test_missing_price_forces_exit():
    """A held name whose close disappears must be force-exited, not held at
    a phantom 0% return (F3 — the engine-level survivorship subsidy)."""
    panel = make_synthetic_market(n_days=120, n_tickers=30, seed=9)
    close = panel.close.copy()
    victim = close.columns[0]
    # make victim top-ranked so it is held long, then delist it at day 60
    scores_wide = panel.close.pct_change(21)
    scores_wide[victim] = 10.0
    close.loc[close.index[60]:, victim] = np.nan
    s = scores_wide.stack()
    s.index.names = ["date", "ticker"]
    bt = backtest_long_short("delist", s, close, horizon=5, lag=1,
                             n_quantiles=5, cost_bps=0.0)
    assert bt.forced_exit_days > 0


def test_weights_are_dollar_neutral_and_leg_sized():
    panel = make_synthetic_market(n_days=120, n_tickers=50, seed=7)
    scores = panel.close.pct_change(21)
    w = _target_weights(scores, n_quantiles=5)
    row = w.iloc[90]
    assert np.isclose(row.sum(), 0.0, atol=1e-9)          # dollar neutral
    assert np.isclose(row[row > 0].sum(), 1.0, atol=1e-9)  # long leg = 100%
    assert np.isclose(row[row < 0].sum(), -1.0, atol=1e-9)


def test_no_positions_before_first_signal_plus_lag():
    """P&L must be exactly zero through signal+lag+0 and NONZERO at
    signal+lag+1 — pinned from both sides so a shift(lag) engine (same-close
    execution, the classic bug) fails this test (review finding F5)."""
    panel = make_synthetic_market(n_days=200, n_tickers=30, seed=8)
    scores_wide = panel.close.pct_change(21)
    scores_wide.iloc[:100] = np.nan  # signals only exist from day 100
    s = _score_series(panel, scores_wide)
    bt = backtest_long_short("late", s, panel.close, horizon=5, lag=1, cost_bps=0.0)
    # signal day 100, lag 1 -> executed close(101) -> first P&L on day 102
    early = bt.daily.loc[: panel.dates[101]]
    assert (early["gross_ret"].abs() < 1e-12).all(), "P&L before the executable day"
    assert abs(bt.daily.loc[panel.dates[102], "gross_ret"]) > 1e-12, (
        "no P&L on the first executable day — engine lag is off by one"
    )


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
