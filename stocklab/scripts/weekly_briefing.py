#!/usr/bin/env python3
"""Weekly FieldWatch briefing (BUILD_PLAN Phase 2).

Data source order: live store (data_cache/live) when it has data, else the
bundled 2013-2018 panel (demo mode, clearly labeled). A freshness guard keeps
scheduled runs honest: when the newest price is older than `--max-stale-days`
(default 10), the run emits a short STALE-DATA status instead of a full
briefing — no pretending yesterday's world is today's.

Outputs:
  briefings/briefing_<asof>.md      the full briefing (or stale notice)
  briefings/state.json              last run's field scores, for the delta section
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.data.loaders import load_bundled, sanitize_corporate_actions
from stocklab.data.panel import long_to_panel
from stocklab.data.live import PriceStore
from stocklab.fieldwatch import field_snapshot, briefing, build_fields

ROOT = Path(__file__).resolve().parents[1]
BRIEF_DIR = ROOT / "briefings"
STATE = BRIEF_DIR / "state.json"


def load_panel() -> tuple[object, str]:
    store = PriceStore(ROOT / "data_cache" / "live")
    fresh = store.freshness()
    if fresh.get("has_data"):
        df = store.load()
        panel = long_to_panel(df)
        panel, _notes = sanitize_corporate_actions(panel)
        return panel, "live"
    panel, _ = load_bundled()
    return panel, "bundled-demo"


def load_field_config(tickers) -> dict[str, list[str]]:
    cfgp = ROOT / "fields.yml"
    sectors_csv = ROOT / "data_cache" / "sp500_sectors.csv"
    cfg = yaml.safe_load(cfgp.read_text()) if cfgp.exists() else {"auto": {}, "custom": {}}
    auto = cfg.get("auto") or {}
    custom = cfg.get("custom") or {}

    if sectors_csv.exists() and (auto.get("sectors") or auto.get("subindustries")):
        sectors_df = pd.read_csv(sectors_csv).set_index("Symbol")
        fields = build_fields(
            tickers, sectors_df,
            min_members=int(auto.get("min_members", 5)),
            custom=custom,
        )
        if not auto.get("subindustries", True):
            fields = {k: v for k, v in fields.items() if not k.endswith("[sub]")}
        if not auto.get("sectors", True):
            sector_names = set(pd.read_csv(sectors_csv)["GICS Sector"].unique())
            fields = {k: v for k, v in fields.items() if k not in sector_names}
        return fields
    # no sector file: custom fields only
    return {f"{k} [custom]": [t for t in v if t in tickers]
            for k, v in custom.items() if len([t for t in v if t in tickers]) >= 3}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-stale-days", type=int, default=10)
    ap.add_argument("--as-of", default=None, help="override (demo/backfill runs)")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    BRIEF_DIR.mkdir(exist_ok=True)
    panel, source = load_panel()
    as_of = pd.Timestamp(args.as_of) if args.as_of else panel.dates[-1]

    now = pd.Timestamp(datetime.now(timezone.utc).date())
    stale_days = int((now - panel.dates[-1]).days)
    stale = source == "live" and stale_days > args.max_stale_days

    out_path = BRIEF_DIR / f"briefing_{as_of.date()}.md"
    if stale:
        out_path.write_text(
            f"# FieldWatch — STALE DATA NOTICE ({now.date()})\n\n"
            f"Newest price in the live store is {panel.dates[-1].date()} "
            f"({stale_days} days old > {args.max_stale_days} allowed). "
            "No briefing generated — a briefing on stale data would describe "
            "a market that no longer exists.\n\n"
            "Run scripts/update_prices.py (requires a network-permitted "
            "environment or a CSV drop), then re-run this script.\n"
        )
        print(f"STALE ({stale_days}d) -> {out_path}")
        return

    fields = load_field_config(list(panel.tickers))
    snaps = [field_snapshot(panel, members, name, as_of=as_of)
             for name, members in fields.items()]
    snaps = [s for s in snaps if s]

    # delta vs previous run
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    prev_scores = prev.get("scores", {})
    deltas = []
    for s in snaps:
        if s.name in prev_scores:
            d = s.score - prev_scores[s.name]
            if abs(d) >= 0.15:
                deltas.append((s.name, prev_scores[s.name], s.score, d))
    deltas.sort(key=lambda x: -abs(x[3]))

    text = briefing(snaps, as_of, top_n=args.top)
    if source == "bundled-demo":
        text = ("> **DEMO MODE**: running on the bundled 2013-2018 dataset — "
                "this describes a historical market. Wire the live feed "
                "(scripts/update_prices.py) for current briefings.\n\n") + text
    if deltas:
        lines = ["", "## Movers since last briefing "
                     f"({prev.get('as_of', 'n/a')} -> {as_of.date()})", ""]
        for name, a, b, d in deltas[:10]:
            arrow = "up" if d > 0 else "down"
            lines.append(f"- {name}: attention {a:.2f} -> {b:.2f} ({arrow})")
        text += "\n".join(lines) + "\n"

    out_path.write_text(text)
    STATE.write_text(json.dumps({
        "as_of": str(as_of.date()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "scores": {s.name: s.score for s in snaps},
    }, indent=2))
    top = sorted(snaps, key=lambda s: -s.score)[:5]
    print(f"[{source}] as of {as_of.date()}: " +
          "; ".join(f"{s.name} {s.score:.2f}" for s in top))
    print(f"-> {out_path}")


if __name__ == "__main__":
    main()
