"""Score ensembling.

Members' scores are z-scored per date (so units are comparable), then
averaged. Admission rule: a member joins the ensemble only if its own
out-of-sample IC beat the momentum baseline's — an ensemble of losers is
not diversification, it is dilution.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def zscore_by_date(scores: pd.Series) -> pd.Series:
    g = scores.groupby(level="date")
    mu = g.transform("mean")
    sd = g.transform("std")
    return (scores - mu) / (sd + 1e-12)


def ensemble_scores(members: dict[str, pd.Series], weights: dict[str, float] | None = None) -> pd.Series:
    """Average per-date z-scored member scores (equal weights by default).

    Rows where some members are missing are renormalized over the PRESENT
    members' weights (a fixed divisor silently shrank partial-coverage rows
    toward zero — review finding F6). Weights must be non-negative and name
    only actual members.
    """
    if not members:
        raise ValueError("no ensemble members")
    zs = {name: zscore_by_date(s) for name, s in members.items()}
    df = pd.DataFrame(zs)
    if weights:
        unknown = set(weights) - set(df.columns)
        if unknown:
            raise ValueError(f"weights name unknown members: {sorted(unknown)}")
        w = pd.Series(weights).reindex(df.columns).fillna(0.0)
        if (w < 0).any() or w.sum() <= 0:
            raise ValueError("ensemble weights must be non-negative with positive sum")
        num = df.mul(w, axis=1).sum(axis=1)
        den = df.notna().mul(w, axis=1).sum(axis=1)
        out = num / den.replace(0.0, np.nan)
    else:
        out = df.mean(axis=1)   # skips NaN per row == renormalized equal weights
    out.name = "ensemble"
    return out.dropna()
