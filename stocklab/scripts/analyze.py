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
    panel, source, banner = wb.load_panel()
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

    # Coverage warning. load_panel() already DETECTS a partial store and builds
    # the banner; this line used to drop it into `_banner` and the pack shipped
    # with no trace of it. On 2026-08-12 a pack went out built on 135 of 2,992
    # tickers (4.5%) with four of the six top fields carrying 0-1 members that
    # had actually printed, and nothing in the file said so. The check is
    # worthless if its answer is discarded, so it rides at the top of the pack
    # and the analyst brief is required to read it.
    ld = panel.close.apply(lambda s: s.last_valid_index())
    share = float((ld == as_of).mean())
    pack_dict["coverage"] = {
        "as_of": str(as_of.date()),
        "tickers_total": int(len(ld)),
        "tickers_priced_on_as_of": int((ld == as_of).sum()),
        "share_on_as_of": round(share, 4),
        "banner": banner or "",
        "ok": bool(share >= 0.95),
    }
    if share < 0.95:
        pack_dict["coverage"]["warning"] = (
            f"PARTIAL DATA: only {share:.1%} of tickers are priced on {as_of.date()}. "
            "Field scores mix trading days and thin fields may be built on one or "
            "two names. Do not rank fields against each other from this pack — "
            "re-run the price update first.")
        print(f"WARNING: pack built on {share:.1%} coverage", file=sys.stderr)

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

    # Buried moves: the attention score is a MEAN over ~5 indicators, so one
    # extreme reading gets diluted by four ordinary ones. Measured on 2026-08-11:
    # 24 of 129 fields had a 21d trend at/above the 80th percentile of their own
    # history yet ranked outside the top 15 (Basic Materials +20.5% at rank 68,
    # Paper +19.0% at rank 63). The analyst only ever sees `top_fields`, so those
    # moves were invisible to it. Surfaced here so a large one-sided move cannot
    # be averaged out of the briefing.
    try:
        import numpy as np
        ranked_all = sorted([s for s in snaps if s and np.isfinite(s.score)],
                            key=lambda s: -s.score)
        top_names = {s.name for s in ranked_all[:6]}
        buried = []
        for i, s in enumerate(ranked_all, start=1):
            tr = s.indicators.get("trend_21d", {})
            if i > 15 and (tr.get("pctile") or 0) >= 0.80 and s.name not in top_names:
                buried.append({
                    "field": s.name, "attention_rank": i, "n_fields": len(ranked_all),
                    "ret_21d": tr.get("value"), "trend_pctile": tr.get("pctile"),
                    "volume_influx_pctile": s.indicators.get("volume_influx", {}).get("pctile"),
                    "movers": s.members_moving,
                })
        buried.sort(key=lambda b: -abs(b["ret_21d"] or 0))
        pack_dict["buried_moves"] = {
            "n": len(buried),
            "note": "Large one-sided moves the composite attention score ranked "
                    "OUTSIDE the top 15. Trend at/above the 80th percentile of the "
                    "field's own history. A high trend with LOW volume_influx means "
                    "the price moved without money arriving — treat as unexplained, "
                    "not as confirmation.",
            "fields": buried[:12],
        }
    except Exception as e:
        pack_dict["buried_moves"] = {"error": str(e)}

    out = ROOT / "briefings" / f"analysis_pack_{pack.as_of}.json"
    out.write_text(json.dumps(pack_dict, indent=2, default=float))
    print(json.dumps(pack_dict, indent=2, default=float))
    print(f"\nsaved -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
