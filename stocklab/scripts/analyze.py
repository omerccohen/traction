#!/usr/bin/env python3
"""Build the analysis pack from the current live data and save it.

This is the deterministic input to the hedge-fund-analyst desk note. It reuses
the exact same panel/field/indicator machinery as the weekly briefing, so the
pack can never disagree with the briefing it accompanies.

Output: briefings/analysis_pack_<as_of>.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# reuse the briefing's data loaders so pack and briefing are always consistent
import importlib.util
_wb_path = Path(__file__).resolve().parent / "weekly_briefing.py"
_spec = importlib.util.spec_from_file_location("weekly_briefing", _wb_path)
wb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wb)

from stocklab.fieldwatch import field_snapshot
from stocklab.analyst import build_analysis_pack

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    panel, source, _banner = wb.load_panel()
    as_of = panel.dates[-1]
    fields, _warn = wb.load_field_config(list(panel.tickers))
    snaps = [field_snapshot(panel, members, name, as_of=as_of)
             for name, members in fields.items()]
    snaps = [s for s in snaps if s]

    from stocklab.indicators import load_registry, refresh_all
    inds = load_registry()
    states = refresh_all(inds)

    pack = build_analysis_pack(
        snaps, inds, states, as_of=as_of, source=source,
        universe_size=len(panel.tickers), top_n=6,
    )
    pack_dict = pack.to_dict()

    # Physical-proxy panel: the commodity/theme ETF field is a physical
    # supply/demand cross-check, but it rarely ranks top-6 (percentiles are vs
    # its own history), so inject it explicitly so the analyst ALWAYS sees which
    # physical thing is actually moving. Real moves only, from the same panel.
    try:
        from stocklab.target_finder import member_moves
        etfs = fields.get("Thematic Proxies", [])
        if etfs:
            import pandas as pd
            sec = pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv").set_index("Symbol")
            sub = sec["GICS Sub-Industry"]
            mv = member_moves(panel, etfs, as_of)
            recs = []
            for r in mv.to_dict("records"):
                r["tracks"] = str(sub.get(r["ticker"], ""))
                recs.append(r)
            pack_dict["physical_proxies"] = {
                "field": "Thematic Proxies", "n": len(recs),
                "note": "Commodity/theme ETFs — physical supply/demand cross-check. "
                        "Real 21d/63d moves; use to confirm or question equity themes.",
                "movers": recs,
            }
    except Exception as e:  # never let the cross-check kill the pack
        pack_dict["physical_proxies"] = {"error": str(e)}

    out = ROOT / "briefings" / f"analysis_pack_{pack.as_of}.json"
    out.write_text(json.dumps(pack_dict, indent=2, default=float))
    print(json.dumps(pack_dict, indent=2, default=float))
    print(f"\nsaved -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
