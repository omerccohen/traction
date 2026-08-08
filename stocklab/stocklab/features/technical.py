"""Trailing technical features.

TIMING CONTRACT: every feature value at date t may use data up to and including
close(t), and nothing after. All operations are rolling/ewm/shift on
date-indexed wide frames — auditable by reading the code, and enforced by the
point-in-time test in tests/test_point_in_time.py.

Feature selection is deliberately conservative: factors with decades of
academic literature (momentum, short-term reversal, volatility, 52-week high,
liquidity) rather than exotica. On daily equity data, feature quality is
dominated by signal-to-noise, not cleverness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.panel import Panel

STOCK_FEATURES = [
    "ret_1d", "ret_5d",
    "mom_21", "mom_63", "mom_126", "mom_12_1",
    "vol_21", "vol_63", "downside_ratio_63",
    "px_sma50", "sma50_sma200", "macd_hist", "boll_z",
    "pct_from_high_252", "rsi_14",
    "log_adv_21", "amihud_21", "vol_trend",
    # v4 additions — each from a specific published anomaly, not invention:
    "mom_vol_scaled",    # volatility-scaled momentum (Barroso & Santa-Clara 2015)
    "mom_consistency",   # fraction of positive months in the 12-1 window
    "max_ret_21",        # lottery-demand MAX effect (Bali, Cakici, Whitelaw 2011)
    "beta_63",           # rolling market beta (low-beta anomaly; also enables neutralization)
]

MARKET_FEATURES = ["mkt_ret_21", "mkt_vol_21", "mkt_dispersion_21"]


def _ema(df: pd.DataFrame, span: int) -> pd.DataFrame:
    return df.ewm(span=span, adjust=False).mean()


def compute_stock_features(panel: Panel) -> dict[str, pd.DataFrame]:
    """Per-stock trailing features as wide (date x ticker) frames."""
    c = panel.close
    v = panel.volume
    ret1 = c.pct_change()

    out: dict[str, pd.DataFrame] = {}
    out["ret_1d"] = ret1
    out["ret_5d"] = c.pct_change(5)

    out["mom_21"] = c.pct_change(21)
    out["mom_63"] = c.pct_change(63)
    out["mom_126"] = c.pct_change(126)
    # classic 12-1: 252d return skipping the most recent 21d (avoids reversal)
    out["mom_12_1"] = c.shift(21).pct_change(231)

    out["vol_21"] = ret1.rolling(21).std() * np.sqrt(252)
    out["vol_63"] = ret1.rolling(63).std() * np.sqrt(252)
    downside = ret1.where(ret1 < 0).rolling(63, min_periods=20).std()
    out["downside_ratio_63"] = downside / (ret1.rolling(63).std() + 1e-12)

    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    out["px_sma50"] = c / sma50 - 1.0
    out["sma50_sma200"] = sma50 / sma200 - 1.0

    macd_line = _ema(c, 12) - _ema(c, 26)
    macd_signal = _ema(macd_line, 9)
    out["macd_hist"] = (macd_line - macd_signal) / c

    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    out["boll_z"] = (c - sma20) / (std20 + 1e-12)

    out["pct_from_high_252"] = c / c.rolling(252).max() - 1.0

    delta = c.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    # Wilder's smoothing = EMA with alpha 1/14
    rs = up.ewm(alpha=1 / 14, adjust=False).mean() / (
        down.ewm(alpha=1 / 14, adjust=False).mean() + 1e-12
    )
    out["rsi_14"] = 100 - 100 / (1 + rs)

    dv = panel.dollar_volume()
    adv21 = dv.rolling(21).mean()
    out["log_adv_21"] = np.log(adv21.clip(lower=1.0))
    out["amihud_21"] = (ret1.abs() / dv.clip(lower=1.0)).rolling(21).mean() * 1e9
    out["vol_trend"] = v.rolling(21).mean() / (v.rolling(63).mean() + 1e-12) - 1.0

    # ---- v4 literature additions (all trailing) ----------------------------
    out["mom_vol_scaled"] = out["mom_12_1"] / (out["vol_63"] + 1e-6)

    # consistency: share of positive non-overlapping 21d blocks in the 12-1
    # window (12 blocks ending 21d ago) — "steady" vs "one-jump" momentum
    pos_month = (c.pct_change(21) > 0).astype(float)
    out["mom_consistency"] = (
        sum(pos_month.shift(21 * i) for i in range(1, 12)) / 11.0
    )

    out["max_ret_21"] = ret1.rolling(21).max()

    mkt = ret1.mean(axis=1)
    mkt_var = mkt.rolling(63).var()
    # beta_i = cov(r_i, mkt)/var(mkt), rolling 63d, computed without loops:
    # cov = E[r*m] - E[r]E[m] over the window
    rm = ret1.mul(mkt, axis=0)
    cov = rm.rolling(63).mean() - ret1.rolling(63).mean().mul(mkt.rolling(63).mean(), axis=0)
    out["beta_63"] = cov.div(mkt_var + 1e-12, axis=0)

    return out


def compute_market_features(panel: Panel) -> pd.DataFrame:
    """Equal-weight market context features (one value per date).

    These are the same for every stock on a given date, so they carry no
    cross-sectional information on their own — they let models condition the
    *use* of stock features on the regime (e.g. momentum behaves differently
    in high-vol markets).
    """
    ret1 = panel.close.pct_change()
    mkt_ret = ret1.mean(axis=1)  # equal-weight market daily return
    out = pd.DataFrame(index=panel.dates)
    out["mkt_ret_21"] = mkt_ret.rolling(21).sum()
    out["mkt_vol_21"] = mkt_ret.rolling(21).std() * np.sqrt(252)
    out["mkt_dispersion_21"] = ret1.std(axis=1).rolling(21).mean() * np.sqrt(252)
    return out


def trailing_zscore(s: pd.Series, window: int = 252, min_periods: int = 63) -> pd.Series:
    """Point-in-time z-score: (x_t - mean(past window)) / std(past window).

    The rolling window ends at t (inclusive) — uses only information available
    at t. Clipped at +/-3 to bound outliers.
    """
    mu = s.rolling(window, min_periods=min_periods).mean()
    sd = s.rolling(window, min_periods=min_periods).std()
    return ((s - mu) / (sd + 1e-12)).clip(-3, 3)
