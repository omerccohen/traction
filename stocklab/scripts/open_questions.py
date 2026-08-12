#!/usr/bin/env python3
"""Open questions — the machine-generated shortlist of what SURVIVED the week.

Why this exists: the weekly layers are good at debunking. The desk note kills a
story, the target-finder overturns a mechanism, the rankings demote the loudest
name. But debunking is the SETUP, not the conclusion — and the leads that
survive it lived only in whatever summary a human or an LLM happened to write.
On 2026-08-11 that failed: three independent analysts all flagged a physical
signal with no equity attention, the price table already marked a name
"positioned, NOT fully priced", and the summary still reported the week as
"nothing to do".

So the shortlist is COMPUTED here, deterministically, from the week's own
artifacts. No LLM, nothing to forget.

Three questions it answers mechanically:
  1. Where do the research and the price DISAGREE? (the only place a variant
     view can exist — everything else is already consensus)
  2. Which physical moves have NO equity attention behind them? (a commodity
     moving hard while its miners are ignored is the rarest setup on the board)
  3. What did the deep rankings rate highly that never got a price check?
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]

# proxy ETF -> the equity fields that SHOULD light up if the move is real.
# Explicit and auditable: an unmapped proxy is reported as unmapped rather than
# silently ignored.
PROXY_TO_FIELDS = {
    "COPX": ["Metal Mining", "Other Metals and Minerals"],
    "XME":  ["Metal Mining", "Steel/Iron Ore", "Metal Fabrications"],
    "SLX":  ["Steel/Iron Ore"],
    "GLD":  ["Precious Metals"],
    "URA":  ["Metal Mining", "Electric Utilities: Central"],
    "NLR":  ["Electric Utilities: Central"],
    "USO":  ["Oil and Gas Field Machinery", "Oil/Gas Transmission"],
    "XLE":  ["Oil and Gas Field Machinery", "Oil/Gas Transmission"],
    "SOXX": ["Semiconductors"],
    "LIT":  ["Metal Mining"],
    "REMX": ["Metal Mining", "Other Metals and Minerals"],
    "TAN":  ["Solar Energy"],
    "ITA":  ["Military/Government/Technical", "Aerospace"],
    "JETS": ["Air Freight/Delivery Services"],
    "IYT":  ["Trucking Freight/Courier Services"],
    "XHB":  ["Homebuilding"],
    "PAVE": ["Engineering & Construction"],
    "WOOD": ["Forest Products"],
    "DBA":  ["Farming/Seeds/Milling", "Food Chains"],
    "KRE":  ["Major Banks", "Savings Institutions"],
}
BIG_MOVE = 0.10          # a proxy move worth explaining
TOP_N_ATTENTION = 15     # "has equity attention" = inside the top N of 130


def _latest(pattern: str) -> Path | None:
    files = sorted(ROOT.glob(pattern))
    return files[-1] if files else None


def main() -> None:
    pack_p = _latest("briefings/analysis_pack_*.json")
    if not pack_p:
        print("no analysis pack found — run scripts/analyze.py first")
        return
    pack = json.loads(pack_p.read_text())
    as_of = pack["as_of"]
    scores = json.loads((ROOT / "briefings" / "state.json").read_text())["scores"]
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    rank_of = {k: i + 1 for i, (k, _) in enumerate(ranked)}

    def field_rank(name: str):
        """Attention rank of a field, matching with or without the [sub] suffix."""
        for k in scores:
            if k.split(" [")[0] == name:
                return rank_of[k], scores[k]
        return None, None

    out = [f"# Open questions — {as_of}", "",
           "*Computed, not summarised. These are the leads that SURVIVED this "
           "week's debunking. Research targets — the system has no predictive "
           "power and none of this is a buy signal.*", ""]

    # --- 1. where research and price disagree -------------------------------
    pvp = ROOT / "briefings" / f"price_vs_position_{as_of}.md"
    disagree = []
    if pvp.exists():
        for line in pvp.read_text().splitlines():
            if "positioned, NOT fully priced" in line:
                m = re.match(r"\|\s*\*\*([A-Z][A-Z0-9.\-]{0,5})\*\*\s*\|\s*(\d{1,3})%\s*\|"
                             r"\s*(\d+|—)\s*\|\s*(\d+|—)\s*\|\s*(\d+|—)\s*\|\s*([\d.]+|n/m)\s*\|", line)
                if m:
                    disagree.append(m.groups())
    out += ["## 1. Where the research and the price disagree", "",
            "*The only place a variant view can exist. Strong on the filings AND "
            "still in the cheaper half — everything else is already consensus.*", ""]
    if disagree:
        out += ["| Ticker | Positioned | Cheap vs all | Cheap vs sector | Improving | P/E |",
                "|---|---|---|---|---|---|"]
        out += [f"| **{t}** | {p}% | {c} | {cs} | {i} | {pe} |" for t, p, c, cs, i, pe in disagree]
    else:
        out.append("*None this week — every researched name is either priced for "
                   "perfection or cheap for a reason. That is a complete answer.*")
    out.append("")

    # --- 2. physical moves with no equity attention --------------------------
    out += ["## 2. Physical moves with NO equity attention", "",
            f"*A proxy moved more than {BIG_MOVE:.0%} over 21 days while the equity "
            f"fields that should follow it sit outside the top {TOP_N_ATTENTION} of "
            f"{len(scores)}. Something is happening that nobody is watching.*", ""]
    orphans, unmapped = [], []
    for mv in pack.get("physical_proxies", {}).get("movers", []):
        t, r21 = mv["ticker"], mv.get("ret_21d")
        if r21 is None or abs(r21) < BIG_MOVE:
            continue
        if t not in PROXY_TO_FIELDS:
            unmapped.append(f"{t} ({r21:+.1%})")
            continue
        ranks = [(f,) + field_rank(f) for f in PROXY_TO_FIELDS[t]]
        known = [(f, rk, sc) for f, rk, sc in ranks if rk]
        if known and all(rk > TOP_N_ATTENTION for _, rk, _ in known):
            detail = ", ".join(f"{f} rank {rk}/{len(scores)}" for f, rk, _ in known)
            orphans.append(f"- **{t} {r21:+.1%}/21d** ({mv.get('tracks','')}) — "
                           f"equity attention absent: {detail}")
    out += orphans if orphans else ["*None — every large physical move has a "
                                    "corresponding equity field drawing attention.*"]
    if unmapped:
        out += ["", f"*Unmapped proxies (no equity field assigned, so not checked): "
                    f"{', '.join(unmapped)}*"]
    out.append("")

    # --- 3. highly-ranked names with no price check -------------------------
    out += ["## 3. Rated highly by the research, never price-checked", "",
            "*Deep-research score >= 70% but missing from the price table — the "
            "positioning is known, what you would pay for it is not.*", ""]
    priced = {d[0] for d in disagree}
    if pvp.exists():
        priced |= set(re.findall(r"\|\s*\*\*([A-Z][A-Z0-9.\-]{0,5})\*\*\s*\|", pvp.read_text()))
    unchecked = []
    for f in sorted(ROOT.glob(f"briefings/rank_thesis*_{as_of}.md")):
        for line in f.read_text().splitlines():
            m = re.search(r"\*\*([A-Z][A-Z0-9.\-]{0,5})\*\*\s*\|\s*\*{0,2}\s*(\d{1,3})\s*%?", line)
            if m and int(m.group(2)) >= 70 and m.group(1) not in priced:
                unchecked.append(f"- **{m.group(1)}** ({m.group(2)}%) — from {f.name}")
    out += sorted(set(unchecked)) if unchecked else ["*None — every highly-rated "
                                                     "name has a price read.*"]
    out += ["", "---", "",
            "*Generated mechanically from this week's pack, price table and deep "
            "rankings. It exists because a human summary once reported a week as "
            "'nothing to do' while these leads sat unread in the outputs.*"]

    dest = ROOT / "briefings" / f"open_questions_{as_of}.md"
    dest.write_text("\n".join(out))
    print(f"disagreements: {len(disagree)} | orphan physical signals: {len(orphans)} "
          f"| unpriced high-rated: {len(set(unchecked))}")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
