"""Vectorized cost-aware portfolio backtest.

Timing (matches the label contract exactly):
  scores dated t -> target weights formed from date-t cross-section
  -> executed at close(t+1) -> first P&L accrues on day t+2's return.

Portfolio: top-bucket long / bottom-bucket short, exactly n//q names per leg
(ordinal ranks, deterministic under ties), equal weight within leg, held
`horizon` days via overlapping tranches (1/horizon of capital re-formed
daily). Tranche overlap is the turnover-damping device.

Accounting conventions (explicit, because silent conventions are how
backtests lie):
* Returns are quoted per unit of SINGLE-LEG notional: $1 long + $1 short =
  gross exposure 2.0. Sharpe is leverage-invariant; annual returns are not —
  do not compare them to a fund's return on gross/2 without halving.
* Costs: cost_bps per unit of |weight change| (each unit of |dw| is one side
  of one trade). The initial build and the terminal unwind are both charged.
* A name whose close is missing on day d (halt/delisting/gap) cannot be held
  through d: its weight is forced to zero (exit cost charged) and re-entered
  only when it trades again. The count of such forced exits is reported —
  on survivor-biased data these events are rare precisely because the biased
  vendor removed them, which is part of why survivor-biased results flatter.
* The reported window is trimmed to [first active day, last active day]; the
  terminal unwind is charged on the last active day. Dead-capital zeros
  outside that window never dilute the statistics.
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
    forced_exit_days: int = 0        # held-name days zeroed because close was missing
    neutrality_violation_days: int = 0

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
            "forced_exit_days": self.forced_exit_days,
            "neutrality_violation_days": self.neutrality_violation_days,
        }


def _target_weights(
    scores: pd.DataFrame,
    n_quantiles: int,
    long_only: bool = False,
) -> pd.DataFrame:
    """Per-date target weights from a wide score frame (date x ticker).

    Exactly n_names//n_quantiles names per leg, chosen by ordinal rank
    (method='first': ties broken deterministically by column order — a tie
    group can never silently empty a leg, an earlier bug class caught in
    review). Long leg sums to +1; short leg to -1 (dollar-neutral).
    Dates with fewer than 3*n_quantiles names take no positions.
    """
    n_names = scores.notna().sum(axis=1)
    r = scores.rank(axis=1, method="first")           # ordinal 1..n, NaN stays NaN
    n_leg = (n_names // n_quantiles).clip(lower=1)

    top = r.gt(n_names - n_leg, axis=0)
    w = top.astype(float).div(top.sum(axis=1).replace(0, np.nan), axis=0)
    if not long_only:
        bot = r.le(n_leg, axis=0)
        w = w.sub(bot.astype(float).div(bot.sum(axis=1).replace(0, np.nan), axis=0))

    w = w.fillna(0.0)
    w[n_names < 3 * n_quantiles] = 0.0
    return w


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
    score_dates = scores.index.get_level_values("date").unique()
    missing_dates = score_dates.difference(close.index)
    if len(missing_dates) > 0:
        raise ValueError(
            f"{len(missing_dates)} score dates missing from the price index "
            f"(first: {missing_dates[0]}) — align scores to the trading grid first"
        )

    scores_w = scores.unstack("ticker").reindex(columns=close.columns)
    scores_w = scores_w.reindex(close.index)   # align to full trading grid

    w_target = _target_weights(scores_w, n_quantiles, long_only=long_only)

    # overlapping tranches: day d holds the mean of the last `horizon` target
    # weight vectors, executed with `lag`; signal t first earns P&L on day
    # t+lag+1. Fixed divisor (not min_periods mean) => the book ramps in
    # 1/horizon steps instead of deploying full capital into one tranche.
    w_eff = w_target.rolling(horizon, min_periods=1).sum().div(horizon)
    w_eff = w_eff.shift(lag + 1).fillna(0.0)

    # a name with no printed close today cannot be held today: force exit
    # (cost charged via dw); re-entry only when it trades again. Same for the
    # first day back after a gap (its gap return is unknowable).
    tradable = close.notna() & close.shift(1).notna()
    would_hold = w_eff.ne(0.0)
    forced_exit_days = int((would_hold & ~tradable).sum().sum())
    w_eff = w_eff.where(tradable, 0.0)

    # neutrality guard: if forced exits skewed a day's book, note it
    if not long_only:
        net_exp = w_eff.sum(axis=1)
        gross_exp = w_eff.abs().sum(axis=1)
        neutrality_violation_days = int(((net_exp.abs() > 0.05) & (gross_exp > 0)).sum())
    else:
        neutrality_violation_days = 0

    # explicit ffill = the old pad default, kept deliberately: a held position
    # with no print marks flat until the next real price (the missing-price
    # forced-exit logic handles true disappearances); pandas 3 drops the
    # implicit pad, so spell it out
    ret1 = close.ffill().pct_change(fill_method=None)
    gross_full = w_eff.mul(ret1.fillna(0.0)).sum(axis=1)
    dw_full = w_eff.diff().abs().sum(axis=1)

    active = w_eff.abs().sum(axis=1) > 0
    if not active.any():
        raise ValueError("no active positions — scores produced an empty book")
    first = active.idxmax()
    last = active[::-1].idxmax()
    gross = gross_full.loc[first:last]
    dw = dw_full.loc[first:last].copy()
    # terminal unwind: liquidate the last day's book (symmetric with the
    # initial build, which diff() already charges at `first`)
    dw.loc[last] += float(w_eff.loc[last].abs().sum())

    cost = dw * (cost_bps / 1e4)
    net = gross - cost

    w_long = w_eff.clip(lower=0.0)
    w_short = w_eff.clip(upper=0.0)
    long_ret = w_long.mul(ret1.fillna(0.0)).sum(axis=1).loc[first:last]
    short_ret = w_short.mul(ret1.fillna(0.0)).sum(axis=1).loc[first:last]

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
        forced_exit_days=forced_exit_days,
        neutrality_violation_days=neutrality_violation_days,
    )
