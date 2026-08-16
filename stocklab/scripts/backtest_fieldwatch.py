#!/usr/bin/env python3
"""Point-in-time backtest of the FieldWatch attention mechanism.

Runs the mechanism at many historical as-of dates over the last ~2 years,
using ONLY data available at each date (trailing windows; the panel is
truncated to <= as_of), then measures — mechanically, from the real data —
whether its signals had any FORWARD value.

Why no LLM here: the desk-note layer would "know" the future from its training
data, so it cannot be honestly backtested. This tests the deterministic engine
that feeds it. Every number below is computed from real prices, no narrative.

Hypotheses tested (the mechanism's own claims + the honest questions):
  H1 (system's own claim): field "attention" does NOT predict forward field
     return — rank IC ~ 0. Confirming this validates the system's honesty.
  H2 (regime persistence — the mechanism's actual job): the vol / dispersion
     state it reads should PERSIST (predict forward vol / forward dispersion).
  H3 (direction of the character labels): do STRESS fields continue down or
     mean-revert? do MOMENTUM fields continue up? Report what the data says.
  H4 (field trend-following): does ranking fields by trailing trend predict
     forward field return at all?
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sstats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.data.live import PriceStore, apply_split_adjustments
from stocklab.data.loaders import sanitize_corporate_actions
from stocklab.data.panel import Panel, long_to_panel
from stocklab.fieldwatch import field_snapshot, build_fields, _trailing_pctile
from stocklab.analyst import classify_field
from stocklab.backtest.metrics import newey_west_tstat

ROOT = Path(__file__).resolve().parents[1]
FWD_H = 21          # primary forward horizon (trading days)
FWD_H2 = 63


def load_live_panel() -> Panel:
    store = PriceStore(ROOT / "data_cache" / "live")
    df = store.load()
    panel = long_to_panel(df)
    panel, _ = apply_split_adjustments(panel, store.load_actions())
    panel, _ = sanitize_corporate_actions(panel)
    return panel


def _field_eqw_return(close: pd.DataFrame, members, start, end) -> float:
    cols = [t for t in members if t in close.columns]
    if len(cols) < 3:
        return np.nan
    sub = close[cols].loc[start:end]
    if len(sub) < 2:
        return np.nan
    # fill_method=None: a member with no print contributes NOTHING to the
    # field's forward return, instead of a padded 0% forever — a delisted
    # name must drop out of the outcome, not dampen it
    daily = sub.pct_change(fill_method=None).mean(axis=1)
    return float((1 + daily).prod() - 1)


def _field_fwd_vol(close: pd.DataFrame, members, start, end) -> float:
    cols = [t for t in members if t in close.columns]
    if len(cols) < 3:
        return np.nan
    sub = close[cols].loc[start:end]
    daily = sub.pct_change(fill_method=None).mean(axis=1)
    return float(daily.std() * np.sqrt(252))


def _field_fwd_dispersion(close: pd.DataFrame, members, start, end) -> float:
    cols = [t for t in members if t in close.columns]
    if len(cols) < 3:
        return np.nan
    sub = close[cols].loc[start:end]
    return float(sub.pct_change(fill_method=None).std(axis=1).mean())


def run() -> dict:
    panel = load_live_panel()
    dates = panel.dates
    _broad = ROOT / "data_cache" / "universe" / "broad_sectors.csv"
    _sf = _broad if _broad.exists() else ROOT / "data_cache" / "sp500_sectors.csv"
    sectors = pd.read_csv(_sf).set_index("Symbol")
    fields = build_fields(list(panel.tickers), sectors, min_members=5)

    # as-of grid: every ~10 trading days over the last 2 years, leaving room
    # for the forward window
    start_i = int(np.searchsorted(dates, dates[-1] - pd.Timedelta(days=730)))
    last_i = len(dates) - FWD_H2 - 1
    asof_idx = list(range(start_i, last_i, 10))

    rows = []
    for i in asof_idx:
        as_of = dates[i]
        fwd_end_21 = dates[min(i + FWD_H, len(dates) - 1)]
        fwd_end_63 = dates[min(i + FWD_H2, len(dates) - 1)]
        for name, members in fields.items():
            snap = field_snapshot(panel, members, name, as_of=as_of)
            if snap is None or not np.isfinite(snap.score):
                continue
            c = classify_field(snap)
            fret21 = _field_eqw_return(panel.close, members, dates[i + 1], fwd_end_21)
            fret63 = _field_eqw_return(panel.close, members, dates[i + 1], fwd_end_63)
            fvol = _field_fwd_vol(panel.close, members, dates[i + 1], fwd_end_21)
            fdisp = _field_fwd_dispersion(panel.close, members, dates[i + 1], fwd_end_21)
            rows.append({
                "as_of": as_of, "field": name,
                "attention": snap.score, "character": c["character"],
                "trend_21d": c["trend_21d"],
                "vol_pctile": c["volatility_pctile"],
                "disp_pctile": c["dispersion_pctile"],
                "coh_pctile": c["cohesion_pctile"],
                "fwd_ret_21": fret21, "fwd_ret_63": fret63,
                "fwd_vol_21": fvol, "fwd_disp_21": fdisp,
            })
    df = pd.DataFrame(rows).dropna(subset=["fwd_ret_21"])

    out = {"n_asof_dates": len(asof_idx), "n_obs": int(len(df)),
           "asof_range": [str(dates[start_i].date()), str(dates[last_i].date())],
           "universe": int(len(panel.tickers)), "n_fields": len(fields)}

    # --- per-date cross-field rank IC helper (Newey-West on the daily series)
    def per_date_ic(xcol, ycol):
        ics = []
        for d, g in df.groupby("as_of"):
            gg = g[[xcol, ycol]].dropna()
            if len(gg) >= 8 and gg[xcol].nunique() > 3:
                ics.append(sstats.spearmanr(gg[xcol], gg[ycol]).statistic)
        ics = pd.Series([x for x in ics if np.isfinite(x)])
        return {"mean_ic": float(ics.mean()), "n_dates": int(len(ics)),
                "nw_t": float(newey_west_tstat(ics, lags=3))}

    # H1: attention vs forward return (system claims ~0)
    out["H1_attention_predicts_fwd_ret21"] = per_date_ic("attention", "fwd_ret_21")
    out["H1_attention_predicts_fwd_ret63"] = per_date_ic("attention", "fwd_ret_63")

    # H2: regime persistence — does the state it reads persist?
    out["H2_vol_pctile_predicts_fwd_vol"] = per_date_ic("vol_pctile", "fwd_vol_21")
    out["H2_disp_pctile_predicts_fwd_disp"] = per_date_ic("disp_pctile", "fwd_disp_21")

    # H4: field trend-following — trailing trend vs forward return
    out["H4_trend_predicts_fwd_ret21"] = per_date_ic("trend_21d", "fwd_ret_21")
    out["H4_trend_predicts_fwd_ret63"] = per_date_ic("trend_21d", "fwd_ret_63")

    # H3: character labels — forward behavior by bucket (demeaned per date so
    # we measure RELATIVE field behavior, not the market's drift)
    df["fwd_ret_21_dm"] = df.groupby("as_of")["fwd_ret_21"].transform(lambda s: s - s.mean())
    df["fwd_ret_63_dm"] = df.groupby("as_of")["fwd_ret_63"].transform(lambda s: s - s.mean())
    char = {}
    for c, g in df.groupby("character"):
        char[c] = {
            "n": int(len(g)),
            "fwd_ret_21_demeaned_mean": round(float(g["fwd_ret_21_dm"].mean()), 4),
            "fwd_ret_63_demeaned_mean": round(float(g["fwd_ret_63_dm"].mean()), 4),
            "fwd_ret_21_raw_mean": round(float(g["fwd_ret_21"].mean()), 4),
            "fwd_vol_21_mean": round(float(g["fwd_vol_21"].mean()), 4),
        }
    out["H3_character_forward_behavior"] = char

    # market drift over the sample (context for the raw means)
    out["sample_mean_fwd_ret21_all_fields"] = round(float(df["fwd_ret_21"].mean()), 4)

    df.to_csv(ROOT / "experiments" / "fieldwatch_backtest_rows.csv", index=False)
    return out


if __name__ == "__main__":
    res = run()
    (ROOT / "experiments" / "fieldwatch_backtest.json").write_text(
        json.dumps(res, indent=2, default=float))
    print(json.dumps(res, indent=2, default=float))
