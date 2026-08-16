"""Live ranking report: today's cross-sectional scores, with the honesty
attached (metrics of the signal that produced them, skeptic flags, and the
disclaimer). A ranking without its out-of-sample evidence is not shipped.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import DISCLAIMER
from .features.pipeline import FeatureDataset
from .models.base import Model


@dataclass
class RankingReport:
    as_of: pd.Timestamp
    table: pd.DataFrame          # ticker, score, percentile, top features
    signal_evidence: dict        # OOS metrics of this model family
    skeptic_summary: str
    markdown: str


def latest_ranking(
    ds: FeatureDataset,
    model: Model,
    signal_evidence: dict | None = None,
    skeptic_summary: str = "",
    top_n: int = 20,
) -> RankingReport:
    """Score the most recent date with a model trained on ALL labeled data.

    The trained model may use every date whose label is complete; the scored
    date's rows carry no label (they are the live rows) — nothing is leaked.
    """
    dates = ds.dates
    as_of = dates[-1]

    labeled_dates = pd.DatetimeIndex(
        ds.fwd_ret.dropna().index.get_level_values("date").unique()
    ).sort_values()
    model.fit(ds, labeled_dates)
    scores = model.predict(ds, pd.DatetimeIndex([as_of]))
    s_all = scores.xs(as_of, level="date")
    # NaN sorts LAST in sort_values, so unscored names would fill the
    # "Bottom N (lowest scores)" table as the model's most bearish picks.
    n_unscored = int(s_all.isna().sum())
    s = s_all.dropna().sort_values(ascending=False)
    pct = s.rank(pct=True)

    x_today = ds.X.xs(as_of, level="date")
    # market-context features are identical across stocks on a date — showing
    # them per name is noise; display only stock-specific features
    from .features.technical import MARKET_FEATURES
    stock_cols = [c for c in x_today.columns if c not in MARKET_FEATURES]

    n_distinct = s.round(10).nunique()
    rows = []
    for tkr, sc in s.items():
        feats = x_today.loc[tkr, stock_cols]
        top_feats = feats.abs().sort_values(ascending=False).head(3).index.tolist()
        rows.append({
            "ticker": tkr,
            "score": float(sc),
            "percentile": float(pct.loc[tkr]),
            "notable_features": ", ".join(f"{f}={feats[f]:+.2f}" for f in top_feats),
        })
    table = pd.DataFrame(rows)

    md = [
        f"# StockLab ranking as of {as_of.date()}",
        "",
        f"> {DISCLAIMER}",
        "",
        "**Read the evidence before the ranking.** The out-of-sample record of this",
        "signal family on this dataset is the only justification these ranks have:",
        "",
        "```json",
        str(signal_evidence or {}),
        "```",
        "",
    ]
    if skeptic_summary:
        md += ["**Skeptic flags on the underlying signal:**", "", "```", skeptic_summary, "```", ""]
    # head/tail overlap when fewer than 2*top_n names have scores — the same
    # ticker must never appear as both a highest and a lowest score
    k = min(top_n, len(table) // 2) if len(table) < 2 * top_n else top_n
    md += [
        f"## Top {k} (highest scores)",
        "",
        table.head(k).to_markdown(index=False),
        "",
        f"## Bottom {k} (lowest scores)",
        "",
        table.tail(k).iloc[::-1].to_markdown(index=False),
        "",
        f"*The model assigns only {n_distinct} distinct score levels across "
        f"{len(s)} scored names — tied scores mean the model genuinely cannot "
        "distinguish those stocks; the within-tie ordering is arbitrary.*"
        + (f" *{n_unscored} name(s) had no usable score and are excluded "
           "from both tables.*" if n_unscored else ""),
        "",
        "*Scores are cross-sectional relative rankings for the configured horizon — "
        "not price targets, not probabilities, not advice.*",
    ]

    return RankingReport(
        as_of=as_of,
        table=table,
        signal_evidence=signal_evidence or {},
        skeptic_summary=skeptic_summary,
        markdown="\n".join(md),
    )
