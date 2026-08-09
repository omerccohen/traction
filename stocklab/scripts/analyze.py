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
    out = ROOT / "briefings" / f"analysis_pack_{pack.as_of}.json"
    out.write_text(json.dumps(pack.to_dict(), indent=2, default=float))
    print(json.dumps(pack.to_dict(), indent=2, default=float))
    print(f"\nsaved -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
