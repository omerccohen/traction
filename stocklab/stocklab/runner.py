"""Walk-forward experiment orchestration.

For each fold: fit every model on purged train dates, predict the test block;
concatenate out-of-sample predictions across folds; evaluate signals; build
the ensemble with WALK-FORWARD admission (membership for fold k decided only
on folds < k — the ensemble is a strategy that could actually have been run,
not a winner picked on the data it is graded on); backtest; run the skeptic.
All artifacts land in an experiment directory as JSON + markdown.
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
from .labels import forward_returns, cross_sectional_rank
from .validation.walkforward import WalkForwardSplitter, Fold
from .validation import leakage
from .backtest.metrics import signal_report, deflated_sharpe, _filter_min_names, _spearman_by_date
from .backtest.engine import backtest_long_short
from .ensemble import ensemble_scores
from .skeptic import review_signal

BASELINE_NAME = "momentum_12_1"


@dataclass
class ExperimentResult:
    config: ExperimentConfig
    oos_scores: dict = field(default_factory=dict)      # model -> Series (date,ticker)
    signal_reports: dict = field(default_factory=dict)  # model -> SignalReport
    backtests: dict = field(default_factory=dict)       # model -> BacktestResult
    skeptic_reports: dict = field(default_factory=dict)
    holdout_signal_reports: dict = field(default_factory=dict)
    holdout_backtests: dict = field(default_factory=dict)
    ensemble_membership: dict = field(default_factory=dict)  # fold -> [members]
    fold_log: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    n_trials: int = 0
    dataset_biases: list = field(default_factory=list)
    leakage_results: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    holdout_included: bool = False


def _quick_ic(scores: pd.Series, fwd: pd.Series, min_names: int = 20) -> float:
    df = pd.DataFrame({"s": scores, "f": fwd}).dropna()
    if df.empty:
        return np.nan
    df = _filter_min_names(df, min_names)
    if df.empty:
        return np.nan
    return float(_spearman_by_date(df).mean())


def _walk_forward_ensemble(
    fold_preds: dict[str, dict[int, pd.Series]],
    fold_order: list[int],
    fwd_ret: pd.Series,
    verbose: bool = True,
) -> tuple[pd.Series | None, dict[int, list[str]]]:
    """Per-fold ensemble with admission decided ONLY on prior folds' OOS.

    For fold k (k>=1): a candidate (any model except the momentum baseline)
    is admitted iff its concatenated OOS IC on folds < k beats the momentum
    baseline's on the same span. Fold 0 has no prior evidence -> no ensemble.
    If the baseline was not run, the fixed a-priori rule "equal-weight all
    candidates" applies (logged) — fixed rules need no data.
    """
    candidates = [n for n in fold_preds if n != BASELINE_NAME]
    if len(candidates) < 2:
        return None, {}
    have_baseline = BASELINE_NAME in fold_preds

    parts: list[pd.Series] = []
    membership: dict[int, list[str]] = {}
    for pos, k in enumerate(fold_order):
        if pos == 0:
            continue
        prior = fold_order[:pos]
        if have_baseline:
            base_prior = pd.concat(
                [fold_preds[BASELINE_NAME][j] for j in prior if j in fold_preds[BASELINE_NAME]]
            )
            base_ic = _quick_ic(base_prior, fwd_ret.loc[base_prior.index.intersection(fwd_ret.index)])
            admitted = []
            for name in candidates:
                have = [fold_preds[name][j] for j in prior if j in fold_preds[name]]
                if not have:
                    continue
                s_prior = pd.concat(have)
                ic = _quick_ic(s_prior, fwd_ret.loc[s_prior.index.intersection(fwd_ret.index)])
                if np.isfinite(ic) and (not np.isfinite(base_ic) or ic > base_ic):
                    admitted.append(name)
        else:
            admitted = list(candidates)
        membership[k] = sorted(admitted)
        if len(admitted) < 2:
            continue
        members_k = {n: fold_preds[n][k] for n in admitted if k in fold_preds[n]}
        members_k = {n: s for n, s in members_k.items() if len(s) > 0}
        if len(members_k) < 2:
            continue
        parts.append(ensemble_scores(members_k))

    if not parts:
        return None, membership
    ens = pd.concat(parts).sort_index()
    if verbose:
        n_folds_used = len([m for m in membership.values() if len(m) >= 2])
        print(f"ensemble: walk-forward admission active on {n_folds_used} folds")
    return ens, membership


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

    res = ExperimentResult(
        config=cfg, dataset_biases=list(dataset_biases or []),
        holdout_included=bool(include_holdout and hs is not None),
    )
    res.timings["setup"] = time.time() - t0

    # ----- walk-forward ------------------------------------------------------
    fold_preds: dict[str, dict[int, pd.Series]] = {name: {} for name in model_factories}
    for fold in folds:
        if verbose:
            print(repr(fold))
        for name, factory in model_factories.items():
            t1 = time.time()
            try:
                model = factory(ds)
                model.fit(ds, fold.train_dates)
                p = model.predict(ds, fold.test_dates)
                fold_preds[name][fold.index] = p
                res.fold_log.append({
                    "fold": fold.index, "model": name, "n_pred": int(len(p)),
                    "seconds": round(time.time() - t1, 1),
                })
            except Exception as e:  # a model failing must not sink the experiment
                res.errors[f"{name}/fold{fold.index}"] = f"{e}\n{traceback.format_exc(limit=3)}"
                if verbose:
                    print(f"  ERROR {name} fold {fold.index}: {e}")

    fold_order = [f.index for f in folds]
    for name, parts in fold_preds.items():
        if parts:
            s = pd.concat([parts[k] for k in fold_order if k in parts]).sort_index()
            if s.index.has_duplicates:  # folds are disjoint; duplicates = bug upstream
                raise AssertionError(f"{name}: duplicate (date,ticker) predictions across folds")
            res.oos_scores[name] = s

    # ----- ensemble (walk-forward admission; see docstring) ------------------
    ens, membership = _walk_forward_ensemble(
        {n: p for n, p in fold_preds.items() if p}, fold_order, ds.fwd_ret, verbose
    )
    res.ensemble_membership = membership
    if ens is not None and len(ens) > 0:
        res.oos_scores["ensemble"] = ens
    elif verbose and len(model_factories) > 2:
        print("ensemble: not formed (needs >=2 candidates with prior-fold evidence)")

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
        if name == BASELINE_NAME:
            baseline_ic = rep.ic_mean

    # trial accounting: each model configuration evaluated in this run counts
    # as one trial (folds are one strategy rolled forward, not extra trials);
    # n_prior_trials must carry the count from all previous iteration runs —
    # the ledger in scripts/run_experiment.py persists it.
    res.n_trials = n_prior_trials + len(res.oos_scores)

    # ----- backtests ---------------------------------------------------------
    for name, s in res.oos_scores.items():
        bt = backtest_long_short(
            name, s, panel.close,
            horizon=cfg.label.horizon, lag=cfg.label.lag,
            n_quantiles=cfg.backtest.n_quantiles,
            cost_bps=cfg.backtest.cost_bps, cost_grid=cfg.backtest.cost_grid,
        )
        res.backtests[name] = bt

    # spread of Sharpes across NON-ensemble models: the noise dispersion for
    # DSR (the ensemble is a selected object; including it biases the spread)
    plain = [n for n in res.backtests if n != "ensemble"]
    sharpes = [res.backtests[n].stats_net.get("sharpe", np.nan) for n in plain]
    sharpes = [s for s in sharpes if np.isfinite(s)]
    sr_spread = float(np.std(sharpes)) if len(sharpes) >= 3 else 0.5  # 0.5 ann: conservative default

    # ----- skeptic -----------------------------------------------------------
    for name in res.oos_scores:
        rep = res.signal_reports[name]
        bt = res.backtests.get(name)
        ic_series = rep.ic_series
        half = len(ic_series) // 2
        fh, sh = float(ic_series.iloc[:half].mean()), float(ic_series.iloc[half:].mean())
        dsr = None
        if bt is not None and np.isfinite(bt.stats_net.get("sharpe", np.nan)):
            # overlapping k-day holds autocorrelate daily returns; the DSR's
            # sqrt(n-1) assumes independence -> use n/horizon effective obs
            # (conservative; review finding m5)
            n_eff = max(bt.stats_net.get("n_days", 0) // cfg.label.horizon, 2)
            dsr = deflated_sharpe(
                bt.stats_net["sharpe"], n_eff,
                n_trials=res.n_trials, sr_std_across_trials=sr_spread,
                skew=bt.stats_net.get("skew", 0.0), kurt=bt.stats_net.get("kurtosis", 3.0),
            )
        res.skeptic_reports[name] = review_signal(
            name, rep.to_dict(), bt.to_dict() if bt else None,
            dataset_biases=res.dataset_biases,
            baseline_ic=baseline_ic if name != BASELINE_NAME else None,
            n_trials=res.n_trials, dsr=dsr,
            first_half_ic=fh, second_half_ic=sh,
            horizon=cfg.label.horizon,
        )
        if dsr is not None:
            res.backtests[name].stats_net["deflated_sharpe_prob"] = float(dsr)

    # ----- holdout-only breakout (the number the lockbox exists to produce) --
    if res.holdout_included:
        cutoff = pd.Timestamp(hs)
        for name, s in res.oos_scores.items():
            s_h = s[s.index.get_level_values("date") >= cutoff]
            if len(s_h) == 0:
                continue
            try:
                res.holdout_signal_reports[name] = signal_report(
                    name, s_h, ds.fwd_ret, horizon=cfg.label.horizon,
                    n_quantiles=cfg.backtest.n_quantiles,
                )
                res.holdout_backtests[name] = backtest_long_short(
                    name, s_h, panel.close,
                    horizon=cfg.label.horizon, lag=cfg.label.lag,
                    n_quantiles=cfg.backtest.n_quantiles,
                    cost_bps=cfg.backtest.cost_bps, cost_grid=cfg.backtest.cost_grid,
                )
            except ValueError as e:
                res.errors[f"holdout/{name}"] = str(e)

    res.timings["total"] = time.time() - t0
    return res


def run_leakage_suite(
    panel: Panel, config: ExperimentConfig | None = None, verbose: bool = True,
    include_sequence_path: bool = True,
) -> dict:
    """Shuffled-label + canary checks on BOTH model input paths.

    Honest scope (review finding M1): the shuffled-label test detects
    train/test row contamination and index misalignment — it CANNOT detect a
    lookahead *feature* (the shuffle destroys that link too); feature timing
    is guarded by the point-in-time tests in tests/. The canary validates
    that the IC metric fires when future information is present.

    Covers the tabular path (Ridge on X) and the sequence path (Ridge on
    flattened SequenceStore windows — the only code doing manual index
    arithmetic, review finding M5). Fold selection respects the lockbox.
    """
    from .models.baselines import RidgeModel
    from .models.sequences import SequenceStore
    from sklearn.linear_model import Ridge as SkRidge

    cfg = config or ExperimentConfig()
    panel, _ = apply_universe_filters(
        panel, cfg.universe.min_history, cfg.universe.min_price, cfg.universe.min_dollar_volume
    )
    ds = build_dataset(panel, cfg)
    splitter = WalkForwardSplitter(cfg)
    labeled = pd.DatetimeIndex(ds.fwd_ret.dropna().index.get_level_values("date").unique()).sort_values()
    folds = splitter.split(labeled)
    if cfg.split.holdout_start is not None:
        cutoff = pd.Timestamp(cfg.split.holdout_start)
        pre = [f for f in folds if f.test_dates[-1] < cutoff]
        folds = pre or folds
    fold = folds[len(folds) // 2]

    out = {}

    # 1) tabular shuffled labels -> IC must collapse
    y_shuf = leakage.shuffle_labels_within_dates(ds.y, seed=cfg.seed)
    ds_shuf = FeatureDataset(
        X=ds.X, y=y_shuf, fwd_ret=ds.fwd_ret, feature_names=ds.feature_names,
        config=cfg, ranked_features=ds.ranked_features,
    )
    m = RidgeModel()
    m.fit(ds_shuf, fold.train_dates)
    p = m.predict(ds_shuf, fold.test_dates)
    ic_shuf = _quick_ic(p, y_shuf.loc[p.index])
    out["tabular_shuffled_ic"] = ic_shuf
    out["tabular_shuffled_verdict"] = (
        "PASS (no train/test row contamination detected)" if abs(ic_shuf) < 0.02
        else f"FAIL: |IC|={abs(ic_shuf):.4f} on shuffled labels — rows leak across the split"
    )

    # 2) tabular canary: future return as feature -> metric must fire
    X_can = leakage.inject_canary(ds.X, ds.fwd_ret, seed=cfg.seed)
    ds_can = FeatureDataset(
        X=X_can, y=ds.y, fwd_ret=ds.fwd_ret, feature_names=ds.feature_names + ["__canary"],
        config=cfg, ranked_features=ds.ranked_features,
    )
    m2 = RidgeModel()
    m2.fit(ds_can, fold.train_dates)
    p2 = m2.predict(ds_can, fold.test_dates)
    ic_can = _quick_ic(p2, ds.fwd_ret.loc[p2.index])
    out["tabular_canary_ic"] = ic_can
    out["tabular_canary_verdict"] = (
        "PASS (detector fires on planted leak)" if ic_can > 0.2
        else "FAIL: planted leak NOT detected — detector broken"
    )

    if include_sequence_path:
        feats = list(cfg.sequence.features)

        def _seq_ic(ranked, target, eval_against) -> float:
            store = SequenceStore(
                FeatureDataset(X=ds.X, y=target, fwd_ret=ds.fwd_ret,
                               feature_names=ds.feature_names, config=cfg,
                               ranked_features=ranked),
                [c for c in ranked.columns], cfg.sequence.length,
            )
            dsx = FeatureDataset(X=ds.X, y=target, fwd_ret=ds.fwd_ret,
                                 feature_names=ds.feature_names, config=cfg,
                                 ranked_features=ranked)
            tr = store.batch_for(dsx, fold.train_dates, with_labels=True, stride=4)
            te = store.batch_for(dsx, fold.test_dates, with_labels=False, stride=1)
            if len(tr.X) < 500 or len(te.X) < 200:
                return np.nan
            lin = SkRidge(alpha=10.0)
            lin.fit(tr.X.reshape(len(tr.X), -1), tr.y)
            pred = pd.Series(lin.predict(te.X.reshape(len(te.X), -1)), index=te.index)
            return _quick_ic(pred, eval_against.loc[pred.index.intersection(eval_against.index)])

        # 3) sequence shuffled labels
        ic_seq_shuf = _seq_ic(ds.ranked_features[feats], y_shuf, y_shuf)
        out["sequence_shuffled_ic"] = ic_seq_shuf
        out["sequence_shuffled_verdict"] = (
            "PASS (no train/test row contamination detected)" if abs(ic_seq_shuf) < 0.03
            else f"FAIL: |IC|={abs(ic_seq_shuf):.4f} — sequence path leaks across the split"
        )

        # 4) sequence canary: rank of the future return as an extra feature plane
        ranked_can = ds.ranked_features[feats].copy()
        fwd_wide = ds.fwd_ret.unstack("ticker")
        ranked_can["__canary"] = cross_sectional_rank(fwd_wide).stack().reindex(ranked_can.index)
        ranked_can["__canary"] = ranked_can["__canary"].fillna(0.0)
        ic_seq_can = _seq_ic(ranked_can, ds.y, ds.fwd_ret)
        out["sequence_canary_ic"] = ic_seq_can
        out["sequence_canary_verdict"] = (
            "PASS (window indexing exposes the current row, as designed; detector fires)"
            if ic_seq_can > 0.2 else
            "FAIL: canary in the sequence window NOT detected — window math suspect"
        )

    if verbose:
        print("leakage suite:", json.dumps(out, indent=2, default=float))
    return out


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def _signal_table(reports: dict, order: list[str]) -> list[str]:
    lines = []
    lines.append("| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for name in order:
        r = reports.get(name)
        if r is None:
            continue
        lines.append(
            f"| {name} | {r.ic_mean:.4f} | {r.icir:.3f} | {r.ic_tstat_nw:.2f} | "
            f"{r.ic_positive_share:.0%} | {r.monotonicity:.2f} | {r.top_bottom_spread*1e4:.0f} bps | "
            f"{r.rank_autocorr_1d:.2f} | {r.n_days} |"
        )
    return lines


def _backtest_table(backtests: dict, order: list[str]) -> list[str]:
    lines = []
    lines.append("| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for name in order:
        bt = backtests.get(name)
        if not bt:
            continue
        sn, sg = bt.stats_net, bt.stats_gross
        lines.append(
            f"| {name} | {sn.get('sharpe', float('nan')):.2f} | {sn.get('ann_return', float('nan')):.1%} | "
            f"{sg.get('sharpe', float('nan')):.2f} | {sn.get('max_drawdown', float('nan')):.1%} | "
            f"{bt.avg_daily_turnover:.2f} | {bt.breakeven_cost_bps:.0f} | "
            f"{sn.get('deflated_sharpe_prob', float('nan')):.2f} |"
        )
    return lines


def result_to_markdown(res: ExperimentResult, title: str) -> str:
    lines = [f"# {title}", "", f"> {DISCLAIMER}", ""]
    lines.append(f"- trials counted for deflation: **{res.n_trials}** "
                 "(this run's models + persisted prior-run ledger)")
    lines.append(f"- folds: {len({f['fold'] for f in res.fold_log})}, "
                 f"total runtime {res.timings.get('total', 0):.0f}s")
    if res.errors:
        lines.append(f"- errors: {len(res.errors)} (see errors.json)")
    lines.append("")

    order = sorted(res.signal_reports, key=lambda n: -res.signal_reports[n].ic_mean)

    if res.holdout_included and res.holdout_signal_reports:
        h_order = sorted(res.holdout_signal_reports,
                         key=lambda n: -res.holdout_signal_reports[n].ic_mean)
        lines.append(f"## HOLDOUT-ONLY (test >= {res.config.split.holdout_start}) — "
                     "the only numbers never iterated on")
        lines.append("")
        lines.append("Every development decision was made on the pre-holdout folds; this")
        lines.append("section is the sole out-of-sample-of-the-process evidence.")
        lines.append("")
        lines += _signal_table(res.holdout_signal_reports, h_order)
        lines.append("")
        lines += _backtest_table(res.holdout_backtests, h_order)
        lines.append("")

    lines.append("## Signal tear sheet (all OOS folds, concatenated)")
    if res.holdout_included:
        lines.append("")
        lines.append("*Includes the pre-holdout folds that development iterated on — read the")
        lines.append("holdout-only section above for the untouched estimate.*")
    lines.append("")
    lines += _signal_table(res.signal_reports, order)
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
    lines += _backtest_table(res.backtests, order)
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

    if res.ensemble_membership:
        lines.append("### Ensemble membership by fold (walk-forward admission)")
        lines.append("")
        for k in sorted(res.ensemble_membership):
            m = res.ensemble_membership[k]
            lines.append(f"- fold {k}: {', '.join(m) if m else '(none admitted)'}")
        lines.append("")

    lines.append("## Per-year net performance")
    lines.append("")
    years = sorted({y for bt in res.backtests.values() for y in bt.by_year})
    if years:
        lines.append("| model | " + " | ".join(str(y) for y in years) + " |")
        lines.append("|" + "---|" * (len(years) + 1))
        for name in order:
            bt = res.backtests.get(name)
            if not bt:
                continue
            row = " | ".join(
                (f"{bt.by_year[y]['ann_return']:.0%}/{bt.by_year[y]['sharpe']:.1f}"
                 if y in bt.by_year else "—") for y in years
            )
            lines.append(f"| {name} | {row} |")
        lines.append("  (cells: ann return / Sharpe)")
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
        "holdout_signal_reports": {k: v.to_dict() for k, v in res.holdout_signal_reports.items()},
        "holdout_backtests": {k: v.to_dict() for k, v in res.holdout_backtests.items()},
        "ensemble_membership": {str(k): v for k, v in res.ensemble_membership.items()},
        "skeptic": {k: v.to_dict() for k, v in res.skeptic_reports.items()},
        "fold_log": res.fold_log,
        "n_trials": res.n_trials,
        "dataset_biases": res.dataset_biases,
        "leakage": res.leakage_results,
        "timings": res.timings,
        "config": res.config.to_dict(),
        "holdout_included": res.holdout_included,
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=float))
    if res.errors:
        (out / "errors.json").write_text(json.dumps(res.errors, indent=2))
    for name, s in res.oos_scores.items():
        s.to_frame("score").to_csv(out / f"scores_{name}.csv.gz", compression="gzip")
    return out
