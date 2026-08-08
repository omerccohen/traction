"""FieldWatch — an attention allocator over market fields (sectors/industries).

WHAT THIS IS: the buildable core of the "hedge fund advisor" role. It watches
every field for STATISTICALLY UNUSUAL activity — trend, internal dispersion,
volume influx, volatility regime, correlation structure — and ranks fields by
how much is happening, so a human researcher spends attention where the action
is. It mirrors the practitioner loop's step 2-3 (theme candidates + field
verification) from docs/RESEARCH_FUND_PROCESS.md.

WHAT THIS IS NOT: a predictor or a buy list. This project measured field
momentum's forward IC on this data: ~zero-to-negative. Unusualness describes
the PRESENT concentration of activity; the profitable follow-up is human
research (physical indicators, value-chain mapping, bottleneck economics), not
mechanical position-taking. Every briefing carries that framing.

All indicators are trailing percentiles of each field vs ITS OWN history —
point-in-time by construction, unit-free across fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data.panel import Panel


def build_fields(
    tickers,
    sectors_df: pd.DataFrame,
    min_members: int = 5,
    custom: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Assemble the watchable field map.

    Three layers, coarse to fine:
      1. all 11 GICS sectors,
      2. every GICS sub-industry with >= min_members mapped names
         (finer 'fields' like Semiconductors, Biotechnology, Regional Banks),
      3. user-defined custom fields (cross-sector value chains, e.g. a
         'memory chain' of designers+equipment+OEM buyers) — any list of
         tickers becomes a watchable field.
    """
    smap = sectors_df["GICS Sector"]
    sub = sectors_df["GICS Sub-Industry"]
    fields: dict[str, list[str]] = {}
    mapped = [t for t in tickers if t in smap.index]
    for t in mapped:
        fields.setdefault(str(smap[t]), []).append(t)
    sub_counts = sub.reindex(mapped).value_counts()
    for si, n in sub_counts.items():
        if n >= min_members:
            fields[f"{si} [sub]"] = [t for t in mapped if str(sub.get(t)) == si]
    for name, members in (custom or {}).items():
        got = [t for t in members if t in tickers]
        if len(got) >= 3:
            fields[f"{name} [custom]"] = got
    return fields


@dataclass
class FieldSnapshot:
    name: str
    n_members: int
    score: float                    # attention score = mean |z| of indicators
    indicators: dict                # name -> {"value","pctile","note"}
    members_moving: list            # largest recent movers within the field

    def headline(self) -> str:
        hot = [k for k, v in self.indicators.items() if v["pctile"] >= 0.90]
        cool = [k for k, v in self.indicators.items() if v["pctile"] <= 0.10]
        bits = []
        if hot:
            bits.append("elevated: " + ", ".join(hot))
        if cool:
            bits.append("depressed: " + ", ".join(cool))
        return "; ".join(bits) if bits else "nothing unusual"


def _trailing_pctile(series: pd.Series, window: int = 252) -> float:
    """Percentile of the last value within its own trailing window."""
    s = series.dropna()
    if len(s) < window // 2:
        return np.nan
    w = s.iloc[-window:]
    return float((w <= w.iloc[-1]).mean())


def field_snapshot(
    panel: Panel,
    members: list[str],
    name: str,
    as_of: pd.Timestamp | None = None,
    news_net: pd.DataFrame | None = None,
) -> FieldSnapshot | None:
    cols = [t for t in members if t in panel.close.columns]
    if len(cols) < 3:
        return None
    close = panel.close[cols]
    volume = panel.volume[cols]
    if as_of is not None:
        close = close.loc[:as_of]
        volume = volume.loc[:as_of]
    ret1 = close.pct_change()

    eq_idx = ret1.mean(axis=1)                       # equal-weight field return
    ind: dict[str, dict] = {}

    mom21 = float((1 + eq_idx.iloc[-21:]).prod() - 1)
    ind["trend_21d"] = {
        "value": round(mom21, 4),
        "pctile": _trailing_pctile((1 + eq_idx).cumprod().pct_change(21)),
        "note": f"field 21d return {mom21:+.1%}",
    }

    vol21 = eq_idx.rolling(21).std() * np.sqrt(252)
    ind["volatility"] = {
        "value": round(float(vol21.iloc[-1]), 3),
        "pctile": _trailing_pctile(vol21),
        "note": f"field vol {float(vol21.iloc[-1]):.0%} annualized",
    }

    disp = ret1.std(axis=1).rolling(21).mean()
    ind["dispersion"] = {
        "value": round(float(disp.iloc[-1]), 4),
        "pctile": _trailing_pctile(disp),
        "note": "members diverging (winners/losers separating)"
        if _trailing_pctile(disp) > 0.8 else "members moving together",
    }

    dv = (close * volume).sum(axis=1)
    dv_ratio = dv.rolling(21).mean() / dv.rolling(126).mean()
    ind["volume_influx"] = {
        "value": round(float(dv_ratio.iloc[-1]), 3),
        "pctile": _trailing_pctile(dv_ratio),
        "note": "money/attention flowing in" if float(dv_ratio.iloc[-1]) > 1.1
        else ("attention draining" if float(dv_ratio.iloc[-1]) < 0.9 else "normal turnover"),
    }

    # average pairwise correlation over 63d vs its history: a BREAK in
    # co-movement often marks a regime change inside the field
    if len(cols) >= 4:
        r63 = ret1.iloc[-63:]
        cm = r63.corr().to_numpy()
        avg_corr_now = float(cm[np.triu_indices_from(cm, 1)].mean())
        hist = []
        for end in range(126, len(ret1), 21):
            sub = ret1.iloc[max(0, end - 63):end]
            if len(sub) >= 40:
                c = sub.corr().to_numpy()
                hist.append(c[np.triu_indices_from(c, 1)].mean())
        if hist:
            pct = float((np.array(hist) <= avg_corr_now).mean())
            ind["cohesion"] = {
                "value": round(avg_corr_now, 3),
                "pctile": pct,
                "note": "field trading as one block (macro/theme-driven)"
                if pct > 0.8 else ("stocks decoupling (idiosyncratic phase)"
                                   if pct < 0.2 else "normal co-movement"),
            }

    if news_net is not None:
        nn = news_net[[c for c in cols if c in news_net.columns]]
        if nn.shape[1] >= 2:
            if as_of is not None:
                nn = nn.loc[:as_of]
            intensity = nn.notna().sum(axis=1).rolling(21).mean()
            sent = nn.mean(axis=1).rolling(10, min_periods=3).mean()
            ind["news_intensity"] = {
                "value": round(float(intensity.iloc[-1]), 2),
                "pctile": _trailing_pctile(intensity),
                "note": "unusual news flow volume" if _trailing_pctile(intensity) > 0.85
                else "normal news flow",
            }
            if np.isfinite(sent.iloc[-1]):
                ind["news_tone"] = {
                    "value": round(float(sent.iloc[-1]), 3),
                    "pctile": _trailing_pctile(sent),
                    "note": "tone of recent coverage (descriptive only — "
                            "proven non-predictive on this data)",
                }

    score = float(np.nanmean([abs(v["pctile"] - 0.5) * 2 for v in ind.values()]))

    m21 = close.pct_change(21).iloc[-1].sort_values()
    movers = [f"{t} {m21[t]:+.0%}" for t in list(m21.index[:2]) + list(m21.index[-2:])]

    return FieldSnapshot(
        name=name, n_members=len(cols), score=round(score, 3),
        indicators=ind, members_moving=movers,
    )


def briefing(snapshots: list[FieldSnapshot], as_of, top_n: int = 8) -> str:
    snaps = sorted([s for s in snapshots if s], key=lambda s: -s.score)
    lines = [
        f"# FieldWatch briefing — as of {pd.Timestamp(as_of).date()}",
        "",
        "> Attention allocation, not advice. 'Unusual' means activity is",
        "> concentrating — it does NOT mean 'will go up' (field momentum's",
        "> forward IC on this data measured ~zero). The profitable follow-up",
        "> is the research loop: physical indicators for the flagged field,",
        "> value-chain mapping, bottleneck economics — see",
        "> docs/RESEARCH_FUND_PROCESS.md steps 3-5.",
        "",
    ]
    for s in snaps[:top_n]:
        lines.append(f"## {s.name}  (attention score {s.score:.2f}, {s.n_members} names)")
        lines.append("")
        lines.append(f"**{s.headline()}**")
        lines.append("")
        for k, v in sorted(s.indicators.items(), key=lambda kv: -abs(kv[1]['pctile'] - 0.5)):
            bar = "#" * int(round(v["pctile"] * 10))
            lines.append(f"- {k:15s} p{v['pctile']*100:3.0f} {bar:<10s} {v['note']}")
        lines.append(f"- extremes 21d: {', '.join(s.members_moving)}")
        lines.append("")
        lines.append("**Next (human) step:** what physical series would confirm or kill a "
                     "thesis here? (orders/pricing/inventory/capacity for this field)")
        lines.append("")
    return "\n".join(lines)
