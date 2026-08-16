#!/usr/bin/env python3
"""Point-in-time test of the VALUATION layer (hypothesis H2).

Pre-registered in experiments/PREREGISTER_improvement.md (addendum, committed
BEFORE this ran).

The levels test concluded the fundamental composite failed because it contained
no price. This tests that diagnosis: does knowing what the market ALREADY
charges (earnings yield, book/price, sales/price) turn positioning into
something with forward information?

Signals compared on identical dates:
  VALUE              cheapness (higher = cheaper)
  IMPROVEMENT        how fast the business is getting better
  LEVELS             how good it is now (the known-backwards sort)
  IMPROVEMENT+VALUE  "improving, and not already priced for it"
  LEVELS+VALUE       classic quality-at-a-reasonable-price
  momentum           reference
  IMPROV+VALUE+MOM   everything

Reported split into HELD-OUT (2022-03..2023-12, never examined) vs TAINTED
(2024-01..), raw and sector-neutral, at 63d and 126d.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sstats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stocklab.data.live import PriceStore, apply_split_adjustments
from stocklab.data.loaders import sanitize_corporate_actions
from stocklab.data.panel import long_to_panel
from stocklab.backtest.metrics import newey_west_tstat
from stocklab.fundamentals import (load_facts, improvement_features,
                                   level_features, valuation_features)

ROOT = Path(__file__).resolve().parents[1]
FWD = [63, 126]
SPLIT = pd.Timestamp("2024-01-01")
MIN_PIT_DV = 150e6      # $/day, trailing 252d median AS OF each date — the
                        # tradeability bar docs/BACKTEST_VALUATION.md already
                        # claimed the universe met but never enforced

IMPROV = ["rev_growth", "rev_accel", "margin_chg", "margin_accel"]
VALUE = ["earnings_yield", "book_to_price", "sales_to_price"]


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
    return g.groupby(by)[col].transform(
        lambda s: _z(s) if s.notna().sum() >= 5 else pd.Series(np.nan, index=s.index))


def run():
    store = PriceStore(ROOT / "data_cache" / "live")
    panel = long_to_panel(store.load())
    panel, _ = apply_split_adjustments(panel, store.load_actions())
    panel, _ = sanitize_corporate_actions(panel)
    close, dates = panel.close, panel.dates
    sectors = pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv"
                          ).set_index("Symbol")["GICS Sector"]

    funds = load_facts(ROOT / "data_cache" / "xbrl")
    tickers = [t for t in funds if t in close.columns]
    asof_idx = list(range(147, len(dates) - max(FWD) - 1, 21))

    # Point-in-time tradeability. The fundamental universe on disk was chosen by
    # `liquid_universe()`, which ranks by dollar volume over the LAST 252 days of
    # the store and applies that list back to 2018 — so a name is in the sample
    # because of what it became. Measured: 78 names climbed more than 500
    # liquidity places since 2022, and 247 of 611 (40%) traded under $150M/day
    # then. QBTS was rank 2531 at $474K/day in 2022 and is rank 157 today.
    # We cannot un-choose the downloaded pool, but we CAN refuse to count an
    # observation on a date when the name was not actually tradeable. Record the
    # trailing median dollar volume AS OF each date and report every result both
    # ways, so the hindsight-dependence is visible instead of assumed away.
    dv_pit = (close * panel.volume).rolling(252, min_periods=200).median()

    rows = []
    for i in asof_idx:
        as_of = dates[i]
        iso = str(as_of.date())
        for t in tickers:
            imp = improvement_features(funds[t], iso)
            if imp is None:
                continue
            s = close[t].loc[:as_of].dropna()
            if len(s) < 147:
                continue
            px = float(s.iloc[-1])
            val = valuation_features(funds[t], iso, px)
            if val is None:
                continue
            lev = level_features(funds[t], iso)
            fwd = {}
            for h in FWD:
                j = i + h
                fwd[f"fwd_{h}"] = (float(close[t].iloc[j] / px - 1)
                                   if j < len(dates) and np.isfinite(close[t].iloc[j])
                                   else np.nan)
            rows.append({"as_of": as_of, "ticker": t, "sector": sectors.get(t),
                         "pit_dv": float(dv_pit[t].iloc[i])
                         if np.isfinite(dv_pit[t].iloc[i]) else np.nan,
                         "momentum": float(px / s.iloc[-127] - 1),
                         "leverage": lev["leverage"], **imp,
                         **{k: v for k, v in val.items()}, **fwd})

    df = pd.DataFrame(rows)
    parts = []
    for _, g in df.groupby("as_of"):
        g = g.copy()
        for c in IMPROV + VALUE + ["margin"]:
            g["z_" + c] = _zs(g, c)
            g["sn_" + c] = _zs(g, c, by="sector")
        g["z_lowlev"], g["sn_lowlev"] = -_zs(g, "leverage"), -_zs(g, "leverage", "sector")
        g["z_mom"] = _zs(g, "momentum")
        for pre in ("z", "sn"):
            g[f"{pre}_IMPROVEMENT"] = g[[f"{pre}_{c}" for c in IMPROV]].mean(axis=1, skipna=True)
            g[f"{pre}_VALUE"] = g[[f"{pre}_{c}" for c in VALUE]].mean(axis=1, skipna=True)
            g[f"{pre}_LEVELS"] = g[[f"{pre}_margin", f"{pre}_lowlev"]].mean(axis=1, skipna=True)
            g[f"{pre}_IMPROV_VALUE"] = g[[f"{pre}_IMPROVEMENT", f"{pre}_VALUE"]].mean(axis=1, skipna=True)
            g[f"{pre}_LEVELS_VALUE"] = g[[f"{pre}_LEVELS", f"{pre}_VALUE"]].mean(axis=1, skipna=True)
        g["z_ALL"] = g[["z_IMPROVEMENT", "z_VALUE", "z_mom"]].mean(axis=1, skipna=True)
        parts.append(g)
    df = pd.concat(parts, ignore_index=True)

    def ic(sig, tgt, frame=None):
        frame = df if frame is None else frame
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
        h, tn = s[s.index < SPLIT], s[s.index >= SPLIT]
        return {"mean_ic": float(s.mean()), "nw_t": float(newey_west_tstat(s, lags=3)),
                "n_dates": int(len(s)),
                "held_out_ic": float(h.mean()) if len(h) else None, "held_out_n": int(len(h)),
                "tainted_ic": float(tn.mean()) if len(tn) else None, "tainted_n": int(len(tn))}

    def spread(sig, tgt, frame=None):
        frame = df if frame is None else frame
        sp, idx = [], []
        for d0, g in frame.groupby("as_of"):
            gg = g[[sig, tgt]].dropna().sort_values(sig)
            if len(gg) < 40:
                continue
            k = max(len(gg) // 10, 3)
            sp.append(gg[tgt].tail(k).mean() - gg[tgt].head(k).mean()); idx.append(d0)
        s = pd.Series(sp, index=pd.DatetimeIndex(idx))
        return {"mean": float(s.mean()), "median": float(s.median()),
                "nw_t": float(newey_west_tstat(s, lags=3)),
                "hit_rate": float((s > 0).mean()),
                "held_out_mean": float(s[s.index < SPLIT].mean()) if (s.index < SPLIT).any() else None,
                "tainted_mean": float(s[s.index >= SPLIT].mean()) if (s.index >= SPLIT).any() else None}

    named = ["IMPROVEMENT", "VALUE", "LEVELS", "IMPROV_VALUE", "LEVELS_VALUE"]

    def report(frame):
        blk = {"n_obs": int(len(frame)),
               "n_asof_dates": int(frame["as_of"].nunique()),
               "median_names_per_date": int(frame.groupby("as_of").size().median()),
               "median_pit_dv_musd": round(float(frame["pit_dv"].median()) / 1e6, 1)
               if frame["pit_dv"].notna().any() else None}
        for h in FWD:
            tgt = f"fwd_{h}"
            b = {n: ic("z_" + n, tgt, frame) for n in named}
            b.update({n + "_sn": ic("sn_" + n, tgt, frame) for n in named})
            b["momentum"] = ic("z_mom", tgt, frame)
            b["ALL"] = ic("z_ALL", tgt, frame)
            blk[f"IC_{h}d"] = b
            blk[f"components_{h}d"] = {c: ic("z_" + c, tgt, frame) for c in VALUE}
            blk[f"spread_{h}d"] = {n: spread("z_" + n, tgt, frame)
                                   for n in ["VALUE", "IMPROV_VALUE", "ALL"]}
        return blk

    # Both cuts, always. The screened one is the honest answer to "would this
    # have worked?"; the full one is kept beside it so the gap between them is
    # the measured cost of the hindsight-selected pool rather than a claim.
    screened = df[df["pit_dv"] >= MIN_PIT_DV]
    out = {"universe": len(tickers),
           "asof_range": [str(df["as_of"].min().date()), str(df["as_of"].max().date())],
           "pit_screen_usd_per_day": MIN_PIT_DV,
           "note": ("`full` includes every observation, including names that were "
                    "microcaps on the as-of date and only became liquid later. "
                    "`pit_screened` keeps only observations whose trailing 252d "
                    "median dollar volume ON THAT DATE cleared the screen — the "
                    "cut a real book could have traded. Read pit_screened. "
                    "NOTE: the screen cannot repair the other half of the "
                    "selection — companies that were liquid then and are gone or "
                    "illiquid now were never downloaded, so survivorship remains."),
           "full": report(df),
           "pit_screened": report(screened)}
    df.to_csv(ROOT / "experiments" / "valuation_backtest_rows.csv", index=False)
    return out


if __name__ == "__main__":
    res = run()
    (ROOT / "experiments" / "valuation_backtest.json").write_text(
        json.dumps(res, indent=2, default=float))
    print(json.dumps(res, indent=2, default=float))
