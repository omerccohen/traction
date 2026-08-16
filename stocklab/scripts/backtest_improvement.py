#!/usr/bin/env python3
"""Point-in-time test: does ranking by IMPROVEMENT beat ranking by LEVELS?

Hypothesis + decision rule are pre-registered in
experiments/PREREGISTER_improvement.md (committed BEFORE this ran).

Levels answer "how good is this company?" — the prior test showed that is
negatively related to forward returns (it is already in the price). This tests
the alternative: "how fast is it getting better?"

IMPROVEMENT features (all strictly point-in-time, filings filed<=as_of):
  rev_growth      revenue YoY growth, latest reported quarter
  rev_accel       that growth MINUS the prior quarter's YoY growth  (2nd derivative)
  margin_chg      operating margin YoY change
  margin_accel    that change MINUS the prior quarter's YoY change

Reported against LEVELS (margin level, low leverage) and momentum on identical
dates, split into a HELD-OUT period (2022-03..2023-12, never examined) and the
TAINTED period (2024-01..) where margin-change was originally spotted.
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
FWD = [63, 126]
SPLIT = pd.Timestamp("2024-01-01")      # held-out (before) vs tainted (after)


def _d(s): return date.fromisoformat(s)


def _quarterly(points, as_of_iso):
    q = [p for p in points if p["filed"] <= as_of_iso and p.get("start")
         and 80 <= (_d(p["end"]) - _d(p["start"])).days <= 100]
    q.sort(key=lambda p: p["end"])
    # dedupe by period end, keeping the earliest-filed (first knowledge)
    seen = {}
    for p in q:
        if p["end"] not in seen:
            seen[p["end"]] = p
    return sorted(seen.values(), key=lambda p: p["end"])


def _instant(points, as_of_iso):
    i = [p for p in points if p["filed"] <= as_of_iso and not p.get("start")]
    i.sort(key=lambda p: p["end"])
    return i[-1] if i else None


def _year_ago(q, ref):
    """The quarter ~365d before `ref` (within 45d), strictly earlier."""
    tgt = _d(ref["end"]) - timedelta(days=365)
    c = [p for p in q if p["end"] < ref["end"] and abs((_d(p["end"]) - tgt).days) <= 45]
    return min(c, key=lambda p: abs((_d(p["end"]) - tgt).days)) if c else None


def features(fam: dict, as_of_iso: str) -> dict | None:
    rev_q = _quarterly(fam.get("revenue", []), as_of_iso)
    if len(rev_q) < 6:                       # need 2 quarters + both year-agos
        return None
    cur, prev = rev_q[-1], rev_q[-2]
    cur_ya, prev_ya = _year_ago(rev_q, cur), _year_ago(rev_q, prev)
    if not cur_ya or not cur_ya["val"] or cur["val"] <= 0:
        return None

    g_now = cur["val"] / cur_ya["val"] - 1
    g_prev = (prev["val"] / prev_ya["val"] - 1) if (prev_ya and prev_ya["val"]) else None
    rev_accel = (g_now - g_prev) if g_prev is not None else None

    # margins on matching period-ends
    oi = {p["end"]: p["val"] for p in _quarterly(fam.get("op_income", []), as_of_iso)}
    rv = {p["end"]: p["val"] for p in rev_q}

    def marg(p):
        if p and p["end"] in oi and rv.get(p["end"]):
            m = oi[p["end"]] / rv[p["end"]]
            return m if -2 < m < 2 else None
        return None

    m_now, m_ya = marg(cur), marg(cur_ya)
    m_prev, m_prev_ya = marg(prev), marg(prev_ya)
    margin_chg = (m_now - m_ya) if (m_now is not None and m_ya is not None) else None
    margin_chg_prev = (m_prev - m_prev_ya) if (m_prev is not None and m_prev_ya is not None) else None
    margin_accel = ((margin_chg - margin_chg_prev)
                    if (margin_chg is not None and margin_chg_prev is not None) else None)

    eq = _instant(fam.get("equity", []), as_of_iso)
    li = _instant(fam.get("liabilities", []), as_of_iso)
    leverage = (li["val"] / eq["val"]) if (eq and li and eq["val"] > 0) else None

    # sanity gates — drop mis-tagged XBRL rather than feed it in
    if not (-0.9 < g_now < 5):
        return None
    if rev_accel is not None and not (-3 < rev_accel < 3):
        rev_accel = None
    if leverage is not None and not (0 <= leverage < 50):
        leverage = None
    return {"rev_growth": g_now, "rev_accel": rev_accel, "margin": m_now,
            "margin_chg": margin_chg, "margin_accel": margin_accel,
            "leverage": leverage}


def _z(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    s = s.clip(s.quantile(0.02), s.quantile(0.98))
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and np.isfinite(sd) else s * 0.0


def _zs(g, col, by=None):
    if g[col].notna().sum() < 8:
        return pd.Series(np.nan, index=g.index)
    if by is None:
        return _z(g[col])
    return g.groupby(by)[col].transform(lambda s: _z(s) if s.notna().sum() >= 5
                                        else pd.Series(np.nan, index=s.index))


def run():
    store = PriceStore(ROOT / "data_cache" / "live")
    panel = long_to_panel(store.load())
    panel, _ = apply_split_adjustments(panel, store.load_actions())
    panel, _ = sanitize_corporate_actions(panel)
    close, dates = panel.close, panel.dates
    sectors = pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv"
                          ).set_index("Symbol")["GICS Sector"]

    funds = {f.stem: json.loads(f.read_text()) for f in XBRL.glob("*.json")}
    tickers = [t for t in funds if t in close.columns]

    # widest honest grid: needs 147d of price history behind, 126d of forward ahead
    asof_idx = list(range(147, len(dates) - max(FWD) - 1, 21))

    rows = []
    for i in asof_idx:
        as_of = dates[i]
        iso = str(as_of.date())
        for t in tickers:
            f = features(funds[t], iso)
            if f is None:
                continue
            s = close[t].loc[:as_of].dropna()
            if len(s) < 147:
                continue
            fwd = {}
            for h in FWD:
                j = i + h
                fwd[f"fwd_{h}"] = (float(close[t].iloc[j] / close[t].loc[as_of] - 1)
                                   if j < len(dates) and np.isfinite(close[t].iloc[j])
                                   and np.isfinite(close[t].loc[as_of]) else np.nan)
            rows.append({"as_of": as_of, "ticker": t, "sector": sectors.get(t),
                         "momentum": float(s.iloc[-1] / s.iloc[-127] - 1), **f, **fwd})

    df = pd.DataFrame(rows)
    IMPROV = ["rev_growth", "rev_accel", "margin_chg", "margin_accel"]
    parts = []
    for _, g in df.groupby("as_of"):
        g = g.copy()
        for c in IMPROV:
            g["z_" + c] = _zs(g, c)
            g["sn_" + c] = _zs(g, c, by="sector")
        g["z_margin"], g["z_lowlev"] = _zs(g, "margin"), -_zs(g, "leverage")
        g["sn_margin"], g["sn_lowlev"] = _zs(g, "margin", "sector"), -_zs(g, "leverage", "sector")
        g["z_mom"] = _zs(g, "momentum")
        g["IMPROVEMENT"] = g[["z_" + c for c in IMPROV]].mean(axis=1, skipna=True)
        g["IMPROVEMENT_sn"] = g[["sn_" + c for c in IMPROV]].mean(axis=1, skipna=True)
        g["LEVELS"] = g[["z_margin", "z_lowlev"]].mean(axis=1, skipna=True)
        g["LEVELS_sn"] = g[["sn_margin", "sn_lowlev"]].mean(axis=1, skipna=True)
        g["IMPROV_plus_MOM"] = g[["IMPROVEMENT", "z_mom"]].mean(axis=1, skipna=True)
        parts.append(g)
    df = pd.concat(parts, ignore_index=True)

    def ic(frame, sig, tgt):
        ics, idx = [], []
        for d0, g in frame.groupby("as_of"):
            gg = g[[sig, tgt]].dropna()
            if len(gg) >= 20 and gg[sig].nunique() > 5:
                r = sstats.spearmanr(gg[sig], gg[tgt]).statistic
                if np.isfinite(r):
                    ics.append(r); idx.append(d0)
        s = pd.Series(ics, index=pd.DatetimeIndex(idx))
        if s.empty:
            return None
        held, taint = s[s.index < SPLIT], s[s.index >= SPLIT]
        return {"mean_ic": float(s.mean()), "nw_t": float(newey_west_tstat(s, lags=3)),
                "n_dates": int(len(s)),
                "held_out_ic": float(held.mean()) if len(held) else None,
                "held_out_n": int(len(held)),
                "tainted_ic": float(taint.mean()) if len(taint) else None,
                "tainted_n": int(len(taint))}

    def spread(sig, tgt):
        sp, idx = [], []
        for d0, g in df.groupby("as_of"):
            gg = g[[sig, tgt]].dropna().sort_values(sig)
            if len(gg) < 40:
                continue
            k = max(len(gg) // 10, 3)
            sp.append(gg[tgt].tail(k).mean() - gg[tgt].head(k).mean()); idx.append(d0)
        s = pd.Series(sp, index=pd.DatetimeIndex(idx))
        return {"mean_top_minus_bottom": float(s.mean()),
                "median": float(s.median()),
                "nw_t": float(newey_west_tstat(s, lags=3)),
                "hit_rate": float((s > 0).mean()),
                "held_out_mean": float(s[s.index < SPLIT].mean()) if (s.index < SPLIT).any() else None,
                "tainted_mean": float(s[s.index >= SPLIT].mean()) if (s.index >= SPLIT).any() else None}

    out = {"universe": len(tickers), "n_obs": int(len(df)),
           "n_asof_dates": int(df["as_of"].nunique()),
           "asof_range": [str(df["as_of"].min().date()), str(df["as_of"].max().date())],
           "split_date": str(SPLIT.date()),
           "median_names_per_date": int(df.groupby("as_of").size().median())}
    for h in FWD:
        tgt = f"fwd_{h}"
        out[f"IC_{h}d"] = {k: ic(df, k, tgt) for k in
                           ["IMPROVEMENT", "IMPROVEMENT_sn", "LEVELS", "LEVELS_sn",
                            "z_mom", "IMPROV_plus_MOM"]}
        out[f"components_{h}d"] = {c: ic(df, "z_" + c, tgt) for c in IMPROV}
        out[f"spread_{h}d"] = {k: spread(k, tgt) for k in ["IMPROVEMENT", "LEVELS", "IMPROV_plus_MOM"]}
    df.to_csv(ROOT / "experiments" / "improvement_backtest_rows.csv", index=False)
    return out


if __name__ == "__main__":
    res = run()
    (ROOT / "experiments" / "improvement_backtest.json").write_text(
        json.dumps(res, indent=2, default=float))
    print(json.dumps(res, indent=2, default=float))
