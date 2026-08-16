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
    """Percentile of the last value within its own trailing window.

    The CURRENT value must itself be real. dropna()-then-last silently
    substituted the most recent valid reading — a weeks-old number presented
    as today's percentile when the current value was missing.
    """
    if len(series) == 0 or not np.isfinite(series.iloc[-1]):
        return np.nan
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
    # fill_method=None: a day with no print is UNKNOWN, not "unchanged".
    # pandas' default pad turned every stale/halted/delisted member into an
    # endless run of 0.0% returns — deflating vol and dispersion, and letting
    # a field with no data at all ship a calm-looking snapshot.
    ret1 = close.pct_change(fill_method=None)

    eq_idx = ret1.mean(axis=1)                       # equal-weight field return
    ind: dict[str, dict] = {}

    tail21 = eq_idx.iloc[-21:]
    # prod() over an all-NaN window returns 1.0 (min_count=0), i.e. a dead
    # field would read "+0.0%"; require at least one real day.
    mom21 = float((1 + tail21).prod() - 1) if tail21.notna().any() else np.nan
    ind["trend_21d"] = {
        "value": round(mom21, 4),
        "pctile": _trailing_pctile(
            (1 + eq_idx).cumprod().pct_change(21, fill_method=None)),
        "note": f"field 21d return {mom21:+.1%}" if np.isfinite(mom21)
        else "no member printed in the last 21 days — return unknown",
    }

    vol21 = eq_idx.rolling(21).std() * np.sqrt(252)
    vol_last = float(vol21.iloc[-1])
    ind["volatility"] = {
        "value": round(vol_last, 3),
        "pctile": _trailing_pctile(vol21),
        "note": f"field vol {vol_last:.0%} annualized" if np.isfinite(vol_last)
        else "field vol unknown — data gaps in the last 21 days",
    }

    disp = ret1.std(axis=1).rolling(21).mean()
    disp_p = _trailing_pctile(disp)
    ind["dispersion"] = {
        "value": round(float(disp.iloc[-1]), 4),
        "pctile": disp_p,
        "note": "dispersion unknown — data gaps" if not np.isfinite(disp_p)
        else ("members diverging (winners/losers separating)"
              if disp_p > 0.8 else "members moving together"),
    }

    # min_count=1: a day where NO member has data is unknown dollar volume,
    # not zero — sum's default turned pre-listing history into a phantom
    # zero-volume era that manufactured extreme influx percentiles.
    dv = (close * volume).sum(axis=1, min_count=1)
    dv_ratio = dv.rolling(21).mean() / dv.rolling(126).mean()
    dv_last = float(dv_ratio.iloc[-1])
    ind["volume_influx"] = {
        "value": round(dv_last, 3),
        "pctile": _trailing_pctile(dv_ratio),
        "note": "turnover unknown — data gaps" if not np.isfinite(dv_last)
        else ("money/attention flowing in" if dv_last > 1.1
              else ("attention draining" if dv_last < 0.9 else "normal turnover")),
    }

    # average pairwise correlation over 63d vs its history: a BREAK in
    # co-movement often marks a regime change inside the field.
    # History windows must NOT overlap the current 63d (self-comparison) and
    # there must be enough of them for a percentile to mean anything —
    # audit F2: a single comparison point made pctile ∈ {0,1} and let one
    # data point rocket a field to the top of the briefing.
    # A pair contributes nothing when one leg has no history in the window (a
    # later IPO, a halt), and pandas .corr() returns NaN for it. Taking a plain
    # .mean() over the triangle then makes the WHOLE window NaN, and `NaN <= x`
    # is False — so every unusable window silently counted as "history above
    # today" and dragged the percentile to the floor. Measured 2026-08-13:
    # 129 of 130 fields had NaN history, and in the large fields (Technology,
    # Industrials, Finance, Health Care) ALL 95 history points were NaN, so the
    # percentile was 0.000 out of zero valid comparisons and the field was
    # labelled "stocks decoupling". 109 of 130 fields carried that label; only
    # 40 deserve it, and several invert outright — Basic Materials went 0.00 ->
    # 0.965 ("trading as one block"), Semiconductors 0.00 -> 0.825. That number
    # is what produced the "selection market, not a beta market" desk-note
    # headline. Average over the pairs that exist, and drop unusable windows
    # rather than counting them as evidence.
    def _pair_mean(c: np.ndarray) -> float:
        v = c[np.triu_indices_from(c, 1)]
        return float(np.nanmean(v)) if np.isfinite(v).any() else np.nan

    # min_periods=40 (mirroring the >=40-row history rule): a pair whose legs
    # share fewer than 40 real days is noise, not a correlation — and a field
    # whose data STOPPED mid-window must read unknown, not ship a weeks-old
    # correlation as today's.
    if len(cols) >= 4:
        r63 = ret1.iloc[-63:]
        avg_corr_now = _pair_mean(r63.corr(min_periods=40).to_numpy())
        hist = []
        for end in range(126, len(ret1) - 63, 21):
            sub = ret1.iloc[max(0, end - 63):end]
            if len(sub) >= 40:
                h = _pair_mean(sub.corr(min_periods=40).to_numpy())
                if np.isfinite(h):
                    hist.append(h)
        if len(hist) >= 8 and np.isfinite(avg_corr_now):
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

    devs = np.array([abs(v["pctile"] - 0.5) * 2 for v in ind.values()])
    score = float(np.nanmean(devs)) if np.isfinite(devs).any() else np.nan

    # Extremes must never be contaminated by MISSING data. Vendors publish some
    # tickers a day late, so on any given as_of a slice of the universe has no
    # print yet — and NaN sorts LAST in pandas, which silently promoted
    # not-yet-reported names to "biggest gainer" in the movers list the analyst
    # reads. Tolerate a few days of per-ticker lag (measure each name from its
    # own last real price), then drop anything still unknown.
    # fill_method=None is load-bearing: pct_change's own default pad forward-
    # filled PAST the deliberate 3-day tolerance, so ".dropna()" never dropped
    # anything and names halted for weeks reappeared as "+0%" movers.
    m21 = (close.ffill(limit=3).pct_change(21, fill_method=None)
           .iloc[-1].dropna().sort_values())
    if len(m21) >= 4:
        picks = list(m21.index[:2]) + list(m21.index[-2:])
    else:
        picks = list(m21.index)
    movers = [f"{t} {m21[t]:+.0%}" for t in picks]

    return FieldSnapshot(
        name=name, n_members=len(cols), score=round(score, 3),
        indicators=ind, members_moving=movers,
    )


def briefing(snapshots: list[FieldSnapshot], as_of, top_n: int = 8) -> str:
    # A NaN score must not enter the sort: NaN comparisons break the ordering
    # and can seat an unmeasurable field above real ones.
    snaps = sorted([s for s in snapshots if s and np.isfinite(s.score)],
                   key=lambda s: -s.score)
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
        def _dev(kv):
            p = kv[1]["pctile"]
            return -abs(p - 0.5) if np.isfinite(p) else 1.0  # unknowns sort last
        for k, v in sorted(s.indicators.items(), key=_dev):
            p = v["pctile"]
            if np.isfinite(p):
                bar = "#" * int(round(p * 10))
                lines.append(f"- {k:15s} p{p*100:3.0f} {bar:<10s} {v['note']}")
            else:
                lines.append(f"- {k:15s} p ——  {'':<10s} {v['note']}")
        lines.append(f"- extremes 21d: {', '.join(s.members_moving)}")
        lines.append("")
        lines.append("**Next (human) step:** what physical series would confirm or kill a "
                     "thesis here? (orders/pricing/inventory/capacity for this field)")
        lines.append("")
    return "\n".join(lines)
