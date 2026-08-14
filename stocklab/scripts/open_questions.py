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
_CLOSE = _FIELDS = None   # shared by sections 2b/2c, built once

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
TREND_PCTILE = 0.80      # a move this extreme should not be buried by averaging
FLAT_AVG = 0.03          # group average this small reads as "nothing happening"
SPLIT_SPREAD = 0.50      # ...while members this far apart means plenty happened


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
    # A company researched in two groups yields two rows — CEG and VST are in
    # both the power and the utilities rankings — so the count overstated the
    # number of distinct leads (18 rows, 16 companies). Keep the highest
    # positioning score per ticker and say how many were merged, rather than
    # presenting the same company twice as two separate opportunities.
    dupes = len(disagree) - len({d[0] for d in disagree})
    best: dict[str, tuple] = {}
    for row in disagree:
        if row[0] not in best or int(row[1]) > int(best[row[0]][1]):
            best[row[0]] = row
    disagree = sorted(best.values(), key=lambda r: -int(r[1]))
    out += ["## 1. Where the research and the price disagree", "",
            "*The only place a variant view can exist. Strong on the filings AND "
            "still in the cheaper half — everything else is already consensus.*", ""]
    if disagree:
        out += ["| Ticker | Positioned | Cheap vs all | Cheap vs sector | Improving | P/E |",
                "|---|---|---|---|---|---|"]
        out += [f"| **{t}** | {p}% | {c} | {cs} | {i} | {pe} |" for t, p, c, cs, i, pe in disagree]
        if dupes:
            out += ["", f"*{dupes} company/companies appeared in two research "
                        "groups (CEG and VST are ranked in both power and "
                        "utilities); each is listed once at its highest "
                        "positioning score, so this is a count of distinct "
                        "names, not of table rows.*"]
    elif not pvp.exists():
        # "no disagreements" and "the input file is not there" are different
        # answers, and this printed the reassuring one for both. Moving the
        # price table aside turned 17 disagreements into a confident "that is a
        # complete answer" — the exact failure this whole file exists to
        # prevent. The two cases must never share a sentence again.
        out.append(f"> **CANNOT ANSWER — `{pvp.name}` does not exist.** This "
                   "section is blank because its input is MISSING, not because "
                   "nothing survived. Run `scripts/price_vs_position.py` first; "
                   "until then this week's disagreements are unknown.")
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

    # --- 2b. big moves the composite attention score buried ------------------
    # Measured failure, not a hypothetical: attention = mean(|pctile-0.5|) across
    # ~5 indicators, so ONE extreme reading is diluted by four middling ones. On
    # 2026-08-11, 24 of 129 fields had a trend at/above the 80th percentile of
    # their own history yet ranked outside the top 15 — Basic Materials was
    # +20.5% (92nd pctile) at rank 68, Paper +19.0% (98th) at rank 63. The
    # metals move was found by LLM analysts DESPITE the score, not because of it.
    # A big one-sided move on draining volume is precisely the shape the
    # composite hides, so it is surfaced here directly.
    out += ["## 2b. Big moves the attention score buried", "",
            f"*Trend at/above the {int(TREND_PCTILE*100)}th percentile of the "
            f"field's own history, yet ranked outside the top {TOP_N_ATTENTION}. "
            "The composite averages five indicators, so a single extreme reading "
            "gets diluted — these are large one-sided moves the ranking "
            "de-emphasised.*", ""]
    buried = []
    global _CLOSE, _FIELDS
    try:
        import numpy as np
        import pandas as pd
        from stocklab.data.live import PriceStore, apply_split_adjustments
        from stocklab.data.loaders import sanitize_corporate_actions
        from stocklab.data.panel import long_to_panel
        from stocklab.fieldwatch import field_snapshot, build_fields
        st = PriceStore(ROOT / "data_cache" / "live")
        pnl = long_to_panel(st.load())
        pnl, _ = apply_split_adjustments(pnl, st.load_actions())
        pnl, _ = sanitize_corporate_actions(pnl)
        sec = pd.read_csv(ROOT / "data_cache" / "universe" / "broad_sectors.csv").set_index("Symbol")
        flds = build_fields(list(pnl.tickers), sec, min_members=5)
        _CLOSE, _FIELDS = pnl.close.ffill(limit=3), flds
        rows = []
        for n, mem in flds.items():
            sn = field_snapshot(pnl, mem, n, as_of=pnl.dates[-1])
            if sn and np.isfinite(sn.score):
                i = sn.indicators
                rows.append({"field": n, "att": sn.score,
                             "ret": i.get("trend_21d", {}).get("value"),
                             "tp": i.get("trend_21d", {}).get("pctile"),
                             "vi": i.get("volume_influx", {}).get("pctile")})
        d = pd.DataFrame(rows).dropna(subset=["att", "tp"])
        d["rk"] = d["att"].rank(ascending=False)
        hit = d[(d["tp"] >= TREND_PCTILE) & (d["rk"] > TOP_N_ATTENTION)]
        n_qual, n_shown = len(hit), min(len(hit), 10)
        for r in hit.sort_values("ret", key=abs, ascending=False).head(10).itertuples():
            vi = f"volume p{r.vi*100:.0f}" if r.vi == r.vi else "volume n/a"
            buried.append(f"- **{r.field}** — {r.ret:+.1%}/21d at the "
                          f"{r.tp*100:.0f}th pctile of its own history, {vi}, "
                          f"but attention rank **{r.rk:.0f}/{len(d)}**")
        # a cap that does not announce itself reads as a census — Steel/Iron Ore
        # was one of the entries silently dropped here
        if n_qual > n_shown:
            buried.append(f"- *…and {n_qual - n_shown} more qualifying fields not "
                          f"shown ({n_qual} qualified, top {n_shown} by size listed).*")
    except Exception as e:
        buried = [f"*could not compute: {type(e).__name__}: {e}*"]
    out += buried if buried else ["*None — no large move is being hidden by the "
                                  "composite this week.*"]
    out.append("")

    # --- 2c. groups that look calm but are violently split inside ------------
    # The SECOND averaging trap, found the same way as 2b. A field's headline
    # return is the equal-weight MEAN of its members, so big winners and big
    # losers cancel and the group reads "asleep". The `dispersion` indicator is
    # supposed to catch this, but it is scored against the field's OWN history —
    # a field that is always dispersed never looks unusually dispersed. Measured
    # on 2026-08-11: 17 of 129 fields had a near-flat average with a >50-point
    # internal spread, and 6 of the 8 largest were ranked outside the top 40
    # (Restaurants 119/130 with a member at +38% and another at -35%).
    out += ["## 2c. Groups that look calm but are split inside", "",
            "*Average move near zero, but the members are pulling violently "
            "apart — the winners and losers cancel out in the headline number. "
            "The group looks asleep; individual companies are not.*", ""]
    split = []
    try:
        import numpy as np
        r21 = _CLOSE.iloc[-1] / _CLOSE.iloc[-22] - 1
        for n, mem in _FIELDS.items():
            cols = [t for t in mem if t in r21.index and np.isfinite(r21.get(t, np.nan))]
            if len(cols) < 5:
                continue
            v = r21[cols]
            avg, spread = float(v.mean()), float(v.max() - v.min())
            rk, _ = field_rank(n.split(" [")[0])
            if abs(avg) < FLAT_AVG and spread > SPLIT_SPREAD and rk and rk > TOP_N_ATTENTION:
                split.append((spread, f"- **{n}** — average {avg:+.1%} but best "
                                      f"{v.max():+.0%} / worst {v.min():+.0%} across "
                                      f"{len(cols)} companies, attention rank "
                                      f"**{rk}/{len(scores)}**"))
        n_split = len(split)
        split = [s for _, s in sorted(split, key=lambda x: -x[0])][:8]
        if n_split > len(split):
            split.append(f"- *…and {n_split - len(split)} more split groups not "
                         f"shown ({n_split} qualified, widest {len(split) - 1} listed).*")
    except Exception as e:
        split = [f"*could not compute: {type(e).__name__}: {e}*"]
    out += split if split else ["*None — no group is hiding a violent internal "
                                "split behind a calm average.*"]
    out.append("")

    # --- 3. highly-ranked names with no price check -------------------------
    out += ["## 3. Rated highly by the research, never price-checked", "",
            "*Deep-research score >= 70% but missing from the price table — the "
            "positioning is known, what you would pay for it is not.*", ""]
    priced = {d[0] for d in disagree}
    if pvp.exists():
        priced |= set(re.findall(r"\|\s*\*\*([A-Z][A-Z0-9.\-]{0,5})\*\*\s*\|", pvp.read_text()))
    # Two bugs lived here. It globbed ONE exact date while the price table
    # accumulates 100 days of research, so the committed 2026-08-11 file
    # announced "every highly-rated name has a price read" while 17 names at
    # 70%+ (SCCO 91, PWR 89, NUE 88, EME 87) had none. And it re-implemented the
    # loose ticker regex that read FCX's short-interest share count as its
    # score. Reuse price_vs_position's parser — one accumulation window, one
    # ranking-table anchor, one place to fix.
    unchecked = []
    try:
        import importlib.util
        _s = importlib.util.spec_from_file_location(
            "pvp", Path(__file__).resolve().parent / "price_vs_position.py")
        _pvp = importlib.util.module_from_spec(_s)
        _s.loader.exec_module(_pvp)
        positioning, _ = _pvp.load_positioning()
        for group, names in positioning.items():
            for tkr, score in names.items():
                if score >= 70 and tkr not in priced:
                    unchecked.append(f"- **{tkr}** ({score}%) — from {group}")
    except Exception as e:
        unchecked.append(f"- *could not read the rankings: {type(e).__name__}: {e}*")
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
