"""Automated leakage guards.

Three complementary defenses:

1. shuffled_label_test  — retrain a fast model on labels shuffled ACROSS dates
   (block-shuffle preserves each date's cross-sectional label distribution).
   Any surviving IC means the pipeline itself leaks.
2. canary_test          — deliberately inject the future return as a feature.
   The pipeline must then produce absurd IC; if our detector does NOT fire,
   the detector is broken. (Tests the alarm, not the pipeline.)
3. point-in-time recomputation — features on truncated data must equal
   features on full data (implemented in tests/test_point_in_time.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def shuffle_labels_within_dates(y: pd.Series, seed: int = 0) -> pd.Series:
    """Randomly permute the ticker assignment of labels WITHIN each date.

    This is the correct null for a cross-sectional ranking model: each date
    keeps its exact label distribution, but which stock got which label is
    randomized (independently per date), destroying any feature->label
    relationship — including per-ticker persistent-drift effects that a
    weaker across-date block shuffle would leave intact (a null we tried
    first and rejected because genuine drift signal survived it; see
    docs/SKEPTIC_LOG.md). A pipeline with no leaks scores |IC| ~ 0 here.
    """
    rng = np.random.default_rng(seed)
    parts = []
    for d, grp in y.groupby(level="date", sort=False):
        vals = grp.to_numpy()
        parts.append(pd.Series(rng.permutation(vals), index=grp.index))
    out = pd.concat(parts)
    out = out.loc[y.index]
    out.name = y.name
    return out


# Backwards-compatible alias (older name, same corrected semantics).
shuffle_labels_by_date = shuffle_labels_within_dates


def inject_canary(X: pd.DataFrame, fwd_ret: pd.Series, noise: float = 0.1, seed: int = 0) -> pd.DataFrame:
    """Return X plus a '__canary' column ~= the future return (plus noise).

    Used to verify that the skeptic tripwires actually fire when leakage is
    present: run the pipeline with the canary and assert IC explodes.
    """
    rng = np.random.default_rng(seed)
    X2 = X.copy()
    f = fwd_ret.fillna(0.0)
    X2["__canary"] = f + noise * f.std() * rng.standard_normal(len(f))
    return X2


def verdict_from_ic(ic_mean: float, threshold: float = 0.02) -> str:
    """Interpret a shuffled-label IC."""
    if not np.isfinite(ic_mean):
        return "inconclusive"
    return "PASS (no pipeline leak detected)" if abs(ic_mean) < threshold else (
        f"FAIL: |IC|={abs(ic_mean):.4f} on shuffled labels — the pipeline leaks"
    )
