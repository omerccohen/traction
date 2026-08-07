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
    """Average per-date z-scored member scores (equal weights by default)."""
    if not members:
        raise ValueError("no ensemble members")
    zs = {name: zscore_by_date(s) for name, s in members.items()}
    df = pd.DataFrame(zs)
    if weights:
        w = pd.Series(weights).reindex(df.columns).fillna(0.0)
        if w.abs().sum() == 0:
            raise ValueError("all ensemble weights zero")
        out = df.mul(w, axis=1).sum(axis=1) / w.sum()
    else:
        out = df.mean(axis=1)
    out.name = "ensemble"
    return out
