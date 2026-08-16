#!/usr/bin/env python3
"""Point-in-time backtest of a MECHANICAL 'fundamental positioning' ranking.

This is the honest, backtestable stand-in for the LLM deep-research ranker.
The LLM ranker cannot be backtested — it (and its web searches) already know
what happened. So we test the MEASURABLE core of what it rewarded — revenue
growth, margins, margin trend, low leverage — computed STRICTLY from filings
that were filed on/before each as-of date, plus price momentum for reference.

Question answered: if, at each month over the last ~2.5 years, you ranked the
liquid universe by fundamentals you actually knew THEN, did the top-ranked
names go on to rise more than the bottom-ranked ones? Reported as cross-
sectional rank-IC (Newey-West t) and a top-minus-bottom decile forward spread.

Every number is point-in-time. No lookahead. No LLM.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sstats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stocklab.data.live import PriceStore, apply_split_adjustments
from stocklab.data.loaders import sanitize_corporate_actions
from stocklab.data.panel import long_to_panel
from stocklab.backtest.metrics import newey_west_tstat

ROOT = Path(__file__).resolve().parents[1]
XBRL = ROOT / "data_cache" / "xbrl"
FWD = [63, 126]          # forward horizons (trading days ~ 3m, 6m)


def _d(s): return date.fromisoformat(s)


def _quarterly(points, as_of_iso):
    """Point-in-time quarterly (flow) series: only points filed<=as_of, ~90d span."""
    q = [p for p in points if p["filed"] <= as_of_iso and p.get("start")
         and 80 <= (_d(p["end"]) - _d(p["start"])).days <= 100]
    q.sort(key=lambda p: p["end"])
    return q


def _instant(points, as_of_iso):
    """Point-in-time balance-sheet (stock) series: latest point filed<=as_of."""
    i = [p for p in points if p["filed"] <= as_of_iso and not p.get("start")]
    i.sort(key=lambda p: p["end"])
    return i[-1] if i else None


def _yoy_prior(q, latest):
    """The quarter ~1yr before `latest` (within 45d), for YoY comparison."""
    tgt = _d(latest["end"]) - timedelta(days=365)
    cands = [p for p in q if abs((_d(p["end"]) - tgt).days) <= 45 and p["end"] < latest["end"]]
    return min(cands, key=lambda p: abs((_d(p["end"]) - tgt).days)) if cands else None


def features(fam: dict, as_of_iso: str) -> dict | None:
    """Point-in-time fundamental features for one company at one date, or None."""
    rev_q = _quarterly(fam.get("revenue", []), as_of_iso)
    if len(rev_q) < 5:
        return None
    rev, rev_prior = rev_q[-1], _yoy_prior(rev_q, rev_q[-1])
    if not rev_prior or rev["val"] <= 0 or rev_prior["val"] <= 0:
        return None
    rev_growth = rev["val"] / rev_prior["val"] - 1

    # margin on the SAME quarter (match op_income to revenue's period end)
    oi_q = _quarterly(fam.get("op_income", []), as_of_iso)
    oi_by_end = {p["end"]: p["val"] for p in oi_q}
    margin = margin_prior = None
    if rev["end"] in oi_by_end:
        margin = oi_by_end[rev["end"]] / rev["val"]
    if rev_prior["end"] in oi_by_end and rev_prior["val"]:
        margin_prior = oi_by_end[rev_prior["end"]] / rev_prior["val"]
    margin_chg = (margin - margin_prior) if (margin is not None and margin_prior is not None) else None

    eq = _instant(fam.get("equity", []), as_of_iso)
    li = _instant(fam.get("liabilities", []), as_of_iso)
    leverage = (li["val"] / eq["val"]) if (eq and li and eq["val"] > 0) else None

    # sanity gates — mis-tagged XBRL produces absurd values; DROP rather than feed
    if not (-0.9 < rev_growth < 5):
        return None
    if margin is not None and not (-2 < margin < 2):
        margin = None
    if leverage is not None and not (0 <= leverage < 50):
        leverage = None
    return {"rev_growth": rev_growth, "margin": margin,
            "margin_chg": margin_chg, "leverage": leverage,
            "rev_asof_end": rev["end"], "rev_filed": rev["filed"]}


def _z(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    lo, hi = s.quantile(0.02), s.quantile(0.98)          # winsorize
    s = s.clip(lo, hi)
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and np.isfinite(sd) else s * 0.0


def run(n_max=600):
    store = PriceStore(ROOT / "data_cache" / "live")
    panel = long_to_panel(store.load())
    panel, _ = apply_split_adjustments(panel, store.load_actions())
    panel, _ = sanitize_corporate_actions(panel)
    close, dates = panel.close, panel.dates

    funds = {f.stem: json.loads(f.read_text()) for f in XBRL.glob("*.json")}
    tickers = [t for t in funds if t in close.columns]

    # monthly as-of grid over the last ~2.5y, leaving room for the fwd window
    start_i = int(np.searchsorted(dates, dates[-1] - pd.Timedelta(days=int(2.6 * 365))))
    last_i = len(dates) - max(FWD) - 1
    asof_idx = list(range(max(start_i, 252), last_i, 21))

    rows = []
    for i in asof_idx:
        as_of = dates[i]
        as_of_iso = str(as_of.date())
        for t in tickers:
            f = features(funds[t], as_of_iso)
            if f is None:
                continue
            s = close[t].loc[:as_of].dropna()
            if len(s) < 147:
                continue
            mom = float(s.iloc[-1] / s.iloc[-127] - 1)      # 6m price momentum, pit
            fwd = {}
            for h in FWD:
                j = i + h
                fwd[f"fwd_{h}"] = (float(close[t].iloc[j] / close[t].loc[as_of] - 1)
                                   if j < len(dates) and np.isfinite(close[t].iloc[j])
                                   and np.isfinite(close[t].loc[as_of]) else np.nan)
            rows.append({"as_of": as_of, "ticker": t, "momentum": mom, **f, **fwd})

    df = pd.DataFrame(rows)
    # build cross-sectional z-scores + composites PER DATE
    parts = []
    for d0, g in df.groupby("as_of"):
        g = g.copy()
        g["z_growth"] = _z(g["rev_growth"])
        g["z_margin"] = _z(g["margin"]) if g["margin"].notna().sum() > 8 else np.nan
        g["z_mchg"] = _z(g["margin_chg"]) if g["margin_chg"].notna().sum() > 8 else np.nan
        g["z_lowlev"] = -_z(g["leverage"]) if g["leverage"].notna().sum() > 8 else np.nan
        g["z_mom"] = _z(g["momentum"])
        fund_cols = ["z_growth", "z_margin", "z_mchg", "z_lowlev"]
        g["fundamental"] = g[fund_cols].mean(axis=1, skipna=True)
        g["combined"] = g[["fundamental", "z_mom"]].mean(axis=1, skipna=True)
        parts.append(g)
    df = pd.concat(parts, ignore_index=True)

    def ic_series(signal, target):
        ics = []
        for d0, g in df.groupby("as_of"):
            gg = g[[signal, target]].dropna()
            if len(gg) >= 20 and gg[signal].nunique() > 5:
                ics.append(sstats.spearmanr(gg[signal], gg[target]).statistic)
        ics = pd.Series([x for x in ics if np.isfinite(x)])
        half = len(ics) // 2
        return {"mean_ic": float(ics.mean()), "n_dates": int(len(ics)),
                "nw_t": float(newey_west_tstat(ics, lags=3)),
                "ic_1st_half": float(ics.iloc[:half].mean()),
                "ic_2nd_half": float(ics.iloc[half:].mean())}

    def decile_spread(signal, target):
        spreads = []
        for d0, g in df.groupby("as_of"):
            gg = g[[signal, target]].dropna()
            if len(gg) < 40:
                continue
            gg = gg.sort_values(signal)
            k = max(len(gg) // 10, 3)
            spreads.append(gg[target].tail(k).mean() - gg[target].head(k).mean())
        sp = pd.Series(spreads)
        return {"mean_top_minus_bottom": float(sp.mean()), "n_dates": int(len(sp)),
                "nw_t": float(newey_west_tstat(sp, lags=3)),
                "hit_rate_top_beats_bottom": float((sp > 0).mean())}

    out = {"universe_with_fundamentals": len(tickers), "n_obs": int(len(df)),
           "n_asof_dates": int(df["as_of"].nunique()),
           "asof_range": [str(df["as_of"].min().date()), str(df["as_of"].max().date())],
           "median_names_per_date": int(df.groupby("as_of").size().median())}
    for h in FWD:
        tgt = f"fwd_{h}"
        out[f"IC_{h}d"] = {
            "fundamental_composite": ic_series("fundamental", tgt),
            "combined_with_momentum": ic_series("combined", tgt),
            "momentum_only": ic_series("z_mom", tgt),
            "rev_growth_only": ic_series("z_growth", tgt),
            "margin_only": ic_series("z_margin", tgt),
            "low_leverage_only": ic_series("z_lowlev", tgt),
        }
        out[f"decile_spread_{h}d"] = {
            "fundamental_composite": decile_spread("fundamental", tgt),
            "combined_with_momentum": decile_spread("combined", tgt),
        }
    df.to_csv(ROOT / "experiments" / "positioning_backtest_rows.csv", index=False)
    return out


if __name__ == "__main__":
    res = run()
    (ROOT / "experiments" / "positioning_backtest.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps(res, indent=2, default=float))
