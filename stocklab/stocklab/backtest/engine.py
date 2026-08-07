"""Vectorized cost-aware portfolio backtest.

Timing (matches the label contract exactly):
  scores dated t -> target weights formed from date-t cross-section
  -> executed at close(t+1) -> first P&L accrues on day t+2's return.

Portfolio: top-quantile long / bottom-quantile short, equal weight within leg,
held `horizon` days via overlapping tranches (1/horizon of capital re-formed
daily). Tranche overlap is the turnover-damping device: daily turnover is
~2/horizon of gross, not 200%.

Costs are charged on traded notional: cost_bps per unit of |weight change|
(each unit of |dw| is one side of one trade). Gross results are never reported
without the cost grid next to them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .metrics import perf_stats


@dataclass
class BacktestResult:
    name: str
    daily: pd.DataFrame = field(repr=False)   # net_ret, gross_ret, cost, turnover, long_ret, short_ret
    stats_net: dict = field(default_factory=dict)
    stats_gross: dict = field(default_factory=dict)
    stats_by_cost: dict = field(default_factory=dict)     # cost_bps -> perf stats
    leg_stats: dict = field(default_factory=dict)         # 'long'/'short' -> perf stats
    by_year: dict = field(default_factory=dict)           # year -> net perf stats
    avg_daily_turnover: float = 0.0
    breakeven_cost_bps: float = np.nan

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "stats_net": self.stats_net,
            "stats_gross": self.stats_gross,
            "stats_by_cost": self.stats_by_cost,
            "leg_stats": self.leg_stats,
            "by_year": self.by_year,
            "avg_daily_turnover": self.avg_daily_turnover,
            "breakeven_cost_bps": self.breakeven_cost_bps,
        }


def _target_weights(
    scores: pd.DataFrame,
    n_quantiles: int,
    long_only: bool = False,
) -> pd.DataFrame:
    """Per-date target weights from a wide score frame (date x ticker).

    Long leg: top quantile, +1/n each (sums to +1).
    Short leg: bottom quantile, -1/n each (sums to -1). Dollar-neutral.
    """
    ranks = scores.rank(axis=1, pct=True)
    n_names = scores.notna().sum(axis=1)
    w = pd.DataFrame(0.0, index=scores.index, columns=scores.columns)

    top = ranks.ge(1.0 - 1.0 / n_quantiles)
    n_top = top.sum(axis=1).replace(0, np.nan)
    w = w.mask(top, 1.0, axis=0).div(1.0, axis=0)
    w = w.where(~top, top.div(n_top, axis=0))

    if not long_only:
        bot = ranks.le(1.0 / n_quantiles)
        n_bot = bot.sum(axis=1).replace(0, np.nan)
        w = w.where(~bot, -bot.div(n_bot, axis=0))

    # dates with too few names -> no positions
    w[n_names < 3 * n_quantiles] = 0.0
    return w.fillna(0.0)


def backtest_long_short(
    name: str,
    scores: pd.Series,             # (date, ticker) OOS model scores
    close: pd.DataFrame,           # wide close prices (full panel)
    horizon: int = 5,
    lag: int = 1,
    n_quantiles: int = 10,
    cost_bps: float = 10.0,
    cost_grid: tuple = (0.0, 5.0, 10.0, 25.0),
    long_only: bool = False,
    ann_factor: int = 252,
) -> BacktestResult:
    scores_w = scores.unstack("ticker").reindex(columns=close.columns)
    scores_w = scores_w.reindex(close.index)   # align to full trading grid

    w_target = _target_weights(scores_w, n_quantiles, long_only=long_only)

    # overlapping tranches: held weights on day d average the last `horizon`
    # signals, executed with `lag`; first P&L day for signal t is t+lag+1.
    w_eff = w_target.rolling(horizon, min_periods=1).mean().shift(lag + 1)
    w_eff = w_eff.fillna(0.0)

    ret1 = close.pct_change().fillna(0.0)
    gross = (w_eff * ret1).sum(axis=1)

    dw = w_eff.diff().abs().sum(axis=1)
    active = w_eff.abs().sum(axis=1) > 0
    # restrict to the active period (post first signal)
    if active.any():
        first = active.idxmax()
        gross = gross.loc[first:]
        dw = dw.loc[first:]
    cost = dw * (cost_bps / 1e4)
    net = gross - cost

    w_long = w_eff.clip(lower=0.0)
    w_short = w_eff.clip(upper=0.0)
    long_ret = (w_long * ret1).sum(axis=1).loc[gross.index]
    short_ret = (w_short * ret1).sum(axis=1).loc[gross.index]

    daily = pd.DataFrame({
        "gross_ret": gross, "net_ret": net, "cost": cost, "turnover": dw,
        "long_ret": long_ret, "short_ret": short_ret,
    })

    stats_by_cost = {}
    for cb in cost_grid:
        stats_by_cost[float(cb)] = perf_stats(gross - dw * (cb / 1e4), ann_factor)

    avg_to = float(dw.mean())
    mean_gross_daily = float(gross.mean())
    breakeven = (mean_gross_daily / avg_to * 1e4) if avg_to > 1e-9 else np.nan

    by_year = {}
    for year, r in net.groupby(net.index.year):
        if len(r) >= 40:
            s = perf_stats(r, ann_factor)
            by_year[int(year)] = {k: s[k] for k in ("ann_return", "sharpe", "max_drawdown") if k in s}

    return BacktestResult(
        name=name,
        daily=daily,
        stats_net=perf_stats(net, ann_factor),
        stats_gross=perf_stats(gross, ann_factor),
        stats_by_cost=stats_by_cost,
        leg_stats={
            "long": perf_stats(long_ret, ann_factor),
            "short": perf_stats(short_ret, ann_factor),
        },
        by_year=by_year,
        avg_daily_turnover=avg_to,
        breakeven_cost_bps=float(breakeven),
    )
