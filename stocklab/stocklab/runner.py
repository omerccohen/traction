"""Walk-forward experiment orchestration.

For each fold: fit every model on purged train dates, predict the test block;
concatenate out-of-sample predictions across folds; evaluate signals; admit
ensemble members; backtest; run the skeptic. All artifacts land in an
experiment directory as JSON + markdown.
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import DISCLAIMER
from .config import ExperimentConfig
from .data.panel import Panel, apply_universe_filters
from .features.pipeline import build_dataset, FeatureDataset
from .labels import forward_returns
from .validation.walkforward import WalkForwardSplitter
from .validation import leakage
from .backtest.metrics import signal_report, deflated_sharpe
from .backtest.engine import backtest_long_short
from .ensemble import ensemble_scores
from .skeptic import review_signal


@dataclass
class ExperimentResult:
    config: ExperimentConfig
    oos_scores: dict = field(default_factory=dict)      # model -> Series (date,ticker)
    signal_reports: dict = field(default_factory=dict)  # model -> SignalReport
    backtests: dict = field(default_factory=dict)       # model -> BacktestResult
    skeptic_reports: dict = field(default_factory=dict)
    fold_log: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    n_trials: int = 0
    dataset_biases: list = field(default_factory=list)
    leakage_results: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)


def run_walk_forward(
    panel: Panel,
    model_factories: dict,          # name -> callable(ds) -> Model (fresh per fold)
    config: ExperimentConfig | None = None,
    dataset_biases: list[str] | None = None,
    n_prior_trials: int = 0,
    include_holdout: bool = False,
    verbose: bool = True,
) -> ExperimentResult:
    cfg = config or ExperimentConfig()
    t0 = time.time()

    panel, univ_report = apply_universe_filters(
        panel, cfg.universe.min_history, cfg.universe.min_price, cfg.universe.min_dollar_volume
    )
    ds = build_dataset(panel, cfg)
    if verbose:
        print(panel.summary())
        print(ds.summary())

    splitter = WalkForwardSplitter(cfg)
    labeled_dates = pd.DatetimeIndex(
        ds.fwd_ret.dropna().index.get_level_values("date").unique()
    ).sort_values()
    folds = splitter.split(labeled_dates)
    splitter.audit(folds, labeled_dates)

    hs = cfg.split.holdout_start
    if hs is not None and not include_holdout:
        cutoff = pd.Timestamp(hs)
        n_before = len(folds)
        folds = [f for f in folds if f.test_dates[-1] < cutoff]
        if verbose and len(folds) < n_before:
            print(f"lockbox: {n_before - len(folds)} fold(s) with test >= {hs} "
                  "excluded from this iteration run (final run uses include_holdout=True)")
        if not folds:
            raise ValueError("all folds fall inside the holdout; check holdout_start")
    if verbose:
        print(f"{len(folds)} folds; gap={splitter.gap} trading days (purge+embargo)")

    res = ExperimentResult(config=cfg, dataset_biases=list(dataset_biases or []))
    res.timings["setup"] = time.time() - t0

    # ----- walk-forward ------------------------------------------------------
    preds: dict[str, list] = {name: [] for name in model_factories}
    for fold in folds:
        if verbose:
            print(repr(fold))
        for name, factory in model_factories.items():
            t1 = time.time()
            try:
                model = factory(ds)
                model.fit(ds, fold.train_dates)
                p = model.predict(ds, fold.test_dates)
                preds[name].append(p)
                res.fold_log.append({
                    "fold": fold.index, "model": name, "n_pred": int(len(p)),
                    "seconds": round(time.time() - t1, 1),
                })
            except Exception as e:  # a model failing must not sink the experiment
                res.errors[f"{name}/fold{fold.index}"] = f"{e}\n{traceback.format_exc(limit=3)}"
                if verbose:
                    print(f"  ERROR {name} fold {fold.index}: {e}")

    for name, parts in preds.items():
        if parts:
            s = pd.concat(parts).sort_index()
            s = s[~s.index.duplicated(keep="first")]
            res.oos_scores[name] = s

    # ----- evaluation --------------------------------------------------------
    extra_h = {h: forward_returns(panel, h, cfg.label.lag).stack() for h in (1, 10, 21)}
    for h in extra_h:
        extra_h[h].index.names = ["date", "ticker"]

    baseline_ic = None
    for name, s in res.oos_scores.items():
        rep = signal_report(
            name, s, ds.fwd_ret, horizon=cfg.label.horizon,
            n_quantiles=cfg.backtest.n_quantiles, extra_horizon_rets=extra_h,
        )
        res.signal_reports[name] = rep
        if name == "momentum_12_1":
            baseline_ic = rep.ic_mean

    # ----- ensemble ----------------------------------------------------------
    if baseline_ic is not None:
        admitted = {
            n: s for n, s in res.oos_scores.items()
            if n != "momentum_12_1" and res.signal_reports[n].ic_mean > baseline_ic
        }
        if len(admitted) >= 2:
            ens = ensemble_scores(admitted)
            res.oos_scores["ensemble"] = ens
            res.signal_reports["ensemble"] = signal_report(
                "ensemble", ens, ds.fwd_ret, horizon=cfg.label.horizon,
                n_quantiles=cfg.backtest.n_quantiles, extra_horizon_rets=extra_h,
            )
            res.signal_reports["ensemble"].__dict__["members"] = sorted(admitted)

    # trial accounting: every (model x fold-config) evaluated in this run + prior
    res.n_trials = n_prior_trials + len(res.oos_scores)

    # ----- backtests + skeptic ----------------------------------------------
    sharpe_list = []
    for name, s in res.oos_scores.items():
        bt = backtest_long_short(
            name, s, panel.close,
            horizon=cfg.label.horizon, lag=cfg.label.lag,
            n_quantiles=cfg.backtest.n_quantiles,
            cost_bps=cfg.backtest.cost_bps, cost_grid=cfg.backtest.cost_grid,
        )
        res.backtests[name] = bt
        if np.isfinite(bt.stats_net.get("sharpe", np.nan)):
            sharpe_list.append(bt.stats_net["sharpe"])

    sr_spread = float(np.std(sharpe_list)) if len(sharpe_list) >= 3 else 0.5

    for name in res.oos_scores:
        rep = res.signal_reports[name]
        bt = res.backtests.get(name)
        ic_series = rep.ic_series
        half = len(ic_series) // 2
        fh, sh = float(ic_series.iloc[:half].mean()), float(ic_series.iloc[half:].mean())
        dsr = None
        if bt is not None and np.isfinite(bt.stats_net.get("sharpe", np.nan)):
            dsr = deflated_sharpe(
                bt.stats_net["sharpe"], bt.stats_net.get("n_days", 0),
                n_trials=res.n_trials, sr_std_across_trials=sr_spread,
                skew=bt.stats_net.get("skew", 0.0), kurt=bt.stats_net.get("kurtosis", 3.0),
            )
        res.skeptic_reports[name] = review_signal(
            name, rep.to_dict(), bt.to_dict() if bt else None,
            dataset_biases=res.dataset_biases,
            baseline_ic=baseline_ic if name != "momentum_12_1" else None,
            n_trials=res.n_trials, dsr=dsr,
            first_half_ic=fh, second_half_ic=sh,
        )
        if dsr is not None:
            res.backtests[name].stats_net["deflated_sharpe_prob"] = float(dsr)

    res.timings["total"] = time.time() - t0
    return res


def run_leakage_suite(
    panel: Panel, config: ExperimentConfig | None = None, verbose: bool = True
) -> dict:
    """Shuffled-label + canary checks using a fast Ridge model on one split."""
    from .models.baselines import RidgeModel

    cfg = config or ExperimentConfig()
    panel, _ = apply_universe_filters(
        panel, cfg.universe.min_history, cfg.universe.min_price, cfg.universe.min_dollar_volume
    )
    ds = build_dataset(panel, cfg)
    splitter = WalkForwardSplitter(cfg)
    labeled = pd.DatetimeIndex(ds.fwd_ret.dropna().index.get_level_values("date").unique()).sort_values()
    folds = splitter.split(labeled)
    fold = folds[len(folds) // 2]

    out = {}

    # 1) shuffled labels -> IC must collapse
    y_shuf = leakage.shuffle_labels_within_dates(ds.y, seed=cfg.seed)
    ds_shuf = FeatureDataset(
        X=ds.X, y=y_shuf, fwd_ret=ds.fwd_ret, feature_names=ds.feature_names,
        config=cfg, ranked_features=ds.ranked_features,
    )
    m = RidgeModel()
    m.fit(ds_shuf, fold.train_dates)
    p = m.predict(ds_shuf, fold.test_dates)
    # evaluate vs the SHUFFLED target's implied forward returns: use shuffled y as pseudo-returns
    rep = signal_report("shuffled", p, y_shuf.loc[p.index], horizon=cfg.label.horizon,
                        n_quantiles=cfg.backtest.n_quantiles)
    out["shuffled_label_ic"] = rep.ic_mean
    out["shuffled_label_verdict"] = leakage.verdict_from_ic(rep.ic_mean)

    # 2) canary: inject future return as feature -> IC must explode (detector works)
    X_can = leakage.inject_canary(ds.X, ds.fwd_ret, seed=cfg.seed)
    ds_can = FeatureDataset(
        X=X_can, y=ds.y, fwd_ret=ds.fwd_ret, feature_names=ds.feature_names + ["__canary"],
        config=cfg, ranked_features=ds.ranked_features,
    )
    m2 = RidgeModel()
    m2.fit(ds_can, fold.train_dates)
    p2 = m2.predict(ds_can, fold.test_dates)
    rep2 = signal_report("canary", p2, ds.fwd_ret, horizon=cfg.label.horizon,
                         n_quantiles=cfg.backtest.n_quantiles)
    out["canary_ic"] = rep2.ic_mean
    out["canary_verdict"] = (
        "PASS (detector fires on planted leak)" if rep2.ic_mean > 0.2
        else "FAIL: planted leak NOT detected — detector broken"
    )
    if verbose:
        print("leakage suite:", json.dumps(out, indent=2, default=float))
    return out


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def result_to_markdown(res: ExperimentResult, title: str) -> str:
    lines = [f"# {title}", "", f"> {DISCLAIMER}", ""]
    lines.append(f"- trials counted for deflation: **{res.n_trials}**")
    lines.append(f"- folds: {len({f['fold'] for f in res.fold_log})}, "
                 f"total runtime {res.timings.get('total', 0):.0f}s")
    if res.errors:
        lines.append(f"- errors: {len(res.errors)} (see errors.json)")
    lines.append("")

    lines.append("## Signal tear sheet (out-of-sample, concatenated across folds)")
    lines.append("")
    lines.append("| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    order = sorted(res.signal_reports, key=lambda n: -res.signal_reports[n].ic_mean)
    for name in order:
        r = res.signal_reports[name]
        lines.append(
            f"| {name} | {r.ic_mean:.4f} | {r.icir:.3f} | {r.ic_tstat_nw:.2f} | "
            f"{r.ic_positive_share:.0%} | {r.monotonicity:.2f} | {r.top_bottom_spread*1e4:.0f} bps | "
            f"{r.rank_autocorr_1d:.2f} | {r.n_days} |"
        )
    lines.append("")

    lines.append("## IC by horizon (days)")
    lines.append("")
    hs = sorted({h for r in res.signal_reports.values() for h in r.ic_by_horizon})
    if hs:
        lines.append("| model | " + " | ".join(str(h) for h in hs) + " |")
        lines.append("|" + "---|" * (len(hs) + 1))
        for name in order:
            r = res.signal_reports[name]
            row = " | ".join(f"{r.ic_by_horizon.get(h, float('nan')):.4f}" for h in hs)
            lines.append(f"| {name} | {row} |")
        lines.append("")

    lines.append("## Backtest — long-short decile, overlapping tranches, net of costs")
    lines.append("")
    lines.append("| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for name in order:
        bt = res.backtests.get(name)
        if not bt:
            continue
        sn, sg = bt.stats_net, bt.stats_gross
        lines.append(
            f"| {name} | {sn.get('sharpe', float('nan')):.2f} | {sn.get('ann_return', float('nan')):.1%} | "
            f"{sg.get('sharpe', float('nan')):.2f} | {sn.get('max_drawdown', float('nan')):.1%} | "
            f"{bt.avg_daily_turnover:.2f} | {bt.breakeven_cost_bps:.0f} | "
            f"{sn.get('deflated_sharpe_prob', float('nan')):.2f} |"
        )
    lines.append("")

    lines.append("### Cost sensitivity (net Sharpe at bps per side)")
    lines.append("")
    grid = sorted(next(iter(res.backtests.values())).stats_by_cost) if res.backtests else []
    if grid:
        lines.append("| model | " + " | ".join(f"{c:.0f} bps" for c in grid) + " |")
        lines.append("|" + "---|" * (len(grid) + 1))
        for name in order:
            bt = res.backtests.get(name)
            if not bt:
                continue
            row = " | ".join(f"{bt.stats_by_cost[c].get('sharpe', float('nan')):.2f}" for c in grid)
            lines.append(f"| {name} | {row} |")
        lines.append("")

    lines.append("### Long/short leg decomposition (gross ann. return)")
    lines.append("")
    lines.append("| model | long leg | short leg |")
    lines.append("|---|---|---|")
    for name in order:
        bt = res.backtests.get(name)
        if not bt:
            continue
        lines.append(
            f"| {name} | {bt.leg_stats['long'].get('ann_return', float('nan')):.1%} | "
            f"{bt.leg_stats['short'].get('ann_return', float('nan')):.1%} |"
        )
    lines.append("")

    lines.append("## Skeptic reports")
    lines.append("")
    for name in order:
        rep = res.skeptic_reports.get(name)
        if rep:
            lines.append("```")
            lines.append(rep.format())
            lines.append("```")
    lines.append("")
    if res.leakage_results:
        lines.append("## Leakage suite")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(res.leakage_results, indent=2, default=float))
        lines.append("```")
    return "\n".join(lines)


def save_experiment(res: ExperimentResult, out_dir: str | Path, title: str) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(result_to_markdown(res, title))
    payload = {
        "signal_reports": {k: v.to_dict() for k, v in res.signal_reports.items()},
        "backtests": {k: v.to_dict() for k, v in res.backtests.items()},
        "skeptic": {k: v.to_dict() for k, v in res.skeptic_reports.items()},
        "fold_log": res.fold_log,
        "n_trials": res.n_trials,
        "dataset_biases": res.dataset_biases,
        "leakage": res.leakage_results,
        "timings": res.timings,
        "config": res.config.to_dict(),
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=float))
    if res.errors:
        (out / "errors.json").write_text(json.dumps(res.errors, indent=2))
    for name, s in res.oos_scores.items():
        s.to_frame("score").to_csv(out / f"scores_{name}.csv.gz", compression="gzip")
    return out
