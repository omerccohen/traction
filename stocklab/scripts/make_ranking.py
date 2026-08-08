#!/usr/bin/env python3
"""Produce the live stock ranking as of the last date in the data,
using a chosen model trained on all labeled history — shipped together with
that model family's out-of-sample evidence and skeptic flags.

Usage:
    python scripts/make_ranking.py --model lightgbm --evidence experiments/final \
        --out experiments/final/ranking.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.config import ExperimentConfig
from stocklab.data.loaders import load_bundled
from stocklab.data.panel import apply_universe_filters
from stocklab.features.pipeline import build_dataset
from stocklab.report import latest_ranking


def build_model(name: str, cfg: ExperimentConfig, ds):
    if name == "momentum":
        from stocklab.models.baselines import MomentumBaseline
        return MomentumBaseline()
    if name == "ridge":
        from stocklab.models.baselines import RidgeModel
        return RidgeModel(alpha=100.0)
    if name == "lightgbm":
        from stocklab.models.baselines import LightGBMModel
        return LightGBMModel(seed=cfg.seed)
    if name == "mlp":
        from stocklab.models.deep import KerasMLP
        return KerasMLP(n_seeds=3)
    raise SystemExit(f"unsupported model for live ranking: {name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="lightgbm")
    ap.add_argument("--evidence", default=None,
                    help="experiment dir whose results.json provides the OOS evidence")
    ap.add_argument("--out", default="experiments/ranking.md")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    evidence, skeptic_txt = {}, ""
    if args.evidence:
        rj = Path(args.evidence) / "results.json"
        if rj.exists():
            data = json.loads(rj.read_text())
            key = {"momentum": "momentum_12_1"}.get(args.model, args.model)
            sig = data.get("holdout_signal_reports", {}).get(key) or \
                  data.get("signal_reports", {}).get(key, {})
            evidence = {
                "model": key,
                "oos_rank_ic": sig.get("ic_mean"),
                "oos_nw_tstat": sig.get("ic_tstat_nw"),
                "oos_days": sig.get("n_days"),
                "source": str(rj),
                "dataset_biases": data.get("dataset_biases", []),
            }
            flags = data.get("skeptic", {}).get(key, {}).get("flags", [])
            skeptic_txt = "\n".join(f"[{f['severity']}] {f['check']}: {f['message']}"
                                    for f in flags)

    cfg = ExperimentConfig()
    panel, biases = load_bundled()
    panel, _ = apply_universe_filters(
        panel, cfg.universe.min_history, cfg.universe.min_price, cfg.universe.min_dollar_volume
    )
    ds = build_dataset(panel, cfg)
    model = build_model(args.model, cfg, ds)

    rep = latest_ranking(ds, model, signal_evidence=evidence,
                         skeptic_summary=skeptic_txt, top_n=args.top)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rep.markdown)
    print(f"ranking as of {rep.as_of.date()} -> {out}")
    print(rep.table.head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()
