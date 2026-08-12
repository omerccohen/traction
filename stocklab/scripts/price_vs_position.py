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

import re
import sys
from datetime import date, timedelta
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
MAX_RESEARCH_AGE_DAYS = 100   # filings are quarterly; research stays useful until the next season

def load_positioning() -> tuple[dict, str]:
    """Read positioning scores from ALL recent deep-research ranking files.

    Two bugs lived here in turn. First the company list was hardcoded, so a table
    dated this week silently described last week's theses. The fix — use only the
    newest date — then created the opposite bug: each week's research DELETED the
    week before, and on 2026-08-12 the table showed metals and steel alone,
    dropping 63 researched companies including PWR, CEG, ARCC and AEP.

    Research accumulates. Backlogs, contracts and non-accruals are quarterly
    facts, so every group is kept until MAX_RESEARCH_AGE_DAYS and labelled with
    its own research date and age, making staleness visible per group instead of
    silently discarding work. Table rows look like: | 1 | **PWR** | **89%** | ...
    """
    files = sorted(ROOT.glob("briefings/rank_thesis*_*.md"))
    if not files:
        return {}, ""
    newest = max(f.stem.rsplit("_", 1)[-1] for f in files)
    # Research ACCUMULATES — it does not expire weekly. Using only the newest
    # date silently deleted every prior week's work: on 2026-08-12 the table
    # showed metals and steel alone, dropping 63 researched companies including
    # PWR, CEG, ARCC and AEP — the single strongest disagreement on the board.
    # Backlogs, contracts and non-accruals are QUARTERLY facts, so a ranking
    # stays informative until the next filing season. Keep every group, label it
    # with its research date, and drop only what is genuinely stale.
    cutoff = (date.fromisoformat(newest) - timedelta(days=MAX_RESEARCH_AGE_DAYS)).isoformat()
    out: dict[str, dict] = {}
    for f in [f for f in files if f.stem.rsplit("_", 1)[-1] >= cutoff]:
        fdate = f.stem.rsplit("_", 1)[-1]
        title = re.sub(r"^rank_thesis\d*_?", "", f.stem[: -(len(fdate) + 1)])
        title = title.replace("_", " ").title() or f.stem
        age = (date.fromisoformat(newest) - date.fromisoformat(fdate)).days
        title = f"{title} — researched {fdate}" + (f" ({age}d ago)" if age else " (today)")
        rows = {}
        for line in f.read_text().splitlines():
            # ticker is the SECOND cell (a rank column precedes it) and the score
            # may be bolded and may or may not carry a '%': | 1 | **PWR** | **89** |
            # the score cell may carry trailing annotation, e.g.
            # | 5 | **BCSF** | **63%** *(LOW-conf.)* | — so don't demand the cell
            # end right after the number.
            m = re.search(r"\*\*([A-Z][A-Z0-9.\-]{0,5})\*\*\s*\|\s*\*{0,2}\s*(\d{1,3})\s*%?",
                          line)
            if m and 0 <= int(m.group(2)) <= 100:
                rows.setdefault(m.group(1), int(m.group(2)))
        if rows:
            out[title] = rows
    return out, newest
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
    # sector-relative cheapness: a BDC and a software firm are not comparable on
    # raw multiples — lenders ALWAYS look "cheap" on P/E and book-to-price, which
    # made every BDC read as a bargain in the first cut of this table.
    sectors = pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv"
                          ).set_index("Symbol")["GICS Sector"]
    uni["sector"] = uni.index.map(sectors)
    uni["cheap_pct_sector"] = (uni.groupby("sector")["VALUE"]
                               .transform(lambda s: s.rank(pct=True) * 100
                                          if s.notna().sum() >= 5 else np.nan))

    POSITIONING, rank_date = load_positioning()
    if not POSITIONING:
        print("no rank_thesis*.md files found — run the deep-research rankings first")
        return
    stale_note = ("" if rank_date == iso else
                  f"\n> **NOTE:** positioning scores come from the deep-research "
                  f"rankings dated **{rank_date}**, while prices are as of **{iso}**. "
                  "Re-run the rankings for the current week's theses to realign.\n")

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
           stale_note,
           ""]

    for thesis, names in POSITIONING.items():
        out += [f"## {thesis}", "",
                "| Ticker | Positioned | Cheap vs all | Cheap vs sector | Improving | P/E | Read |",
                "|---|---|---|---|---|---|---|"]
        recs = []
        for t, pos in names.items():
            if t not in uni.index:
                recs.append((t, pos, None, None, None, "no filings data", None))
                continue
            r = uni.loc[t]
            ey = r.get("earnings_yield")
            pe = (1 / ey) if (ey is not None and pd.notna(ey) and ey > 0) else None
            recs.append((t, pos, r["cheap_pct"], r["improve_pct"], pe,
                         quadrant(pos, r["cheap_pct"]), r.get("cheap_pct_sector")))
        for t, pos, cp, ip, pe, q, cs in sorted(recs, key=lambda x: -(x[1] or 0)):
            f0 = lambda v: f"{v:.0f}" if v is not None and np.isfinite(v) else "—"
            pes = f"{pe:.0f}" if pe is not None and np.isfinite(pe) else "n/m"
            out.append(f"| **{t}** | {pos}% | {f0(cp)} | {f0(cs)} | {f0(ip)} | {pes} | {q} |")
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
            "## What the backtest says about using this (read before acting)",
            "",
            "Adding price genuinely **fixed the direction** of the ranking: "
            "positioning alone had a forward rank-IC of −0.058, positioning+price "
            "+0.042 (t 2.7, and it held in a period never used to build it). That "
            "is a real, replicated sign flip.",
            "",
            "**But it is NOT a buy rule.** Sorting the universe into cheapness "
            "deciles over 2022-2026, the *most expensive* decile returned **+22.6%** "
            "per 6 months versus **+14.6%** for the cheapest — the giant winners "
            "lived in the expensive names. Cheap stocks won slightly more *often* "
            "(hence the positive rank-IC) while expensive stocks won far *bigger*. "
            "Buying the cheap end would have underperformed.",
            "",
            "So use the two columns to ask *\"is my thesis already in the price?\"* — "
            "never as a screen to buy the cheap end.",
            "",
            "*Honest footer: 'Cheap vs all' compares a bank to a software firm on raw "
            "multiples, which is why lenders (BDCs) look uniformly cheap — read "
            "'Cheap vs sector' for those. Positioning comes from one quarter of "
            "filings. Every decile was positive in this sample (2022-2026 was a bull "
            "market); none of this forecasts returns.*"]

    dest = ROOT / "briefings" / f"price_vs_position_{iso}.md"
    dest.write_text("\n".join(out))
    print(f"universe with valuation: {len(uni)} names")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
