#!/usr/bin/env python3
"""Run the walk-forward experiment on the bundled real dataset.

Usage:
    python scripts/run_experiment.py --models momentum,ridge,lightgbm --out experiments/v1_baselines
    python scripts/run_experiment.py --models all --out experiments/v2_full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.config import ExperimentConfig
from stocklab.data.loaders import load_bundled
from stocklab.runner import run_walk_forward, run_leakage_suite, save_experiment


def build_factories(names: list[str], cfg: ExperimentConfig) -> dict:
    from stocklab.models.baselines import MomentumBaseline, RidgeModel, LightGBMModel

    factories = {}
    if "momentum" in names:
        factories["momentum_12_1"] = lambda ds: MomentumBaseline()
    if "ridge" in names:
        factories["ridge"] = lambda ds: RidgeModel(alpha=100.0)
    if "lightgbm" in names:
        factories["lightgbm"] = lambda ds: LightGBMModel(seed=cfg.seed)

    deep = {"mlp", "lstm", "transformer"} & set(names)
    if deep:
        from stocklab.models.deep import KerasMLP, KerasLSTM, KerasTransformer
        from stocklab.models.sequences import SequenceStore

        store_holder = {}

        def get_store(ds):
            if "store" not in store_holder:
                store_holder["store"] = SequenceStore(
                    ds, list(cfg.sequence.features), cfg.sequence.length
                )
            return store_holder["store"]

        if "mlp" in names:
            factories["mlp"] = lambda ds: KerasMLP(n_seeds=3)
        if "lstm" in names:
            factories["lstm"] = lambda ds: KerasLSTM(
                get_store(ds), n_seeds=2, train_stride=cfg.sequence.train_stride
            )
        if "transformer" in names:
            factories["transformer"] = lambda ds: KerasTransformer(
                get_store(ds), n_seeds=2, train_stride=cfg.sequence.train_stride
            )
    return factories


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="momentum,ridge,lightgbm")
    ap.add_argument("--out", default="experiments/latest")
    ap.add_argument("--title", default="StockLab walk-forward experiment")
    ap.add_argument("--skip-leakage", action="store_true")
    ap.add_argument("--prior-trials", type=int, default=0,
                    help="configs evaluated before this run (for Sharpe deflation)")
    args = ap.parse_args()

    names = (
        ["momentum", "ridge", "lightgbm", "mlp", "lstm", "transformer"]
        if args.models == "all" else [m.strip() for m in args.models.split(",")]
    )

    cfg = ExperimentConfig()
    panel, biases = load_bundled()
    factories = build_factories(names, cfg)
    print(f"models: {list(factories)}")

    res = run_walk_forward(panel, factories, cfg, dataset_biases=biases,
                           n_prior_trials=args.prior_trials)
    if not args.skip_leakage:
        panel2, _ = load_bundled()
        res.leakage_results = run_leakage_suite(panel2, cfg)

    out = save_experiment(res, args.out, args.title)
    print(f"\nsaved -> {out}/report.md")
    for name, rep in sorted(res.signal_reports.items(), key=lambda kv: -kv[1].ic_mean):
        print(f"  {name:14s} IC={rep.ic_mean:+.4f} ICIR={rep.icir:+.3f} t={rep.ic_tstat_nw:+.2f}")


if __name__ == "__main__":
    main()
