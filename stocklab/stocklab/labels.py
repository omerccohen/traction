"""Forward-return labels with an explicit execution lag.

TIMING CONTRACT (see docs/DESIGN.md):
    signal date t -> enter at close(t + lag) -> exit at close(t + lag + horizon)
    label(t) = close(t + lag + horizon) / close(t + lag) - 1

With the default lag=1 you can never trade the close you computed the signal
on — the classic subtle lookahead in tutorial backtests.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data.panel import Panel


def forward_returns(panel: Panel, horizon: int = 5, lag: int = 1) -> pd.DataFrame:
    """Wide (date x ticker) forward returns per the timing contract.

    The last `horizon + lag` dates have NaN labels (future unknown) — they are
    excluded from training/evaluation but still usable for live scoring.
    """
    if horizon < 1 or lag < 0:
        raise ValueError("horizon must be >=1 and lag >=0")
    c = panel.close
    entry = c.shift(-lag)
    exit_ = c.shift(-(lag + horizon))
    return exit_ / entry - 1.0


def cross_sectional_rank(wide: pd.DataFrame) -> pd.DataFrame:
    """Per-date cross-sectional rank mapped SYMMETRICALLY onto [-1, 1].

    Rank transforms use only same-date information — leakage-safe by
    construction — and bound the influence of outliers.

    Uses (2*(r-1)/(n-1)) - 1 with average ranks r in 1..n, so the lowest name
    maps to -1 and the highest to +1 regardless of n. (The earlier 2*(pct-.5)
    form had range [-1+2/n, 1] and a +1/n mean that drifted with universe
    size — review finding m3.) Single-name dates map to 0.
    """
    r = wide.rank(axis=1)                       # average ranks, NaN preserved
    n = wide.notna().sum(axis=1)
    out = (2.0 * (r - 1.0)).div(n - 1.0, axis=0) - 1.0
    out[n == 1] = 0.0
    return out


def make_target(fwd: pd.DataFrame, kind: str = "rank") -> pd.DataFrame:
    """Training target from raw forward returns.

    'rank'   — per-date rank in [-1,1]; robust, what most ranking systems use.
    'demean' — per-date demeaned raw return; keeps magnitude information.
    Evaluation always uses raw forward returns regardless of training target.
    """
    if kind == "rank":
        return cross_sectional_rank(fwd)
    if kind == "demean":
        return fwd.sub(fwd.mean(axis=1), axis=0)
    raise ValueError(f"unknown target kind: {kind}")
