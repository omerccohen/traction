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

    inp = build_target_input(pack, panel, fields,
                             pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv").set_index("Symbol"),
                             as_of)

    sectors = pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv").set_index("Symbol")
    inp["value_chain_pulls"] = {}
    from stocklab.target_finder import member_moves
    for theme, kws in THEME_KEYWORDS.items():
        hits = keyword_universe_search(sectors, kws)
        mv = member_moves(panel, list(hits["ticker"]), as_of)
        merged = hits.merge(mv, on="ticker", how="inner").sort_values("ret_21d", ascending=False)
        inp["value_chain_pulls"][theme] = {
            "n": int(len(merged)),
            "companies": merged.head(40).to_dict("records"),
        }

    out = ROOT / "briefings" / f"target_input_{inp['as_of']}.json"
    out.write_text(json.dumps(inp, indent=2, default=float))
    print(f"saved -> {out}")
    print(f"themes: {list(THEME_KEYWORDS)} | fields dossiered: {len(inp['field_dossiers'])}")
    for t, d in inp["value_chain_pulls"].items():
        print(f"  {t}: {d['n']} companies matched")


if __name__ == "__main__":
    main()
