#!/usr/bin/env python3
"""Feature-family combination sweep — the honest version of "find the
combination of inputs that solves this".

PRE-REGISTERED EXPECTATION (written before running):
  30 trials (15 feature-family combinations x {ridge, lightgbm}) on the
  iteration folds. se(iteration IC) ~ 0.0195 with high inter-trial
  correlation (~8-12 effective independent trials). Expected MAXIMUM
  iteration IC if every combination is pure noise: ~ +0.025 to +0.035.
  Therefore: any "winner" at or below ~ +0.03 iteration IC is exactly what
  noise manufactures and proves nothing.

  Candidate bar (for promotion to FRESH-DATA testing only — the holdout is
  spent and stays sealed): NW t >= 2 AND break-even > 10 bps/side.

All 30 trials are appended to the ledger. Scores are beta-neutralized,
matching the pre-registered primary configuration.
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.config import ExperimentConfig, BacktestConfig
from stocklab.data.loaders import load_bundled
from stocklab.data.panel import apply_universe_filters
from stocklab.features.pipeline import build_dataset, FeatureDataset
from stocklab.features.technical import MARKET_FEATURES
from stocklab.validation.walkforward import WalkForwardSplitter
from stocklab.models.baselines import RidgeModel, LightGBMModel
from stocklab.backtest.metrics import (
    _filter_min_names, _spearman_by_date, newey_west_tstat,
)
from stocklab.backtest.engine import backtest_long_short
from stocklab.neutralize import neutralize_scores
from run_experiment import read_ledger, append_ledger

FAMILIES = {
    "MOM": ["mom_21", "mom_63", "mom_126", "mom_12_1", "mom_vol_scaled",
            "mom_consistency", "sma50_sma200", "px_sma50", "pct_from_high_252"],
    "REV": ["ret_1d", "ret_5d", "rsi_14", "boll_z", "macd_hist"],
    "VOLA": ["vol_21", "vol_63", "downside_ratio_63", "max_ret_21", "beta_63"],
    "LIQ": ["log_adv_21", "amihud_21", "vol_trend"],
}


def combos():
    names = list(FAMILIES)
    for r in (1, 2, 3, 4):
        for c in itertools.combinations(names, r):
            yield "+".join(c), sum((FAMILIES[f] for f in c), [])


def main() -> None:
    cfg = ExperimentConfig(backtest=BacktestConfig(neutralize=("beta_63",)))
    panel, _ = load_bundled()
    panel, _ = apply_universe_filters(
        panel, cfg.universe.min_history, cfg.universe.min_price,
        cfg.universe.min_dollar_volume,
    )
    ds_full = build_dataset(panel, cfg)
    labeled = pd.DatetimeIndex(
        ds_full.fwd_ret.dropna().index.get_level_values("date").unique()
    ).sort_values()
    folds = WalkForwardSplitter(cfg).split(labeled)
    cutoff = pd.Timestamp(cfg.split.holdout_start)
    folds = [f for f in folds if f.test_dates[-1] < cutoff]  # HOLDOUT STAYS SEALED
    print(f"{len(folds)} iteration folds; holdout sealed")

    exposures = ds_full.ranked_features[["beta_63"]]
    rows = []
    n_trials = 0
    for combo_name, cols in combos():
        use = cols + MARKET_FEATURES
        ds = FeatureDataset(
            X=ds_full.X[use], y=ds_full.y, fwd_ret=ds_full.fwd_ret,
            feature_names=use, config=cfg, ranked_features=ds_full.ranked_features,
        )
        for model_name, factory in (
            ("ridge", lambda: RidgeModel(alpha=100.0)),
            ("lightgbm", lambda: LightGBMModel(seed=cfg.seed)),
        ):
            parts = []
            for f in folds:
                m = factory()
                m.fit(ds, f.train_dates)
                parts.append(m.predict(ds, f.test_dates))
            scores = pd.concat(parts).sort_index()
            scores = neutralize_scores(scores, exposures)
            df = pd.DataFrame({"s": scores, "f": ds.fwd_ret}).dropna()
            df = _filter_min_names(df, 20)
            ic = _spearman_by_date(df)
            bt = backtest_long_short(
                f"{combo_name}/{model_name}", scores, panel.close,
                horizon=cfg.label.horizon, lag=cfg.label.lag,
                n_quantiles=cfg.backtest.n_quantiles, cost_bps=cfg.backtest.cost_bps,
            )
            row = {
                "combo": combo_name, "model": model_name, "n_features": len(cols),
                "ic": round(float(ic.mean()), 4),
                "nw_t": round(newey_west_tstat(ic, 2 * cfg.label.horizon), 2),
                "net_sharpe": round(bt.stats_net.get("sharpe", np.nan), 2),
                "breakeven_bps": round(bt.breakeven_cost_bps, 1),
            }
            rows.append(row)
            n_trials += 1
            print(f"{combo_name:20s} {model_name:9s} IC={row['ic']:+.4f} "
                  f"t={row['nw_t']:+.2f} netShp={row['net_sharpe']:+.2f} "
                  f"BE={row['breakeven_bps']:+.1f}")

    out = pd.DataFrame(rows).sort_values("ic", ascending=False)
    outdir = Path("experiments/combination_sweep")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "results.csv", index=False)

    best = out.iloc[0]
    noise_max = "+0.025..+0.035"
    verdict = (
        "CANDIDATE (fresh-data test required — holdout is spent)"
        if (best["nw_t"] >= 2 and best["breakeven_bps"] > 10)
        else "NOISE-CONSISTENT: best result is within the pre-registered "
             f"expected-max-of-noise band ({noise_max}) or fails the economic bar"
    )
    summary = {
        "preregistered_noise_max_ic": noise_max,
        "n_trials": n_trials,
        "best": best.to_dict(),
        "verdict": verdict,
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("\nBEST:", dict(best))
    print("VERDICT:", verdict)

    append_ledger({
        "at": datetime.now(timezone.utc).isoformat(),
        "out": str(outdir), "models": ["combination_sweep"],
        "n_new_trials": n_trials, "include_holdout": False,
    })
    print("ledger total:", read_ledger()["total_trials"])


if __name__ == "__main__":
    main()
