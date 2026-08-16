#!/usr/bin/env python3
"""Pre-committed sensitivity checks on the FINAL holdout result
(docs/PREREGISTRATION.md). Runs on the primary configuration's scores no
matter what the headline said:

  1. per-month holdout rank IC
  2. holdout IC with January-2018 dropped (window-boundary momentum melt-up)
  3. drop-top-5-|IC|-days IC (concentration)
  4. IC by horizon incl. 1d (leakage signature check)
  5. deflated Sharpe vs the full trial ledger

Emits experiments/final/sensitivity.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.config import ExperimentConfig
from stocklab.data.loaders import load_bundled
from stocklab.data.panel import apply_universe_filters
from stocklab.labels import forward_returns
from stocklab.backtest.metrics import _filter_min_names, _spearman_by_date, newey_west_tstat

PRIMARY = "lightgbm"
FINAL_DIR = Path(__file__).resolve().parents[1] / "experiments" / "final"


def ic_series(scores: pd.Series, fwd: pd.Series) -> pd.Series:
    df = pd.DataFrame({"s": scores, "f": fwd}).dropna()
    df = _filter_min_names(df, 20)
    return _spearman_by_date(df)


def main() -> None:
    cfg = ExperimentConfig()
    hs = pd.Timestamp(cfg.split.holdout_start)

    scores = pd.read_csv(FINAL_DIR / f"scores_{PRIMARY}.csv.gz",
                         parse_dates=["date"]).set_index(["date", "ticker"])["score"]
    panel, _ = load_bundled()
    panel, _ = apply_universe_filters(
        panel, cfg.universe.min_history, cfg.universe.min_price, cfg.universe.min_dollar_volume
    )
    fwd = forward_returns(panel, cfg.label.horizon, cfg.label.lag).stack()
    fwd.index.names = ["date", "ticker"]

    s_hold = scores[scores.index.get_level_values("date") >= hs]
    ic = ic_series(s_hold, fwd)
    lines = [
        "# Pre-committed sensitivity checks — primary configuration "
        f"({PRIMARY}, neutralized, h={cfg.label.horizon})",
        "",
        f"Holdout window: {ic.index.min().date()} .. {ic.index.max().date()} "
        f"({len(ic)} scored days)",
        "",
        f"- holdout rank IC: **{ic.mean():+.4f}** (NW t = {newey_west_tstat(ic, 2*cfg.label.horizon):+.2f})",
    ]

    by_month = ic.groupby(ic.index.to_period("M")).agg(["mean", "count"])
    lines += ["", "## Per-month IC", "", "| month | IC | days |", "|---|---|---|"]
    for m, row in by_month.iterrows():
        lines.append(f"| {m} | {row['mean']:+.4f} | {int(row['count'])} |")

    no_jan = ic[ic.index < "2018-01-01"]
    lines += [
        "",
        "## January-2018 boundary check",
        "",
        f"- IC without Jan/Feb-2018: **{no_jan.mean():+.4f}** "
        f"(NW t = {newey_west_tstat(no_jan, 2*cfg.label.horizon):+.2f}, {len(no_jan)} days)",
        f"- IC of 2018 days alone: {ic[ic.index >= '2018-01-01'].mean():+.4f} "
        f"({len(ic[ic.index >= '2018-01-01'])} days) — the data ends 2018-02-07, at a "
        "momentum melt-up peak; the Feb-2018 reversal is outside the sample.",
    ]

    drop5 = ic.drop(ic.abs().sort_values().index[-5:])
    lines += [
        "",
        "## Concentration",
        "",
        f"- IC with the 5 largest-|IC| days removed: **{drop5.mean():+.4f}** "
        f"(vs {ic.mean():+.4f} with them)",
    ]

    lines += ["", "## IC by horizon (holdout, leakage-signature check)", ""]
    for h in (1, 5, 10, 21):
        fh = forward_returns(panel, h, cfg.label.lag).stack()
        fh.index.names = ["date", "ticker"]
        ich = ic_series(s_hold, fh)
        lines.append(f"- {h:2d}d: {ich.mean():+.4f}")

    led = json.loads((FINAL_DIR.parent / "trial_ledger.json").read_text())
    res = json.loads((FINAL_DIR / "results.json").read_text())
    dsr = res.get("holdout_backtests", {}).get(PRIMARY, {}).get("stats_net", {})
    lines += [
        "",
        "## Trial accounting",
        "",
        f"- ledger total (incl. this run): **{led['total_trials']}** configurations",
        f"- primary holdout net Sharpe: {dsr.get('sharpe', float('nan')):+.2f}; "
        f"deflated-Sharpe prob is reported in results.json against this ledger.",
    ]

    out = FINAL_DIR / "sensitivity.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
