#!/usr/bin/env python3
"""FieldWatch demo on the bundled data.

Runs the attention allocator at two historically interesting as-of dates so the
reader can judge what it would have surfaced in real time:
  * 2016-02-10 — depth of the early-2016 momentum crash / energy bust
  * 2018-02-06 — the volatility spike at the very end of the sample
Writes experiments/fieldwatch/briefing_<date>.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.data.loaders import load_bundled
from stocklab.fieldwatch import field_snapshot, briefing

DC = Path(__file__).resolve().parents[1] / "data_cache"


def main() -> None:
    panel, _ = load_bundled()
    sectors = pd.read_csv(DC / "sp500_sectors.csv").set_index("Symbol")
    smap = sectors["GICS Sector"]
    sub = sectors["GICS Sub-Industry"]

    fields: dict[str, list[str]] = {}
    for t in panel.tickers:
        if t in smap.index:
            fields.setdefault(smap[t], []).append(t)
    # finer chip field, per the user's interest
    semis = [t for t in panel.tickers
             if t in sub.index and "Semiconductor" in str(sub[t])]
    if len(semis) >= 3:
        fields["Semiconductors (sub-industry)"] = semis

    news = None
    news_csv = DC / "sp500_news.csv"
    if news_csv.exists():
        n = pd.read_csv(news_csv, index_col=0, parse_dates=["date"])
        n["ticker"] = n["stock"].map(lambda s: {"BRK": "BRK.B"}.get(s, s))
        n["net"] = n["Positive"] - n["Negative"]
        news = n.pivot_table(index="date", columns="ticker", values="net",
                             aggfunc="mean").reindex(panel.dates)

    outdir = Path("experiments/fieldwatch")
    outdir.mkdir(parents=True, exist_ok=True)
    for as_of in ("2016-02-10", "2018-02-06"):
        ts = pd.Timestamp(as_of)
        snaps = [field_snapshot(panel, members, name, as_of=ts, news_net=news)
                 for name, members in fields.items()]
        text = briefing(snaps, ts, top_n=8)
        p = outdir / f"briefing_{as_of}.md"
        p.write_text(text)
        print(f"=== {as_of} : top fields ===")
        for s in sorted([s for s in snaps if s], key=lambda s: -s.score)[:5]:
            print(f"  {s.score:.2f}  {s.name:35s} {s.headline()}")
        print(f"  -> {p}")


if __name__ == "__main__":
    main()
