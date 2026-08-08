#!/usr/bin/env python3
"""Run the walk-forward experiment on the bundled real dataset.

Usage:
    python scripts/run_experiment.py --models momentum,ridge,lightgbm --out experiments/v1_baselines
    python scripts/run_experiment.py --models all --out experiments/v2_full
    python scripts/run_experiment.py --models all --include-holdout --out experiments/final   # ONCE

Trial accounting: every run appends its model count to experiments/trial_ledger.json
and reads the accumulated total as the default prior — so the deflated Sharpe
always answers for the full search history, not just the last run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.config import ExperimentConfig
from stocklab.data.loaders import load_bundled
from stocklab.runner import run_walk_forward, run_leakage_suite, save_experiment

LEDGER = Path(__file__).resolve().parents[1] / "experiments" / "trial_ledger.json"
HOLDOUT_MARKER = Path(__file__).resolve().parents[1] / "experiments" / "HOLDOUT_OPENED.json"


def read_ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"total_trials": 0, "runs": []}


def append_ledger(entry: dict) -> None:
    led = read_ledger()
    led["total_trials"] += entry["n_new_trials"]
    led["runs"].append(entry)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(led, indent=2))


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

        # cache keyed by dataset identity — a bare singleton silently served
        # stale features when factories were reused across datasets (m2)
        store_cache: dict[int, SequenceStore] = {}

        def get_store(ds):
            key = id(ds)
            if key not in store_cache:
                store_cache.clear()
                store_cache[key] = SequenceStore(
                    ds, list(cfg.sequence.features), cfg.sequence.length
                )
            return store_cache[key]

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
    ap.add_argument("--prior-trials", type=int, default=None,
                    help="override the trial ledger (default: read accumulated total)")
    ap.add_argument("--include-holdout", action="store_true",
                    help="FINAL RUN ONLY: also evaluate the locked holdout folds")
    args = ap.parse_args()

    names = (
        ["momentum", "ridge", "lightgbm", "mlp", "lstm", "transformer"]
        if args.models == "all" else [m.strip() for m in args.models.split(",")]
    )

    prior = args.prior_trials if args.prior_trials is not None else read_ledger()["total_trials"]

    if args.include_holdout:
        if HOLDOUT_MARKER.exists():
            opened = json.loads(HOLDOUT_MARKER.read_text())
            print("=" * 72)
            print(f"WARNING: the holdout was ALREADY OPENED {len(opened['opens'])} time(s), "
                  f"first at {opened['opens'][0]['at']}.")
            print("Holdout results below are no longer a first look — treat them as")
            print("validation, not as untouched out-of-sample evidence.")
            print("=" * 72)
        else:
            opened = {"opens": []}
        opened["opens"].append({
            "at": datetime.now(timezone.utc).isoformat(),
            "models": names, "prior_trials": prior, "out": args.out,
        })
        HOLDOUT_MARKER.parent.mkdir(parents=True, exist_ok=True)
        HOLDOUT_MARKER.write_text(json.dumps(opened, indent=2))

    cfg = ExperimentConfig()
    panel, biases = load_bundled()
    factories = build_factories(names, cfg)
    print(f"models: {list(factories)} | prior trials: {prior}")

    res = run_walk_forward(panel, factories, cfg, dataset_biases=biases,
                           n_prior_trials=prior,
                           include_holdout=args.include_holdout)
    if not args.skip_leakage:
        panel2, _ = load_bundled()
        res.leakage_results = run_leakage_suite(panel2, cfg)

    out = save_experiment(res, args.out, args.title)
    append_ledger({
        "at": datetime.now(timezone.utc).isoformat(),
        "out": str(args.out), "models": sorted(res.oos_scores),
        "n_new_trials": len(res.oos_scores),
        "include_holdout": args.include_holdout,
    })
    print(f"\nsaved -> {out}/report.md")
    for name, rep in sorted(res.signal_reports.items(), key=lambda kv: -kv[1].ic_mean):
        print(f"  {name:14s} IC={rep.ic_mean:+.4f} ICIR={rep.icir:+.3f} t={rep.ic_tstat_nw:+.2f}")
    if res.holdout_signal_reports:
        print("HOLDOUT-ONLY:")
        for name, rep in sorted(res.holdout_signal_reports.items(), key=lambda kv: -kv[1].ic_mean):
            print(f"  {name:14s} IC={rep.ic_mean:+.4f} t={rep.ic_tstat_nw:+.2f}")


if __name__ == "__main__":
    main()
