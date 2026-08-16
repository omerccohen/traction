"""Cross-sectional score neutralization.

Why: a dollar-neutral book is not factor-neutral. Momentum-sorted portfolios
carry systematic beta/size tilts, so the "alpha" of the long-short spread is
partly repackaged market exposure — the v1 experiment showed the classic
symptom (long leg +15%, short leg -15% in a bull market: beta, not skill).
Neutralizing scores against known exposures BEFORE portfolio formation makes
the spread a purer bet on the ranking itself (SKEPTIC CHECKLIST #19).

Mechanics: per date, replace scores with the residual of an OLS of scores on
[1, exposures]. Same-date information only — leakage-safe by construction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def neutralize_scores(scores: pd.Series, exposures: pd.DataFrame) -> pd.Series:
    """Residualize scores against exposure columns, per date.

    scores:    (date, ticker) Series.
    exposures: (date, ticker) DataFrame of exposure columns (e.g. ranked
               beta_63, log_adv_21). Rows missing any exposure keep their
               original (demeaned) score rather than being dropped.
    """
    df = exposures.reindex(scores.index)
    out_parts = []
    for d, s_d in scores.groupby(level="date", sort=False):
        y = s_d.to_numpy(dtype=float)
        X = df.loc[s_d.index].to_numpy(dtype=float)
        ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
        resid = y - np.nanmean(y[ok]) if ok.any() else y
        if ok.sum() >= X.shape[1] + 5:
            Xo = np.column_stack([np.ones(int(ok.sum())), X[ok]])
            beta, *_ = np.linalg.lstsq(Xo, y[ok], rcond=None)
            r = y.copy()
            r[ok] = y[ok] - Xo @ beta
            # rows with missing exposures: demean only (no exposure estimate)
            r[~ok] = y[~ok] - beta[0]
            resid = r
        out_parts.append(pd.Series(resid, index=s_d.index))
    out = pd.concat(out_parts)
    out.name = scores.name
    return out.loc[scores.index]
