"""Synthetic market generator with *planted*, realistically-small effects.

Purpose:
1. Pipeline verification — tests assert that the system recovers a signal it
   knows exists, and reports ~zero when the signal is absent. A pipeline that
   cannot pass this on clean synthetic data has no business touching real data.
2. Offline fallback when no real data is available.

Model: single-factor market with regime-switching volatility plus planted
cross-sectional momentum and short-term reversal of tunable strength.
Effect sizes default to the low end of what the literature reports, so any
pipeline that only works on cartoonishly strong synthetic signal fails here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .panel import Panel


def make_synthetic_market(
    n_days: int = 1000,
    n_tickers: int = 80,
    momentum_strength: float = 0.05,
    reversal_strength: float = 0.05,
    seed: int = 0,
    start: str = "2015-01-02",
) -> Panel:
    """Generate a Panel whose cross-section contains planted momentum/reversal.

    momentum_strength / reversal_strength are the daily cross-sectional
    correlation between the planted signal and next-day idiosyncratic return
    scale — 0.05 is an intentionally modest, "good real signal" magnitude.
    Set both to 0.0 for a pure-noise market (null case).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    tickers = [f"S{i:03d}" for i in range(n_tickers)]

    # --- regime-switching market factor -------------------------------------
    # two-state Markov vol: calm (10% ann) / stressed (30% ann)
    p_stay = 0.98
    state = np.zeros(n_days, dtype=int)
    for t in range(1, n_days):
        if rng.random() > p_stay:
            state[t] = 1 - state[t - 1]
        else:
            state[t] = state[t - 1]
    ann_vol = np.where(state == 0, 0.10, 0.30)
    mkt_sigma = ann_vol / np.sqrt(252)
    mkt_ret = rng.normal(0.0004, 1.0, n_days) * mkt_sigma  # ~10% ann drift

    # --- idiosyncratic returns with planted structure -----------------------
    beta = rng.normal(1.0, 0.3, n_tickers)
    idio_sigma = rng.uniform(0.01, 0.03, n_tickers)  # 16%..48% ann idio vol

    rets = np.zeros((n_days, n_tickers))
    # trailing accumulators for the planted signals
    mom_window, mom_skip = 126, 10
    rev_window = 5
    log_prices = np.zeros((n_days, n_tickers))

    for t in range(n_days):
        eps = rng.normal(0, 1, n_tickers) * idio_sigma
        signal = np.zeros(n_tickers)
        if t > mom_window + mom_skip:
            past = log_prices[t - mom_skip - 1] - log_prices[t - mom_window - mom_skip - 1]
            z = (past - past.mean()) / (past.std() + 1e-12)
            signal += momentum_strength * z
        if t > rev_window + 1:
            recent = log_prices[t - 1] - log_prices[t - rev_window - 1]
            z = (recent - recent.mean()) / (recent.std() + 1e-12)
            signal -= reversal_strength * z
        rets[t] = beta * mkt_ret[t] + eps + signal * idio_sigma
        if t + 1 < n_days:
            log_prices[t + 1] = log_prices[t] + np.log1p(np.clip(rets[t], -0.5, 0.5))

    prices = 30.0 * np.exp(log_prices) * rng.uniform(0.5, 3.0, n_tickers)
    close = pd.DataFrame(prices, index=dates, columns=tickers)
    # volume loosely tied to |return| and vol regime, log-normal noise
    base_vol = rng.uniform(2e5, 5e6, n_tickers)
    vol_noise = rng.lognormal(0, 0.4, (n_days, n_tickers))
    volume = pd.DataFrame(
        base_vol * (1 + 5 * np.abs(rets)) * vol_noise, index=dates, columns=tickers
    )
    return Panel(close=close, volume=volume)
