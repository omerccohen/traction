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

import numpy as np
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


MIN_LIVE_HISTORY_DAYS = 252   # audit F1: FieldWatch percentiles need a year


def load_panel() -> tuple[object, str, str]:
    """Returns (panel, source, banner). The live store is used only once it
    spans >= MIN_LIVE_HISTORY_DAYS trading days — a shorter store produced
    NaN/degenerate percentiles that read as briefings (audit F1)."""
    store = PriceStore(ROOT / "data_cache" / "live")
    fresh = store.freshness()
    if fresh.get("has_data"):
        from stocklab.data.live import apply_split_adjustments
        df = store.load()
        panel = long_to_panel(df)
        panel, _notes = apply_split_adjustments(panel, store.load_actions())
        panel, _notes2 = sanitize_corporate_actions(panel)
        if len(panel.dates) >= MIN_LIVE_HISTORY_DAYS:
            return panel, "live", ""
        banner = (f"> **LIVE STORE ACCUMULATING**: {len(panel.dates)}/"
                  f"{MIN_LIVE_HISTORY_DAYS} trading days collected — briefings "
                  "stay on the bundled demo data until the live history "
                  "supports honest percentiles.\n\n")
        panel, _ = load_bundled()
        return panel, "bundled-demo", banner
    panel, _ = load_bundled()
    return panel, "bundled-demo", ""


def load_field_config(tickers) -> tuple[dict[str, list[str]], str]:
    """Returns (fields, warning_banner). NEVER raises: a user-editable file
    must not be able to kill the weekly run (audit F9)."""
    cfgp = ROOT / "fields.yml"
    sectors_csv = ROOT / "data_cache" / "sp500_sectors.csv"
    warn = ""
    try:
        cfg = (yaml.safe_load(cfgp.read_text()) or {}) if cfgp.exists() else {}
    except yaml.YAMLError as e:
        cfg = {}
        warn += (f"> **WARNING**: fields.yml failed to parse ({e}); "
                 "using defaults (all sectors + sub-industries).\n\n")
    auto = cfg.get("auto") or {}
    custom = cfg.get("custom") or {}
    # one resolution point, default True — the gate and the filters previously
    # used contradictory defaults for missing keys (audit F10)
    want_sectors = bool(auto.get("sectors", True))
    want_subs = bool(auto.get("subindustries", True))
    min_members = max(3, int(auto.get("min_members") or 5))

    if sectors_csv.exists() and (want_sectors or want_subs):
        sectors_df = pd.read_csv(sectors_csv).set_index("Symbol")
        fields = build_fields(tickers, sectors_df, min_members=min_members, custom=custom)
        if not want_subs:
            fields = {k: v for k, v in fields.items() if not k.endswith("[sub]")}
        if not want_sectors:
            sector_names = set(sectors_df["GICS Sector"].unique())
            fields = {k: v for k, v in fields.items() if k not in sector_names}
        return fields, warn
    if not sectors_csv.exists():
        warn += ("> **WARNING**: data_cache/sp500_sectors.csv is missing — "
                 "briefing covers CUSTOM fields only (no sectors/sub-industries). "
                 "Restore the file to recover full coverage.\n\n")
    fields = {f"{k} [custom]": [t for t in v if t in tickers]
              for k, v in custom.items() if len([t for t in v if t in tickers]) >= 3}
    return fields, warn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-stale-days", type=int, default=10)
    ap.add_argument("--as-of", default=None, help="override (demo/backfill runs)")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    BRIEF_DIR.mkdir(exist_ok=True)
    panel, source, banner = load_panel()
    as_of = pd.Timestamp(args.as_of) if args.as_of else panel.dates[-1]

    now = pd.Timestamp(datetime.now(timezone.utc).date())
    stale_days = int((now - panel.dates[-1]).days)
    # --as-of is the documented backfill escape hatch: it bypasses the guard
    # (audit F4 — a backfill run must never clobber history with a notice).
    # Negative staleness = future-dated data = an error, not freshness (F5).
    stale = source == "live" and args.as_of is None and (
        stale_days > args.max_stale_days or stale_days < 0)

    if stale:
        notice = BRIEF_DIR / f"stale_{now.date()}.md"   # never a briefing name (F4)
        reason = ("future-dated rows in the store (data error)" if stale_days < 0
                  else f"{stale_days} days old > {args.max_stale_days} allowed")
        notice.write_text(
            f"# FieldWatch — STALE DATA NOTICE ({now.date()})\n\n"
            f"Newest price in the live store is {panel.dates[-1].date()}: {reason}. "
            "No briefing generated — a briefing on stale data would describe "
            "a market that no longer exists.\n\n"
            "Run scripts/update_prices.py (requires a network-permitted "
            "environment or a CSV drop), then re-run this script.\n"
        )
        print(f"STALE ({stale_days}d) -> {notice}")
        return

    out_path = BRIEF_DIR / f"briefing_{as_of.date()}.md"
    fields, config_warn = load_field_config(list(panel.tickers))
    banner += config_warn
    snaps = [field_snapshot(panel, members, name, as_of=as_of)
             for name, members in fields.items()]
    snaps = [s for s in snaps if s and np.isfinite(s.score)]

    # delta vs previous run — only comparable runs compare (audit F3):
    # same source, same field membership, and a gap within ~one month
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    deltas, delta_note = [], ""
    prev_scores = prev.get("scores", {})
    prev_members = prev.get("n_members", {})
    same_source = prev.get("source") == source
    gap_ok = True
    if prev.get("as_of"):
        gap_ok = abs((as_of - pd.Timestamp(prev["as_of"])).days) <= 31
    if prev_scores and not (same_source and gap_ok):
        delta_note = (f"(delta section suppressed: previous briefing "
                      f"[{prev.get('as_of')}, {prev.get('source')}] is not "
                      f"comparable to this one [{as_of.date()}, {source}])")
    elif prev_scores:
        for s in snaps:
            if s.name in prev_scores and prev_members.get(s.name) == s.n_members:
                d = s.score - prev_scores[s.name]
                if abs(d) >= 0.15:
                    deltas.append((s.name, prev_scores[s.name], s.score, d))
        deltas.sort(key=lambda x: -abs(x[3]))

    text = briefing(snaps, as_of, top_n=args.top)
    if source == "bundled-demo":
        banner = ("> **DEMO MODE**: running on the bundled 2013-2018 dataset — "
                  "this describes a historical market. Wire the live feed "
                  "(scripts/update_prices.py) for current briefings.\n\n") + banner
    text = banner + text

    # movers BEFORE the indicator dashboard (audit F8: it read as part of it)
    if deltas or delta_note:
        lines = ["", "## Movers since last briefing "
                     f"({prev.get('as_of', 'n/a')} -> {as_of.date()})", ""]
        if delta_note:
            lines.append(f"*{delta_note}*")
        for name, a, b, d in deltas[:10]:
            arrow = "up" if d > 0 else "down"
            lines.append(f"- {name}: attention {a:.2f} -> {b:.2f} ({arrow})")
        text += "\n".join(lines) + "\n"

    # physical/macro indicator dashboard (Phase 3) — refresh + render
    try:
        from stocklab.indicators import load_registry, refresh_all, dashboard_markdown
        inds = load_registry()
        states = refresh_all(inds)
        text += "\n" + dashboard_markdown(inds, states) + "\n"
    except Exception as e:  # the briefing must never die on the indicator layer
        text += f"\n## Physical & macro indicators\n\n*indicator layer error: {e}*\n"

    out_path.write_text(text)
    STATE.write_text(json.dumps({
        "as_of": str(as_of.date()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        # NaN scores are filtered above; state stays strict-JSON (audit F7)
        "scores": {s.name: s.score for s in snaps},
        "n_members": {s.name: s.n_members for s in snaps},
    }, indent=2))
    top = sorted(snaps, key=lambda s: -s.score)[:5]
    print(f"[{source}] as of {as_of.date()}: " +
          "; ".join(f"{s.name} {s.score:.2f}" for s in top))
    print(f"-> {out_path}")


if __name__ == "__main__":
    main()
