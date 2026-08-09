"""Analysis pack: the deterministic bridge between the raw FieldWatch/indicator
data and the hedge-fund-analyst desk note.

Design principle: the LLM analyst must reason over FACTS, not re-derive them.
This module extracts — purely mechanically, from real data — the regime state,
the ranked fields with their signatures, cross-cutting patterns, and notable
single-stock dislocations. The analyst subagent then prioritizes and explains;
it never invents a number this module didn't compute.

Honesty is structural: every field's "attention" is explicitly NOT a
direction; the pack labels whether elevated activity is constructive (rising
trend + inflow) or stress (falling trend + high vol), so the analyst can't
launder attention into a buy call.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

import numpy as np
import pandas as pd

from .fieldwatch import FieldSnapshot


def _pctile(ind: dict, key: str):
    v = ind.get(key)
    return None if v is None else v.get("pctile")


def classify_field(s: FieldSnapshot) -> dict:
    """Turn a field snapshot into a labeled, human-meaningful summary."""
    ind = s.indicators
    trend_p = _pctile(ind, "trend_21d")
    trend_ret = ind.get("trend_21d", {}).get("value")
    vol_p = _pctile(ind, "volatility")
    disp_p = _pctile(ind, "dispersion")
    coh_p = _pctile(ind, "cohesion")
    vol_in_p = _pctile(ind, "volume_influx")

    # character of the activity
    rising = trend_ret is not None and trend_ret > 0.02
    falling = trend_ret is not None and trend_ret < -0.02
    hot_vol = vol_p is not None and vol_p >= 0.85
    inflow = vol_in_p is not None and vol_in_p >= 0.85
    draining = vol_in_p is not None and vol_in_p <= 0.15
    stockpicker = (disp_p is not None and disp_p >= 0.8) and (coh_p is not None and coh_p <= 0.2)

    if hot_vol and falling:
        character = "STRESS"
        headline = "under pressure — falling with elevated volatility"
    elif rising and inflow:
        character = "MOMENTUM"
        headline = "attracting money on a rising trend"
    elif stockpicker:
        character = "DISPERSION"
        headline = "splitting into winners and losers (stock-picker's phase)"
    elif draining and not hot_vol:
        character = "QUIET"
        headline = "activity draining — calm, being ignored"
    elif hot_vol:
        character = "VOLATILE"
        headline = "unusually volatile without a clear direction"
    else:
        character = "MIXED"
        headline = "mixed signals"

    return {
        "name": s.name,
        "n_members": s.n_members,
        "attention": s.score,
        "character": character,
        "headline": headline,
        "trend_21d": None if trend_ret is None else round(trend_ret, 4),
        "volatility_pctile": vol_p,
        "dispersion_pctile": disp_p,
        "cohesion_pctile": coh_p,
        "movers": s.members_moving,
        "flags": s.headline(),
    }


@dataclass
class AnalysisPack:
    as_of: str
    source: str
    universe_size: int
    regime: dict
    top_fields: list
    cross_cutting: list
    dislocations: list
    caveats: list = dc_field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _regime_from_indicators(inds, states: dict) -> dict:
    """Compact market-regime read from the live indicator statuses."""
    reg = {"vol": None, "trend": None, "valuation": None,
           "triggered": [], "elevated": []}
    for ind in inds:
        st = ind.status(states.get(ind.name, "cache"))
        if st.threshold_state == "TRIGGERED":
            reg["triggered"].append(f"{ind.name}: {st.threshold_note}")
        elif st.threshold_state == "ELEVATED":
            reg["elevated"].append(f"{ind.name}: {st.threshold_note}")
        if ind.name == "vix_level" and st.pctile_5y is not None:
            band = ("calm" if st.pctile_5y < 0.4 else
                    "stressed" if st.pctile_5y > 0.8 else "normal")
            reg["vol"] = {"value": st.latest_value, "pctile": st.pctile_5y,
                          "band": band, "age_days": st.data_age_days}
        if ind.name == "sp500_trend_12m" and st.transformed_value is not None:
            reg["trend"] = {"value": st.transformed_value,
                            "band": "uptrend" if st.transformed_value > 0 else "downtrend",
                            "age_days": st.data_age_days}
        if ind.name == "sp500_pe10" and st.latest_value is not None:
            reg["valuation"] = {"value": st.latest_value, "pctile": st.pctile_5y,
                                "age_days": st.data_age_days}
    return reg


def _cross_cutting(classified: list, all_snaps: list) -> tuple[list, list]:
    """Patterns spanning fields + notable single-stock dislocations."""
    patterns = []

    # market breadth: how many fields are in the stock-picker (decoupled) phase?
    n_disp = sum(1 for c in classified if c["character"] == "DISPERSION")
    n_stress = sum(1 for c in classified if c["character"] == "STRESS")
    total = max(len(classified), 1)
    if n_disp / total >= 0.3:
        patterns.append(
            f"Breadth: {n_disp}/{total} top fields are in a stock-picker's phase "
            "(names decoupling) — a selection market, not a beta market.")
    if n_stress >= 2:
        stressed = [c["name"] for c in classified if c["character"] == "STRESS"][:4]
        patterns.append(f"Stress cluster: {', '.join(stressed)} under pressure together.")

    # related-field confirmation: a sector and its sub-industry both flagged same way
    names = {c["name"]: c for c in classified}
    for c in classified:
        base = c["name"].split(" [")[0]
        for other in classified:
            if other is c:
                continue
            ob = other["name"].split(" [")[0]
            if base != ob and (base in ob or ob in base) \
               and c["character"] == other["character"] == "STRESS":
                patterns.append(
                    f"Confirmed field-level move: '{c['name']}' and '{other['name']}' "
                    "both stressed — a real sector signal, not one-name noise.")
                break

    # single-stock dislocations: |21d move| >= 20% among all snapshots' extremes
    dislocations = []
    seen = set()
    for s in all_snaps:
        for m in s.members_moving:
            try:
                tkr, pct = m.rsplit(" ", 1)
                val = float(pct.strip("%")) / 100
            except Exception:
                continue
            if abs(val) >= 0.20 and tkr not in seen:
                seen.add(tkr)
                dislocations.append({"ticker": tkr, "move_21d": round(val, 3),
                                     "field": s.name})
    dislocations.sort(key=lambda d: -abs(d["move_21d"]))
    # dedupe patterns
    patterns = list(dict.fromkeys(patterns))
    return patterns, dislocations[:12]


def build_analysis_pack(
    snaps: list[FieldSnapshot],
    inds,
    indicator_states: dict,
    as_of,
    source: str,
    universe_size: int,
    top_n: int = 6,
    caveats: list | None = None,
) -> AnalysisPack:
    ranked = sorted([s for s in snaps if s], key=lambda s: -s.score)
    top = [classify_field(s) for s in ranked[:top_n]]
    patterns, dislocations = _cross_cutting(top, ranked)
    regime = _regime_from_indicators(inds, indicator_states)
    return AnalysisPack(
        as_of=str(pd.Timestamp(as_of).date()),
        source=source,
        universe_size=universe_size,
        regime=regime,
        top_fields=top,
        cross_cutting=patterns,
        dislocations=dislocations,
        caveats=caveats or [
            "'Attention' marks unusual activity, NOT direction — field momentum's "
            "forward IC on this data measured ~zero.",
            "This is research triage (where to look), not buy/sell advice.",
            "Universe is current-constituent (survivorship-flagged); "
            "corporate actions handled heuristically, not from an exact event feed.",
        ],
    )
