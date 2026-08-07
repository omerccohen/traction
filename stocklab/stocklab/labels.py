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
    """Per-date cross-sectional rank mapped to [-1, 1].

    Rank transforms use only same-date information — leakage-safe by
    construction — and bound the influence of outliers.
    """
    r = wide.rank(axis=1, pct=True)
    return 2.0 * (r - 0.5)


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
