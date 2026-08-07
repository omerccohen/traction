"""Signal evaluation: the tear-sheet gate every model must pass
before it earns a portfolio backtest.

Primary metric: daily cross-sectional rank IC (Spearman correlation between
score and realized forward return). Because k-day labels overlap, the daily IC
series is autocorrelated — significance uses a Newey-West t-statistic with
lag = horizon. Realistic good values on daily equities are IC 0.02-0.06
(Qlib benchmark table); anything far above that is treated as evidence of a
bug, not brilliance.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats as sstats


# ---------------------------------------------------------------------------
# statistical machinery
# ---------------------------------------------------------------------------

def newey_west_tstat(series: pd.Series, lags: int) -> float:
    """t-stat of the mean of an autocorrelated series (HAC / Bartlett kernel).

    Overlapping k-day labels induce ~k-1 days of autocorrelation in the daily
    IC series; a naive t-stat overstates significance by ~sqrt(k).
    """
    x = series.dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 10:
        return np.nan
    mu = x.mean()
    e = x - mu
    gamma0 = float(e @ e) / n
    var = gamma0
    for l in range(1, min(lags, n - 1) + 1):
        w = 1.0 - l / (lags + 1.0)
        gamma = float(e[l:] @ e[:-l]) / n
        var += 2.0 * w * gamma
    se = np.sqrt(max(var, 1e-18) / n)
    return float(mu / se)


def deflated_sharpe(
    sr_ann: float,
    n_obs: int,
    n_trials: int,
    sr_std_across_trials: float,
    skew: float = 0.0,
    kurt: float = 3.0,
    ann_factor: int = 252,
) -> float:
    """Deflated Sharpe Ratio probability (Bailey & Lopez de Prado, 2014).

    Answers: given that `n_trials` strategy variants were evaluated, what is
    the probability that the observed Sharpe would exceed the expected maximum
    Sharpe of `n_trials` pure-noise strategies? Values < ~0.95 mean the result
    is indistinguishable from selection bias over noise.
    """
    if n_obs < 20 or not np.isfinite(sr_ann):
        return np.nan
    sr_daily = sr_ann / np.sqrt(ann_factor)
    n_trials = max(int(n_trials), 1)
    sr_std_daily = max(sr_std_across_trials / np.sqrt(ann_factor), 1e-9)

    if n_trials > 1:
        gamma = 0.5772156649
        z1 = sstats.norm.ppf(1.0 - 1.0 / n_trials)
        z2 = sstats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        sr0 = sr_std_daily * ((1.0 - gamma) * z1 + gamma * z2)
    else:
        sr0 = 0.0

    denom = np.sqrt(max(1.0 - skew * sr_daily + (kurt - 1.0) / 4.0 * sr_daily**2, 1e-9))
    z = (sr_daily - sr0) * np.sqrt(n_obs - 1) / denom
    return float(sstats.norm.cdf(z))


def _spearman_by_date(scores: pd.Series, fwd: pd.Series, min_names: int = 20) -> pd.Series:
    """Daily cross-sectional Spearman IC. Index of inputs: (date, ticker)."""
    df = pd.DataFrame({"s": scores, "f": fwd}).dropna()
    # rank within date, then Pearson of ranks == Spearman (fast, vectorized)
    g = df.groupby(level="date")
    n = g["s"].transform("size")
    df = df[n >= min_names]
    rs = df.groupby(level="date")["s"].rank()
    rf = df.groupby(level="date")["f"].rank()
    d = pd.DataFrame({"rs": rs, "rf": rf})
    ic = d.groupby(level="date").apply(
        lambda x: np.corrcoef(x["rs"], x["rf"])[0, 1] if len(x) > 2 else np.nan
    )
    ic.name = "rank_ic"
    return ic.dropna()


# ---------------------------------------------------------------------------
# tear sheet
# ---------------------------------------------------------------------------

@dataclass
class SignalReport:
    name: str
    ic_mean: float
    ic_std: float
    icir: float                    # ic_mean / ic_std (daily); annualized = icir*sqrt(252)
    ic_tstat_nw: float             # Newey-West t-stat, lag = horizon
    ic_positive_share: float       # fraction of days with IC > 0
    n_days: int
    quantile_returns: dict         # quantile -> mean fwd return (per period)
    monotonicity: float            # Spearman corr between quantile index and mean return
    top_bottom_spread: float       # Q_top - Q_bottom mean fwd return per period
    rank_autocorr_1d: float        # signal stability -> implied turnover/cost
    ic_by_horizon: dict = field(default_factory=dict)   # horizon -> mean rank IC
    ic_series: pd.Series = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "ic_series"}
        d["quantile_returns"] = {int(k): float(v) for k, v in self.quantile_returns.items()}
        d["ic_by_horizon"] = {int(k): float(v) for k, v in self.ic_by_horizon.items()}
        return d


def signal_report(
    name: str,
    scores: pd.Series,
    fwd_ret: pd.Series,
    horizon: int,
    n_quantiles: int = 10,
    extra_horizon_rets: dict | None = None,
) -> SignalReport:
    """Full signal tear sheet from out-of-sample scores and realized returns.

    `scores` and `fwd_ret` share a (date, ticker) MultiIndex. Rows with NaN in
    either are dropped (live rows have NaN fwd_ret and are excluded here).
    """
    df = pd.DataFrame({"s": scores, "f": fwd_ret}).dropna()
    if df.empty:
        raise ValueError("no overlapping scored+labeled rows")

    ic = _spearman_by_date(df["s"], df["f"])

    # quantile portfolio means (per-date buckets, then averaged over dates)
    def _q(x: pd.Series) -> pd.Series:
        try:
            return pd.qcut(x, n_quantiles, labels=False, duplicates="drop")
        except ValueError:
            return pd.Series(np.nan, index=x.index)

    q = df.groupby(level="date")["s"].transform(_q)
    qmeans = df.groupby([df.index.get_level_values("date"), q])["f"].mean()
    quantile_returns = qmeans.groupby(level=1).mean().to_dict()

    if len(quantile_returns) >= 3:
        ks = sorted(quantile_returns)
        mono = float(sstats.spearmanr(ks, [quantile_returns[k] for k in ks]).statistic)
        spread = float(quantile_returns[ks[-1]] - quantile_returns[ks[0]])
    else:
        mono, spread = np.nan, np.nan

    # signal stability: average per-ticker autocorrelation of daily ranks
    ranks = df["s"].groupby(level="date").rank(pct=True)
    wide = ranks.unstack("ticker")
    rank_ac = wide.corrwith(wide.shift(1), axis=1).mean()

    ic_by_horizon = {}
    if extra_horizon_rets:
        for h, fr in extra_horizon_rets.items():
            sub = pd.DataFrame({"s": df["s"], "f": fr}).dropna()
            if len(sub) > 100:
                ic_by_horizon[h] = float(_spearman_by_date(sub["s"], sub["f"]).mean())

    return SignalReport(
        name=name,
        ic_mean=float(ic.mean()),
        ic_std=float(ic.std()),
        icir=float(ic.mean() / (ic.std() + 1e-12)),
        ic_tstat_nw=newey_west_tstat(ic, lags=horizon),
        ic_positive_share=float((ic > 0).mean()),
        n_days=int(len(ic)),
        quantile_returns=quantile_returns,
        monotonicity=mono,
        top_bottom_spread=spread,
        rank_autocorr_1d=float(rank_ac),
        ic_by_horizon=ic_by_horizon,
        ic_series=ic,
    )


# ---------------------------------------------------------------------------
# portfolio-level stats
# ---------------------------------------------------------------------------

def perf_stats(daily_ret: pd.Series, ann_factor: int = 252) -> dict:
    r = daily_ret.dropna()
    if len(r) < 20:
        return {"n_days": int(len(r))}
    ann_ret = float(r.mean() * ann_factor)
    ann_vol = float(r.std() * np.sqrt(ann_factor))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    curve = (1 + r).cumprod()
    dd = float((curve / curve.cummax() - 1).min())
    return {
        "n_days": int(len(r)),
        "ann_return": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": float(sharpe),
        "sharpe_tstat_nw": newey_west_tstat(r, lags=10),
        "max_drawdown": dd,
        "skew": float(r.skew()),
        "kurtosis": float(r.kurtosis() + 3.0),
        "worst_day": float(r.min()),
        "best_day": float(r.max()),
    }
