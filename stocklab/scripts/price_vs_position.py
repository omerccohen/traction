#!/usr/bin/env python3
"""Positioning vs price — the missing half of the research funnel.

The deep-research rankings answer "who is best positioned?". The backtest showed
that question ALONE sorts backwards, because good positioning is public and
therefore already in the price. This script adds the second axis: what does the
market already charge for that positioning?

For each researched company it reports, from real point-in-time data:
  * positioning  — the filings-based probability from the deep-research ranking
  * cheapness    — percentile vs the whole liquid universe (100 = cheapest),
                   from earnings yield / book-to-price / sales-to-price
  * improvement  — percentile of how fast the business is getting better

and puts it in one of four honest quadrants. This is DESCRIPTIVE — it says what
is already priced, not what will happen. It is not advice.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stocklab.data.live import PriceStore, apply_split_adjustments
from stocklab.data.loaders import sanitize_corporate_actions
from stocklab.data.panel import long_to_panel
from stocklab.fundamentals import (load_facts, improvement_features,
                                   valuation_features)

ROOT = Path(__file__).resolve().parents[1]

# positioning probabilities from the deep-research rankings (briefings/rank_thesis*)
POSITIONING = {
    "Construction / build-out": {"PWR": 89, "EME": 87, "FIX": 86, "IESC": 83, "AGX": 78,
                                 "HUBB": 71, "PLPC": 62, "ITRI": 55, "LMB": 48, "MTRX": 35},
    "Power / firm supply": {"CEG": 82, "VST": 74, "TLN": 67, "NRG": 44, "OTTR": 16},
    "Private credit / BDCs": {"ARCC": 82, "MAIN": 80, "FDUS": 75, "SLRC": 67, "BCSF": 63,
                              "NMFC": 57, "CION": 52, "MFIC": 45},
}
VALUE = ["earnings_yield", "book_to_price", "sales_to_price"]
IMPROV = ["rev_growth", "rev_accel", "margin_chg", "margin_accel"]


def _z(s):
    s = s.astype(float)
    s = s.clip(s.quantile(0.02), s.quantile(0.98))
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and np.isfinite(sd) else s * 0.0


def quadrant(pos, cheap_pct):
    if pos is None or cheap_pct is None or not np.isfinite(cheap_pct):
        return "insufficient data"
    if pos >= 70 and cheap_pct >= 50:
        return "positioned, NOT fully priced"
    if pos >= 70:
        return "priced for perfection"
    if cheap_pct >= 50:
        return "cheap for a reason?"
    return "weak and not cheap"


def main() -> None:
    store = PriceStore(ROOT / "data_cache" / "live")
    panel = long_to_panel(store.load())
    panel, _ = apply_split_adjustments(panel, store.load_actions())
    panel, _ = sanitize_corporate_actions(panel)
    as_of = panel.dates[-1]
    iso = str(as_of.date())
    funds = load_facts(ROOT / "data_cache" / "xbrl")

    rows = []
    for t, fam in funds.items():
        if t not in panel.close.columns:
            continue
        s = panel.close[t].loc[:as_of].dropna()
        if len(s) < 147:
            continue
        px = float(s.iloc[-1])
        val = valuation_features(fam, iso, px)
        imp = improvement_features(fam, iso)
        if val is None:
            continue
        rows.append({"ticker": t, "price": px, **val,
                     **{k: (imp or {}).get(k) for k in IMPROV}})
    uni = pd.DataFrame(rows).set_index("ticker")
    if uni.empty:
        print("no universe data — run scripts/fetch_fundamentals.py first")
        return

    # cheapness + improvement composites, percentile-ranked across the universe
    uni["VALUE"] = pd.concat([_z(uni[c]) for c in VALUE], axis=1).mean(axis=1, skipna=True)
    uni["IMPROVEMENT"] = pd.concat([_z(uni[c]) for c in IMPROV], axis=1).mean(axis=1, skipna=True)
    uni["cheap_pct"] = uni["VALUE"].rank(pct=True) * 100
    uni["improve_pct"] = uni["IMPROVEMENT"].rank(pct=True) * 100

    out = [f"# Positioning vs price — as of {iso}",
           "",
           f"*Universe for percentiles: {len(uni)} liquid US companies with usable "
           "point-in-time filings. **Cheapness 100 = cheapest** in the universe "
           "(earnings yield / book-to-price / sales-to-price). Positioning = the "
           "filings-based probability from the deep-research rankings.*",
           "",
           "> **What this is:** the second axis the backtest said was missing. "
           "Positioning alone sorts *backwards* because it is public and already "
           "in the price. This shows what the market already charges for it. "
           "**Descriptive, not advice — it does not predict returns.**",
           ""]

    for thesis, names in POSITIONING.items():
        out += [f"## {thesis}", "",
                "| Ticker | Positioned | Cheapness (pct) | Improving (pct) | P/E | Read |",
                "|---|---|---|---|---|---|"]
        recs = []
        for t, pos in names.items():
            if t not in uni.index:
                recs.append((t, pos, None, None, None, "no filings data"))
                continue
            r = uni.loc[t]
            ey = r.get("earnings_yield")
            pe = (1 / ey) if (ey is not None and pd.notna(ey) and ey > 0) else None
            recs.append((t, pos, r["cheap_pct"], r["improve_pct"], pe,
                         quadrant(pos, r["cheap_pct"])))
        for t, pos, cp, ip, pe, q in sorted(recs, key=lambda x: -(x[1] or 0)):
            cps = f"{cp:.0f}" if cp is not None and np.isfinite(cp) else "—"
            ips = f"{ip:.0f}" if ip is not None and np.isfinite(ip) else "—"
            pes = f"{pe:.0f}" if pe is not None and np.isfinite(pe) else "n/m"
            out.append(f"| **{t}** | {pos}% | {cps} | {ips} | {pes} | {q} |")
        out.append("")

    out += ["## How to read the four quadrants", "",
            "- **positioned, NOT fully priced** — strong on the filings *and* still "
            "in the cheaper half. The only quadrant where the research and the "
            "price disagree, so it is where a variant view could exist.",
            "- **priced for perfection** — genuinely strong, but the market already "
            "knows. This is exactly the group the backtest found underperforms.",
            "- **cheap for a reason?** — the market is discounting it; the research "
            "says it is weakly positioned. Usually the market is right.",
            "- **weak and not cheap** — neither the filings nor the price argue for it.",
            "",
            "*Honest footer: cheapness percentiles are relative to this liquid "
            "universe, not to each company's own history or sector norms — a bank "
            "and a software firm are not comparable on raw multiples. Positioning "
            "comes from one-quarter filings. Nothing here forecasts returns; the "
            "measured forward information in these ranks is ~zero.*"]

    dest = ROOT / "briefings" / f"price_vs_position_{iso}.md"
    dest.write_text("\n".join(out))
    print(f"universe with valuation: {len(uni)} names")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
