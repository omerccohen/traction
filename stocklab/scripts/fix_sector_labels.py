#!/usr/bin/env python3
"""Correct sector labels from REVENUE evidence, and make the file self-consistent.

Why this exists
---------------
`broad_sectors.csv` inherits SIC codes, which a company picks when it first
registers and essentially never updates. We tested the obvious cross-check and
it does not work: the SEC's own `sicDescription` is IDENTICAL to ours and
equally stale (CLF: both say "Metal Mining"; SEI: both say "Oil & Gas Field
Machinery"). Both are wrong. There is no classification source to check against
— they all descend from the same registration code.

The only test that cannot go stale is REVENUE: what the company actually earned
money from in its most recent filing. `docs/AUDIT_SECTOR_LABELS.md` did that for
the 117 companies named in the live briefings, reading each one's segment or
disaggregation-of-revenue table. Result: 87 correct (74.4%), 24 wrong (20.5%),
5 suspicious, 1 unknown. Every correction below carries its revenue share; the
filing citation is in the audit.

Errors concentrate in the micro-cap tail, which is exactly where a field's
dispersion, cohesion and biggest-mover statistics come from — so a group can
have a sound median and still produce a corrupted signal.

Two structural defects are repaired as well:
  * 32 of 169 sub-industries mapped to MORE THAN ONE sector (Industrial
    Machinery/Components appeared under Industrials x73, Technology x18,
    Miscellaneous x12, Consumer Discretionary x7, Energy x5), so the same
    business sat in two sectors depending on the row. Each sub-industry is
    pinned to its majority sector.
  * Pre-revenue companies wore operating labels — OKLO ($1.21M of revenue
    against an $81.6M loss) sat in Electric Utilities beside real utilities.
    They move on announcements, not on power prices, and they were dominating
    the movers list of fields they do not belong to. They get their own bucket.

Run:  python scripts/fix_sector_labels.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data_cache" / "universe" / "broad_sectors.csv"

PRE_REVENUE = "Development Stage/Pre-Revenue"

# ticker -> (new sub-industry, revenue evidence in one line)
CORRECTIONS: dict[str, tuple[str, str]] = {
    # --- operating businesses filed under the wrong industry -----------------
    "SEI":  ("Power Generation",
             "Power Solutions $158.3M of $219.4M Q2-26 revenue = 72.2%; "
             "power adj. EBITDA $96.4M of $121.2M = 79.5%"),
    "DNOW": ("Wholesale Distributors",
             "distributor, manufactures nothing; upstream only $508M of "
             "$1,307M = 38.9%, so 61% is not oilfield"),
    "ARKO": ("Retail-Auto Dealers and Gas Stations",
             "fuel $1,965.9M of $2,346.5M = 83.8%; merchandise 14.8%"),
    "YSWY": ("Retail-Auto Dealers and Gas Stations",
             "fuel $673.1M of $920.8M = 73.1%; inside merchandise 26.1%"),
    "CLF":  ("Steel/Iron Ore",
             "Steelmaking $5,096M of $5,226M = 97.5%; steel assets $19.5B "
             "of $20.1B"),
    "TWI":  ("Construction/Ag Equipment/Trucks",
             "off-highway wheels and tyres $366.3M of $484.8M = 75.6%; "
             "end markets agriculture and earthmoving, not steel"),
    "ATI":  ("Other Metals and Minerals",
             "~77% non-ferrous (nickel alloys 51%, titanium 15%, zirconium "
             "11%); aerospace & defense 51% of revenue"),
    "SXC":  ("Coal Mining",
             "metallurgical coke $367.5M of $475.3M = 77.3%; produces no "
             "steel and mines no ore (coal complex, not steel)"),
    "ROCK": ("Building Products",
             "Residential $425.9M of $509.5M = 83.6%"),
    "WOR":  ("Building Products",
             "building products 62%, consumer products 38%; the steel arm "
             "was separated into WS in 2023"),
    "PLPC": ("Electrical Products",
             "manufacturer, not a contractor: cost of PRODUCTS sold $139.7M "
             "of $212.7M sales; energy products 70%"),
    "OTTR": ("Multi-Sector Companies",
             "Plastics $124.6M is the LARGEST segment (37.3%) vs Electric "
             "$121.3M (36.3%); 63.7% of revenue is non-utility"),
    "ARCC": ("Finance/Investors Services",
             "lends to private middle-market COMPANIES, not consumers; "
             "gross investment income $3,052M FY25. Its 7 BDC peers in the "
             "same briefing already carry this label"),
    "IE":   ("Development Stage/Pre-Revenue",
             "Ivanhoe Electric: 100% of its $724K revenue is data-processing "
             "software; Santa Cruz Copper, Critical Metals and Energy Storage "
             "each report revenue $0; exploration expense $21.4M"),
    "ALOY": ("Development Stage/Pre-Revenue",
             "REalloys inside the former Blackboxstocks shell; $706K revenue, "
             "still books software development cost, net loss $(106.7)M; no "
             "mining revenue line exists"),
    # --- pre-revenue companies wearing an operating label --------------------
    "GFUZ": (PRE_REVENUE, "General Fusion: no revenue concept reported at all"),
    "OKLO": (PRE_REVENUE, "$1.210M revenue H1-26 — the first in company "
                          "history — against net loss $(81.6)M"),
    "NNE":  (PRE_REVENUE, "Nano Nuclear: revenue $214,042 in the quarter, "
                          "net loss $(10.1)M"),
    "FISN": (PRE_REVENUE, "Deep Fission: no revenue concept; H1 net loss "
                          "$(52.4)M"),
    "FRVO": (PRE_REVENUE, "Fervo: revenue $174K H1 against net loss $(87.7)M"),
    "DC":   (PRE_REVENUE, "Dakota Gold: no revenue; income statement is "
                          "entirely expense, net loss $(8.35)M"),
    "NB":   (PRE_REVENUE, "NioCorp: no revenue; Elk Creek pre-construction"),
    "CRML": (PRE_REVENUE, "Critical Metals: no consolidated revenue; the only "
                          "revenue sits inside an equity-accounted JV"),
    "USAR": (PRE_REVENUE, "USA Rare Earth: $5.821M from four customers, no "
                          "mining revenue disclosed; Round Top not in "
                          "production"),
}

# a sub-industry that does not already exist needs a sector
NEW_SUB_SECTOR = {PRE_REVENUE: "Miscellaneous"}

# Named in the briefings but absent from the file entirely, so it could never be
# scored or grouped. Left OUT rather than guessed: adding it needs the same
# revenue check as everything else.
KNOWN_MISSING = ["HDRN"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(CSV)
    before = df.set_index("Symbol")["GICS Sub-Industry"].to_dict()

    # 1. revenue-based corrections
    applied, absent = [], []
    for t, (new_sub, why) in CORRECTIONS.items():
        m = df["Symbol"] == t
        if not m.any():
            absent.append(t)
            continue
        old = before.get(t)
        df.loc[m, "GICS Sub-Industry"] = new_sub
        applied.append((t, old, new_sub, why))

    # 2. pin every sub-industry to ONE sector (majority wins), so the same
    #    business cannot sit in two sectors depending on the row
    for sub, sec in NEW_SUB_SECTOR.items():
        df.loc[df["GICS Sub-Industry"] == sub, "GICS Sector"] = sec
    #    A sub-industry sitting in two sectors is unambiguously wrong, so it is
    #    always pinned. But the pin is only as good as the column it votes on,
    #    and some splits are near-ties: "Industrial Specialties" is 12 Health
    #    Care / 7 Industrials / 6 Consumer Discretionary, so a 48% plurality
    #    decides it. Those are recorded as LOW CONFIDENCE rather than presented
    #    as resolved — they need the same revenue check the tickers above got.
    counts = df.groupby("GICS Sub-Industry")["GICS Sector"].nunique()
    split = counts[counts > 1]
    fixed_sectors, low_conf = [], []
    for sub in split.index:
        m = df["GICS Sub-Industry"] == sub
        vc = df.loc[m, "GICS Sector"].value_counts()
        majority, share = vc.index[0], vc.iloc[0] / vc.sum()
        moved = int((df.loc[m, "GICS Sector"] != majority).sum())
        df.loc[m, "GICS Sector"] = majority
        fixed_sectors.append((sub, majority, moved))
        if share < 0.75:
            low_conf.append((sub, majority, share, dict(vc)))

    print(f"revenue-based label corrections applied: {len(applied)}")
    for t, old, new, why in sorted(applied):
        print(f"  {t:5s} {old:42s} -> {new}")
        print(f"        {why}")
    if absent:
        print(f"\nnot in the file, skipped: {', '.join(absent)}")
    print(f"\nsub-industries pinned to one sector: {len(fixed_sectors)} "
          f"(rows moved: {sum(n for _, _, n in fixed_sectors)})")
    for sub, sec, n in sorted(fixed_sectors, key=lambda x: -x[2])[:8]:
        print(f"  {sub[:52]:54s} -> {sec} ({n} rows)")
    still = df.groupby("GICS Sub-Industry")["GICS Sector"].nunique().max()
    print(f"\nmax sectors per sub-industry after fix: {still} (must be 1)")
    if low_conf:
        print(f"\nLOW CONFIDENCE — pinned on a weak plurality, decided by a "
              f"column that is itself unreliable ({len(low_conf)} of "
              f"{len(fixed_sectors)}). Not resolved, just made consistent:")
        for sub, sec, share, vc in sorted(low_conf, key=lambda x: x[2]):
            print(f"  {share:4.0%} {sub[:44]:46s} -> {sec:24s} "
                  + ", ".join(f"{k} x{v}" for k, v in vc.items()))
    print(f"named in briefings but absent from the file: "
          f"{', '.join(KNOWN_MISSING)} — needs the same revenue check, not a guess")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return
    df.to_csv(CSV, index=False)
    print(f"\nwrote {CSV}")


if __name__ == "__main__":
    main()
