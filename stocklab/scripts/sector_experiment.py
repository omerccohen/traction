#!/usr/bin/env python3
"""Field-level effects — the user's "SanDisk and memory chips" hypothesis,
in its two testable forms:

A. SECTOR MOMENTUM (full universe): does the trailing performance of a
   stock's GICS sector predict the stock? (Moskowitz-Grinblatt 1999 industry
   momentum — real at monthly horizons historically; we test 5d.)
   Features (all trailing, leave-one-out so a stock never sees itself):
     sec_mom_21 / sec_mom_63  — peer-average trailing returns
     rel_sec_mom_21           — own momentum minus the field's (within-field
                                relative strength)

B. PEER NEWS SENTIMENT (33-name news subset): does the rest of the field's
   NEWS predict a stock, excluding its own news? (Cohen-Frazzini economic-
   links spillover; strongest for less-followed small caps per literature —
   mega-caps expected to absorb same-day.)

Caveats pre-declared: sector map is a current-day snapshot (sticky labels,
documented); ~2018+ index leavers unmapped -> both arms restricted to the
SAME mapped universe so deltas stay clean. Trials: +8 to ledger (A: 5, B: 3).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.config import ExperimentConfig, BacktestConfig
from stocklab.data.loaders import load_bundled
from stocklab.features.pipeline import build_dataset, FeatureDataset
from stocklab.labels import cross_sectional_rank
from stocklab.validation.walkforward import WalkForwardSplitter
from stocklab.models.baselines import RidgeModel, LightGBMModel
from stocklab.backtest.metrics import _filter_min_names, _spearman_by_date, newey_west_tstat
from stocklab.neutralize import neutralize_scores
from run_experiment import read_ledger, append_ledger

DC = Path(__file__).resolve().parents[1] / "data_cache"


def loo_group_mean(wide: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """Leave-one-out per-date group mean: stock i gets mean of its group
    excluding itself. Vectorized: (group_sum - x) / (group_n - 1)."""
    out = pd.DataFrame(np.nan, index=wide.index, columns=wide.columns)
    for g, members in groups.groupby(groups):
        cols = [c for c in members.index if c in wide.columns]
        if len(cols) < 2:
            continue
        sub = wide[cols]
        n = sub.notna().sum(axis=1)
        s = sub.sum(axis=1)
        loo = sub.mul(-1).add(s, axis=0).div((n - 1).replace(0, np.nan), axis=0)
        out[cols] = loo.where(sub.notna())
    return out


def eval_scores(scores, fwd, exposures, horizon, min_names=20):
    scores = neutralize_scores(scores, exposures)
    df = pd.DataFrame({"s": scores, "f": fwd.reindex(scores.index)}).dropna()
    df = _filter_min_names(df, min_names)
    ic = _spearman_by_date(df)
    return float(ic.mean()), newey_west_tstat(ic, 2 * horizon), int(len(ic))


def run_ab(ds_a, ds_b, folds, eval_dates, exposures, cfg, min_names, label):
    rows = []
    for arm, ds in (("BASE", ds_a), (label, ds_b)):
        for mn, factory in (("ridge", lambda: RidgeModel(alpha=100.0)),
                            ("lightgbm", lambda: LightGBMModel(seed=cfg.seed))):
            parts = []
            for f in folds:
                m = factory()
                m.fit(ds, f.train_dates)
                parts.append(m.predict(ds, f.test_dates))
            sc = pd.concat(parts).sort_index()
            sc = sc[sc.index.get_level_values("date").isin(eval_dates)]
            ic, t, n = eval_scores(sc, ds.fwd_ret, exposures, cfg.label.horizon, min_names)
            rows.append({"arm": arm, "model": mn, "ic": round(ic, 4),
                         "nw_t": round(t, 2), "n_days": n})
            print(rows[-1])
    return rows


def main() -> None:
    sectors = pd.read_csv(DC / "sp500_sectors.csv")
    smap = sectors.set_index("Symbol")["GICS Sector"]
    subind = sectors.set_index("Symbol")["GICS Sub-Industry"]

    cfg = ExperimentConfig(backtest=BacktestConfig(neutralize=("beta_63",)))
    panel_full, _ = load_bundled()
    mapped = [t for t in panel_full.tickers if t in smap.index]
    print(f"sector coverage: {len(mapped)}/{len(panel_full.tickers)} tickers")
    panel = panel_full.select(mapped)
    groups = smap.reindex(panel.tickers)

    # ---- A: sector momentum on the full mapped universe --------------------
    mom21 = panel.close.pct_change(21)
    mom63 = panel.close.pct_change(63)
    sec21 = loo_group_mean(mom21, groups)
    sec63 = loo_group_mean(mom63, groups)
    rel21 = mom21 - sec21

    ds_base = build_dataset(panel, cfg)
    X_sec = ds_base.X.copy()
    for name, wide in (("sec_mom_21", sec21), ("sec_mom_63", sec63),
                       ("rel_sec_mom_21", rel21)):
        X_sec[name] = cross_sectional_rank(wide).stack().reindex(X_sec.index)
    ok = np.isfinite(X_sec[["sec_mom_21", "sec_mom_63", "rel_sec_mom_21"]].to_numpy()).all(axis=1)
    X_sec = X_sec.loc[ok]
    ds_sec = FeatureDataset(X=X_sec, y=ds_base.y.loc[X_sec.index],
                            fwd_ret=ds_base.fwd_ret.loc[X_sec.index],
                            feature_names=list(X_sec.columns), config=cfg,
                            ranked_features=ds_base.ranked_features)

    labeled = pd.DatetimeIndex(
        ds_sec.fwd_ret.dropna().index.get_level_values("date").unique()).sort_values()
    folds = WalkForwardSplitter(cfg).split(labeled)
    cutoff = pd.Timestamp(cfg.split.holdout_start)
    folds = [f for f in folds if f.test_dates[-1] < cutoff]
    eval_dates = pd.DatetimeIndex(sorted({d for f in folds for d in f.test_dates}))
    exposures = ds_base.ranked_features[["beta_63"]]
    print(f"A: {len(folds)} folds, {len(eval_dates)} eval days")

    uni = cross_sectional_rank(sec21).stack()
    uni.index.names = ["date", "ticker"]
    uni = uni[uni.index.get_level_values("date").isin(eval_dates)]
    ic_u, t_u, n_u = eval_scores(uni, ds_base.fwd_ret, exposures, cfg.label.horizon)
    print(f"A univariate sector momentum 21d: IC={ic_u:+.4f} t={t_u:+.2f} n={n_u}")

    rows_a = run_ab(ds_base, ds_sec, folds, eval_dates, exposures, cfg, 20, "SECTOR")

    # ---- B: peer news sentiment on the 33-name subset ----------------------
    news = pd.read_csv(DC / "sp500_news.csv", index_col=0, parse_dates=["date"])
    news["ticker"] = news["stock"].map(lambda s: {"BRK": "BRK.B"}.get(s, s))
    news["net"] = news["Positive"] - news["Negative"]
    nt = sorted(set(news["ticker"]) & set(panel_full.tickers))
    panel33 = panel_full.select(nt)
    net_wide = (news.pivot_table(index="date", columns="ticker", values="net", aggfunc="mean")
                .reindex(columns=nt).reindex(panel33.dates))
    decayed = net_wide.fillna(0.0).ewm(halflife=3, adjust=False).mean()

    g33 = subind.reindex(nt)
    g33 = g33.fillna("UNKNOWN")
    # merge sparse sub-industries into usable fields; semis stay their own field
    def coarse(s: str) -> str:
        s = str(s)
        if "Semiconductor" in s: return "SEMIS"
        if any(k in s for k in ("Bank", "Financial", "Insurance")): return "FINANCIALS"
        if any(k in s for k in ("Payment", "Transaction")): return "PAYMENTS"
        if any(k in s for k in ("Software", "Internet", "Interactive", "Systems")): return "TECH_PLATFORM"
        if any(k in s for k in ("Pharma", "Health", "Biotech", "Managed")): return "HEALTH"
        if any(k in s for k in ("Beverage", "Household", "Food", "Retail", "Merchandise")): return "CONSUMER"
        return "OTHER"
    fields = g33.map(coarse)
    print("B fields:", fields.value_counts().to_dict())

    peer_news = loo_group_mean(decayed, fields)
    cfg33 = ExperimentConfig(backtest=BacktestConfig(neutralize=("beta_63",), n_quantiles=5))
    ds33 = build_dataset(panel33, cfg33)
    X33n = ds33.X.copy()
    X33n["peer_news"] = cross_sectional_rank(peer_news).stack().reindex(X33n.index)
    X33n["own_news"] = cross_sectional_rank(decayed).stack().reindex(X33n.index)
    ok = np.isfinite(X33n[["peer_news", "own_news"]].to_numpy()).all(axis=1)
    X33n = X33n.loc[ok]
    ds33n = FeatureDataset(X=X33n, y=ds33.y.loc[X33n.index],
                           fwd_ret=ds33.fwd_ret.loc[X33n.index],
                           feature_names=list(X33n.columns), config=cfg33,
                           ranked_features=ds33.ranked_features)

    labeled33 = pd.DatetimeIndex(
        ds33n.fwd_ret.dropna().index.get_level_values("date").unique()).sort_values()
    folds33 = WalkForwardSplitter(cfg33).split(labeled33)
    folds33 = [f for f in folds33 if f.test_dates[-1] < cutoff]
    ed33 = pd.DatetimeIndex(sorted({d for f in folds33 for d in f.test_dates}))
    exp33 = ds33.ranked_features[["beta_63"]]

    pu = cross_sectional_rank(peer_news).stack()
    pu.index.names = ["date", "ticker"]
    pu = pu[pu.index.get_level_values("date").isin(ed33)]
    ic_p, t_p, n_p = eval_scores(pu, ds33.fwd_ret, exp33, cfg33.label.horizon, 15)
    print(f"B univariate PEER news: IC={ic_p:+.4f} t={t_p:+.2f} n={n_p}")

    semi_cols = [t for t in nt if fields.get(t) == "SEMIS"]
    pu_s = cross_sectional_rank(peer_news[semi_cols]).stack()
    pu_s.index.names = ["date", "ticker"]
    fwd_s = ds33.fwd_ret[ds33.fwd_ret.index.get_level_values("ticker").isin(semi_cols)]
    dfs = pd.DataFrame({"s": pu_s, "f": fwd_s.reindex(pu_s.index)}).dropna()
    dfs = dfs[dfs.index.get_level_values("date").isin(ed33)]
    ics = _spearman_by_date(_filter_min_names(dfs, 4))
    print(f"B SEMIS-only peer news (n=6 anecdote): IC={float(ics.mean()):+.4f} "
          f"({len(ics)} days)")

    rows_b = run_ab(ds33, ds33n, folds33, ed33, exp33, cfg33, 15, "PEERNEWS")

    outdir = Path("experiments/field_effects")
    outdir.mkdir(parents=True, exist_ok=True)
    summary = {
        "A_universe": f"{len(mapped)} mapped names, 11 GICS sectors",
        "A_univariate_sector_mom21": {"ic": round(ic_u, 4), "t": round(t_u, 2)},
        "A_rows": rows_a,
        "B_fields": fields.value_counts().to_dict(),
        "B_univariate_peer_news": {"ic": round(ic_p, 4), "t": round(t_p, 2)},
        "B_semis_anecdote_ic": round(float(ics.mean()), 4),
        "B_rows": rows_b,
        "caveats": ["sector map is a current-day snapshot (sticky labels)",
                    "33-name universe chosen in 2020 (survivorship-flavored); deltas only",
                    "semis-only readout is n=6 — anecdote, not evidence"],
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    append_ledger({"at": datetime.now(timezone.utc).isoformat(),
                   "out": str(outdir), "models": ["field_effects"],
                   "n_new_trials": 8, "include_holdout": False})
    print("ledger total:", read_ledger()["total_trials"])


if __name__ == "__main__":
    main()
