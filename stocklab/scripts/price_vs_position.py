#!/usr/bin/env python3
"""Positioning vs price — what the market already charges.

The deep-research rankings answer "who is best positioned?". Positioning is
public information, so it may already be in the price. This script adds the
second axis: what does the market charge for that positioning?

Do NOT reintroduce backtest claims here. The valuation/positioning backtests
were retracted on 2026-08-13 (survivorship-biased universe — see
docs/BACKTEST_VALUATION.md): the "sorts backwards" result, the positioning+
price sign flip, and the decile spread all failed re-measurement on the
tradeable universe. No direction claim survives.

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
        # The score must come from the RANKING table, not from any table that
        # happens to put a number after a bolded ticker. The metals note carries
        # a short-interest table 45 lines above its ranking, and first-match-wins
        # read FCX's share count as its score: FCX 84% -> 27%, HBM 79% -> 9%,
        # ERO 74% -> 4%. FCX then flipped out of "positioned, NOT fully priced"
        # — the one quadrant this process treats as actionable — and vanished
        # from the open questions. Row counts cannot catch it: 120 rows in, 120
        # parsed, 3 silently corrupted.
        #
        # So: find the ranking table by its header, and read only its rows. The
        # ranking row shape is  | <rank> | **TICKER** | **NN%** | ...
        # Every ranking table in briefings/ opens with a "| Rank | Ticker | ..."
        # header, so anchor on that and read only the rows beneath it, until the
        # table ends. Do NOT sniff for keywords anywhere in the line: a first
        # attempt keyed on "company" or "%" appearing in the row swallowed
        # SCCO's own ranking row, whose risk column happens to say "Grupo México
        # controls the company".
        rows = {}
        in_rank = False
        for line in f.read_text().splitlines():
            if re.match(r"\s*\|\s*\**\s*rank\b", line, re.I):
                in_rank = True
                continue
            if not line.lstrip().startswith("|"):
                in_rank = False           # table ended
                continue
            if not in_rank:
                continue
            m = re.match(r"\s*\|\s*\**\s*\d{1,3}\s*\**\s*\|\s*\**\s*"
                         r"([A-Z][A-Z0-9.\-]{0,5})\s*\**\s*\|\s*\**\s*"
                         r"(\d{1,3})\s*%?", line)
            if m and 0 <= int(m.group(2)) <= 100:
                rows.setdefault(m.group(1), int(m.group(2)))
        if not rows:
            print(f"  WARNING: no ranking table parsed from {f.name}",
                  file=sys.stderr)
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
    # Guard BEFORE set_index: on an empty/missing fundamentals cache rows is
    # [], and set_index("ticker") on a columnless frame raises KeyError —
    # killing the run before the message that says how to fix it.
    if not rows:
        print("no universe data — run scripts/fetch_fundamentals.py first")
        return
    uni = pd.DataFrame(rows).set_index("ticker")

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
           "> **What this is:** what the market already charges for each "
           "researched name. Positioning is public information, so a strong "
           "filings read may already be in the price. "
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
            "in the cheaper half. The research and the price disagree here, which "
            "makes it the natural place to ask questions — it is NOT evidence that "
            "these names will do well.",
            "- **priced for perfection** — genuinely strong, and the market already "
            "charges for it.",
            "- **cheap for a reason?** — the market is discounting it; the research "
            "says it is weakly positioned. Usually the market is right.",
            "- **weak and not cheap** — neither the filings nor the price argue for it.",
            "",
            "## What the evidence says about using this (read before acting)",
            "",
            "**Nothing here is a measured edge.** The backtests that once claimed "
            "cheapness helped (a positioning/price \"sign flip\", a cheap-decile "
            "spread) were **retracted on 2026-08-13**: they were run on a universe "
            "built from today's biggest names applied back in time, which flattered "
            "every result. Re-measured on the universe actually tradeable at the "
            "time, no version of the signal passed the evidence bar, and the "
            "cheap-vs-expensive spread flipped sign. Full record: "
            "docs/BACKTEST_VALUATION.md.",
            "",
            "So use the two columns only to ask *\"is my thesis already in the "
            "price?\"* — never as a screen, in either direction.",
            "",
            "*Honest footer: 'Cheap vs all' compares a bank to a software firm on raw "
            "multiples, which is why lenders (BDCs) look uniformly cheap — read "
            "'Cheap vs sector' for those. Positioning comes from one quarter of "
            "filings. None of this forecasts returns.*"]

    dest = ROOT / "briefings" / f"price_vs_position_{iso}.md"
    dest.write_text("\n".join(out))
    print(f"universe with valuation: {len(uni)} names")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
