#!/usr/bin/env python3
"""Assemble the real-data input for the target-finder (BUILD_PLAN next step).

Reads the latest analysis pack + the live panel, builds per-thesis dossiers
(real winners/losers in each flagged field) plus keyword value-chain pulls,
and writes briefings/target_input_<date>.json — the grounding the target-finder
subagent reasons over so it never invents tickers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib.util
_wb = Path(__file__).resolve().parent / "weekly_briefing.py"
_spec = importlib.util.spec_from_file_location("weekly_briefing", _wb)
wb = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(wb)

from stocklab.target_finder import build_target_input, keyword_universe_search

ROOT = Path(__file__).resolve().parents[1]

# value-chain keyword pulls for this week's theses (kept in the script so they
# are explicit and auditable; the subagent may request more)
THEME_KEYWORDS = {
    "ai_power_datacenter": ["electric", "utilit", "power", "engineering", "construction",
                            "nuclear", "energy"],
    "packaged_foods_ma": ["food", "snack", "beverage"],
    "private_credit_bdc": ["investor", "finance", "capital", "asset manage"],
}


def main() -> None:
    panel, source, _ = wb.load_panel()
    as_of = panel.dates[-1]
    fields, _ = wb.load_field_config(list(panel.tickers))

    packs = sorted(ROOT.glob("briefings/analysis_pack_*.json"))
    pack = json.loads(packs[-1].read_text()) if packs else {}

    # ORDERING GUARD (skill-level): this phase is DOWNSTREAM of analyze.py's
    # pack. Both scripts read the "newest" file by glob, so a silently-failed
    # upstream step would let us build targets on last cycle's pack. Refuse to
    # start a downstream phase whose prerequisite didn't finish for THIS data:
    # the pack's as_of must equal the current live-data date. Fail loud (exit 3,
    # no stale file written) so the Routine can skip the target-groups step
    # rather than answer this week's desk note with last week's dossier.
    data_asof = str(as_of.date())
    if not pack:
        print("find_targets: STALE PREREQUISITE — no analysis_pack found; run "
              "scripts/analyze.py first. Not building targets.", file=sys.stderr)
        sys.exit(3)
    if pack.get("as_of") != data_asof:
        print(f"find_targets: STALE PREREQUISITE — newest pack is "
              f"{pack.get('as_of')} but live data is {data_asof}; analyze.py did "
              "not finish for this cycle. Not building targets on a stale pack "
              "(re-run scripts/analyze.py first).", file=sys.stderr)
        sys.exit(3)

    inp = build_target_input(pack, panel, fields,
                             pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv").set_index("Symbol"),
                             as_of)

    sectors = pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv").set_index("Symbol")
    from stocklab.target_finder import member_moves

    # physical-proxy panel: which commodity/theme ETF is actually moving, so the
    # target-finder can verify a supply/demand thesis against the physical tape
    etfs = list(fields.get("Thematic Proxies", []))
    if etfs:
        sub = sectors["GICS Sub-Industry"]
        pmv = member_moves(panel, etfs, as_of)
        recs = [{**r, "tracks": str(sub.get(r["ticker"], ""))} for r in pmv.to_dict("records")]
        inp["physical_proxies"] = {"n": len(recs), "movers": recs}

    inp["value_chain_pulls"] = {}
    for theme, kws in THEME_KEYWORDS.items():
        hits = keyword_universe_search(sectors, kws)
        mv = member_moves(panel, list(hits["ticker"]), as_of)
        merged = hits.merge(mv, on="ticker", how="inner").sort_values("ret_21d", ascending=False)
        # `n` used to report the full match count beside a head(40) list, so a
        # theme with 112 matches shipped its 40 best 21-day performers labelled
        # "n: 112" — for two of three themes the subagent never saw a single
        # negative name and read a truncated winners' list as the whole
        # population. Take from BOTH ends when truncating, and say so.
        keep = 40
        if len(merged) > keep:
            head, tail = merged.head(keep // 2), merged.tail(keep - keep // 2)
            shown = pd.concat([head, tail])
        else:
            shown = merged
        inp["value_chain_pulls"][theme] = {
            "n_matched": int(len(merged)),
            "n_shown": int(len(shown)),
            "truncated": bool(len(merged) > keep),
            "selection": ("all matches" if len(merged) <= keep else
                          f"top {keep // 2} and bottom {keep - keep // 2} by 21d "
                          f"move of {len(merged)} matches — the middle is NOT "
                          "shown, so this is not a census"),
            "companies": shown.to_dict("records"),
        }

    out = ROOT / "briefings" / f"target_input_{inp['as_of']}.json"
    out.write_text(json.dumps(inp, indent=2, default=float))
    print(f"saved -> {out}")
    print(f"themes: {list(THEME_KEYWORDS)} | fields dossiered: {len(inp['field_dossiers'])}")
    for t, d in inp["value_chain_pulls"].items():
        print(f"  {t}: {d['n_matched']} matched, {d['n_shown']} shown"
              + (" (TRUNCATED — top and bottom only)" if d["truncated"] else ""))


if __name__ == "__main__":
    main()
