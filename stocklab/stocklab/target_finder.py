"""Target-finder: turn the analyst's research questions into candidate stock
GROUPS, grounded in the real universe.

The hedge-fund desk note asks questions ("is the AI-power-demand theme sorting
utility winners from losers? check datacenter power contracts"). This module
gives the target-finder subagent the RAW MATERIAL to answer them without
hallucinating tickers: for any theme it can pull the actual companies in the
relevant fields, split into who's moving up vs down, plus keyword search across
the whole 2,969-name universe.

Honest framing (enforced in the prompt, docs/TARGET_FINDER_PROMPT.md): the
output is a RESEARCH TARGET LIST — "if this thesis holds, these are the
companies most exposed, and here is what we could actually verify" — never a
buy list. The whole project proved direction is unpredictable; this maps the
value chain and gathers evidence, it does not call winners.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data.panel import Panel


def member_moves(panel: Panel, tickers: list[str], as_of, lookback=(21, 63)) -> pd.DataFrame:
    """Real recent performance for a set of tickers, as of a date."""
    cols = [t for t in tickers if t in panel.close.columns]
    if not cols:
        return pd.DataFrame(columns=["ticker", "ret_21d", "ret_63d", "last_close"])
    ts_as_of = pd.Timestamp(as_of)
    close = panel.close[cols].loc[:ts_as_of]
    rows = []
    for t in cols:
        s = close[t].dropna()
        if len(s) < max(lookback) + 1:
            continue
        row = {
            "ticker": t,
            "ret_21d": round(float(s.iloc[-1] / s.iloc[-1 - lookback[0]] - 1), 4),
            "ret_63d": round(float(s.iloc[-1] / s.iloc[-1 - lookback[1]] - 1), 4),
            "last_close": round(float(s.iloc[-1]), 2),
        }
        # dropna() anchors the window at the ticker's LAST TRADE, not at
        # as_of — a delisted/halted name would ship a months-old price next
        # to current ones with nothing marking it. Flag, don't hide.
        days_stale = (ts_as_of - s.index[-1]).days
        if days_stale > 5:
            row["stale"] = (f"last price {s.index[-1].date()}, "
                            f"{days_stale} days before as_of")
        rows.append(row)
    if not rows:
        # every candidate lacked enough history: sort_values on a columnless
        # frame raised KeyError and killed the whole targets stage
        return pd.DataFrame(columns=["ticker", "ret_21d", "ret_63d", "last_close"])
    df = pd.DataFrame(rows).sort_values("ret_21d", ascending=False)
    return df


def keyword_universe_search(sectors_df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    """Find companies across the whole universe whose industry or name matches
    any keyword (case-insensitive). Returns ticker + name + sector + industry."""
    cols = {c.lower(): c for c in sectors_df.columns}
    name_col = cols.get("name")
    ind_col = cols.get("gics sub-industry") or cols.get("industry")
    sec_col = cols.get("gics sector") or cols.get("sector")
    hay = sectors_df.index.astype(str)
    text = sectors_df[ind_col].fillna("").astype(str)
    if name_col:
        text = text + " " + sectors_df[name_col].fillna("").astype(str)
    text = text.str.lower()
    mask = pd.Series(False, index=sectors_df.index)
    for kw in keywords:
        mask = mask | text.str.contains(kw.lower(), regex=False)
    hit = sectors_df[mask]
    out = pd.DataFrame({
        "ticker": hit.index,
        "sector": hit[sec_col] if sec_col else "",
        "industry": hit[ind_col] if ind_col else "",
    })
    if name_col:
        out["name"] = hit[name_col].values
    return out.reset_index(drop=True)


def _records(df: pd.DataFrame) -> list[dict]:
    """to_dict('records') minus NaN cells (an absent flag is absent, not nan)."""
    return [{k: v for k, v in r.items()
             if not (isinstance(v, float) and pd.isna(v))}
            for r in df.to_dict("records")]


def field_dossier(panel: Panel, name: str, members: list[str], as_of, top_k: int = 8) -> dict:
    """A field's real winners/losers as of a date — the evidence base for a
    thesis about that field."""
    mv = member_moves(panel, members, as_of)
    if mv.empty:
        # 0 here means "no member could be measured" — which includes a failed
        # name lookup upstream; say so instead of shipping a bare zero
        return {"field": name, "n": 0, "n_members_total": len(members),
                "note": "no member had enough price history to measure"}
    # head(k)/tail(k) OVERLAP when a field has fewer than 2k measured members:
    # 3 of 4 dossiers on 2026-08-13 listed the same tickers as both winner and
    # loser (16 rows, 10 companies). Cap each list at half the field so they
    # are provably disjoint.
    k = min(top_k, len(mv) // 2)
    out = {
        "field": name,
        "n": int(len(mv)),
        "n_members_total": len(members),
        "field_median_ret_21d": round(float(mv["ret_21d"].median()), 4),
        "winners": _records(mv.head(k)),
        "losers": _records(mv.tail(k).iloc[::-1]),
    }
    if len(mv) < len(members):
        out["note"] = (f"{len(members) - len(mv)} of {len(members)} members "
                       "not measured (insufficient price history)")
    if k < top_k:
        out["lists_note"] = (f"small field: top/bottom {k} shown so the two "
                             "lists cannot overlap")
    return out


def build_target_input(pack: dict, panel: Panel, fields: dict, sectors_df: pd.DataFrame,
                       as_of, top_fields: int = 4) -> dict:
    """Assemble the raw material the target-finder subagent reasons over:
    for the top-attention fields, the real winners/losers; plus the whole
    field roster so the agent can pull related value-chain fields by name."""
    top = pack.get("top_fields", [])[:top_fields]
    dossiers = []
    for f in top:
        members = fields.get(f["name"]) or fields.get(f["name"] + " [sub]") or []
        if not members:
            # pack names may drop the [sub]/[custom] suffix; match loosely
            for k, v in fields.items():
                if k.split(" [")[0] == f["name"].split(" [")[0]:
                    members = v
                    break
        dossiers.append({
            "field": f["name"], "character": f["character"],
            "attention": f["attention"],
            **{k: v for k, v in field_dossier(panel, f["name"], members, as_of).items()
               if k not in ("field",)},
        })
    roster = sorted({k.split(" [")[0] for k in fields})
    return {
        "as_of": pack.get("as_of"),
        "regime": pack.get("regime"),
        "field_dossiers": dossiers,
        "all_fields": roster,
        "universe_size": pack.get("universe_size"),
    }
