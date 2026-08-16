#!/usr/bin/env python3
"""Horizon sweep: how does the signal/cost trade-off move with the label
horizon? Cheap models only (momentum/ridge/lightgbm) on iteration folds.

Each (horizon x model) is a trial and is recorded in the ledger. The sweep
exists to CHOOSE a horizon on the iteration window — the final holdout run
then evaluates only the chosen configuration once.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.config import ExperimentConfig, LabelConfig, BacktestConfig
from stocklab.data.loaders import load_bundled
from stocklab.runner import run_walk_forward, save_experiment
from run_experiment import build_factories, read_ledger, append_ledger


def main() -> None:
    horizons = [1, 5, 10, 21]
    prior = read_ledger()["total_trials"]
    summary = {}
    for h in horizons:
        # neutralization on: the sweep chooses the horizon for the final run,
        # which will use the neutralized configuration — compare like with like
        cfg = ExperimentConfig(
            label=LabelConfig(horizon=h),
            backtest=BacktestConfig(neutralize=("beta_63",)),
        )
        panel, biases = load_bundled()
        factories = build_factories(["momentum", "ridge", "lightgbm"], cfg)
        print(f"\n=== horizon {h}d ===")
        res = run_walk_forward(panel, factories, cfg, dataset_biases=biases,
                               n_prior_trials=prior, verbose=True)
        out = save_experiment(res, f"experiments/h{h}_sweep", f"horizon={h}d sweep")
        prior = res.n_trials
        for name, rep in res.signal_reports.items():
            bt = res.backtests.get(name)
            summary[f"h{h}/{name}"] = {
                "ic": round(rep.ic_mean, 4),
                "nw_t": round(rep.ic_tstat_nw, 2),
                "net_sharpe": round(bt.stats_net.get("sharpe", float("nan")), 2) if bt else None,
                "breakeven_bps": round(bt.breakeven_cost_bps, 1) if bt else None,
                "turnover": round(bt.avg_daily_turnover, 2) if bt else None,
            }
        append_ledger({
            "at": datetime.now(timezone.utc).isoformat(),
            "out": f"experiments/h{h}_sweep", "models": sorted(res.oos_scores),
            "n_new_trials": len(res.oos_scores), "include_holdout": False,
        })

    print("\n===== SWEEP SUMMARY =====")
    print(json.dumps(summary, indent=2))
    Path("experiments/horizon_sweep_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
