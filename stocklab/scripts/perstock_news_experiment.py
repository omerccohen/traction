#!/usr/bin/env python3
"""PER-STOCK news sentiment experiment — the real version of the user's
"add news plus sentiment" hypothesis, on the only reachable per-stock dataset.

Data: Datasets/sp500_news.csv from a public GitHub research repo (Kaggle
Benzinga-derived headlines scored with a transformer sentiment model by the
repo author). 34 mega-cap tickers, 2010-2020, date-level Positive/Negative/
Neutral probabilities. Documented caveats:
  * date-level timestamps only (no intraday) — safe under our lag=1
    execution: day-t news trades at close(t+1)
  * the 34-ticker universe was chosen in 2020 -> survivorship-flavored;
    the A/B design (same universe both arms) neutralizes this for the DELTA
  * third-party sentiment model, provenance imperfect -> leakage diagnostics
    below run BEFORE the experiment and gate interpretation

PRE-DECLARED EXPECTATION: fresh-news effects in LARGE caps are the fastest-
arbitraged in the literature (Ke-Kelly-Xiu: 1-2 day assimilation, biggest in
small caps). With a ~30-name cross-section, se(IC) is huge. Expect delta
~ +0.00..+0.02, likely insignificant. Trials: +5 to ledger.

Leakage diagnostics (gate): if raw daily net sentiment "predicts" the 5d
FUTURE return with |IC| > 0.10, or predicts the future better than it
correlates with the SAME day's move, the sentiment was likely constructed
with hindsight -> experiment reported as VOID, not as signal.
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
from stocklab.validation.walkforward import WalkForwardSplitter
from stocklab.models.baselines import RidgeModel, LightGBMModel
from stocklab.backtest.metrics import _filter_min_names, _spearman_by_date, newey_west_tstat
from stocklab.backtest.engine import backtest_long_short
from stocklab.neutralize import neutralize_scores
from run_experiment import read_ledger, append_ledger

NEWS = Path(__file__).resolve().parents[1] / "data_cache" / "sp500_news.csv"
TICKER_MAP = {"BRK": "BRK.B", "FB": "FB", "GOOG": "GOOG"}
MIN_NAMES = 15
N_QUANTILES = 5   # ~30-name cross-section: quintiles, not deciles


def main() -> None:
    news = pd.read_csv(NEWS, index_col=0, parse_dates=["date"])
    news["ticker"] = news["stock"].map(lambda s: TICKER_MAP.get(s, s))
    news["net"] = news["Positive"] - news["Negative"]

    panel_full, _ = load_bundled()
    tickers = sorted(set(news["ticker"]) & set(panel_full.tickers))
    print(f"matched tickers: {len(tickers)} of {news['ticker'].nunique()}")
    panel = panel_full.select(tickers)

    net_wide = (news.pivot_table(index="date", columns="ticker", values="net",
                                 aggfunc="mean")
                .reindex(columns=tickers).reindex(panel.dates))

    # ---- leakage diagnostics (gate) ----------------------------------------
    ret1 = panel.close.pct_change()
    fwd5 = panel.close.shift(-6) / panel.close.shift(-1) - 1.0
    def xs_ic(a: pd.DataFrame, b: pd.DataFrame) -> float:
        ics = []
        for d in a.index:
            x, y = a.loc[d], b.loc[d]
            ok = x.notna() & y.notna()
            if ok.sum() >= 10:
                ics.append(x[ok].rank().corr(y[ok].rank()))
        return float(np.nanmean(ics)) if ics else np.nan
    diag = {
        "sent_vs_same_day_ret": xs_ic(net_wide, ret1),
        "sent_vs_past_ret_t-1": xs_ic(net_wide, ret1.shift(1)),
        "sent_vs_fwd5_ret": xs_ic(net_wide, fwd5),
    }
    print("diagnostics:", json.dumps(diag, indent=2))
    void = (abs(diag["sent_vs_fwd5_ret"]) > 0.10) or (
        abs(diag["sent_vs_fwd5_ret"]) > abs(diag["sent_vs_same_day_ret"]) + 0.05
    )
    if void:
        print("VOID: sentiment shows hindsight signature — aborting experiment")

    # ---- point-in-time news features ---------------------------------------
    had_news = net_wide.notna()
    # exp-decayed net sentiment (half-life 3d): reacts to fresh news, fades
    decayed = net_wide.fillna(0.0).ewm(halflife=3, adjust=False).mean()
    feats_news = {
        "nws_net_decay": decayed,
        "nws_net_5d": net_wide.rolling(5, min_periods=1).mean().fillna(0.0),
        "nws_count_21": had_news.rolling(21).sum(),
        "nws_fresh": (~had_news).astype(float).rolling(10, min_periods=1)
                     .apply(lambda x: float(np.argmax(x[::-1] == 0)) if (x == 0).any() else 10.0,
                            raw=True),
    }

    cfg = ExperimentConfig(backtest=BacktestConfig(neutralize=("beta_63",),
                                                   n_quantiles=N_QUANTILES))
    ds_base = build_dataset(panel, cfg)

    from stocklab.labels import cross_sectional_rank
    X_news = ds_base.X.copy()
    for name, wide in feats_news.items():
        ranked = cross_sectional_rank(wide)
        X_news[name] = ranked.stack().reindex(X_news.index)
    ok = np.isfinite(X_news[list(feats_news)].to_numpy()).all(axis=1)
    X_news = X_news.loc[ok]
    ds_news = FeatureDataset(
        X=X_news, y=ds_base.y.loc[X_news.index], fwd_ret=ds_base.fwd_ret.loc[X_news.index],
        feature_names=list(X_news.columns), config=cfg,
        ranked_features=ds_base.ranked_features,
    )

    labeled = pd.DatetimeIndex(
        ds_news.fwd_ret.dropna().index.get_level_values("date").unique()).sort_values()
    folds = WalkForwardSplitter(cfg).split(labeled)
    cutoff = pd.Timestamp(cfg.split.holdout_start)
    folds = [f for f in folds if f.test_dates[-1] < cutoff]
    eval_dates = pd.DatetimeIndex(sorted({d for f in folds for d in f.test_dates}))
    print(f"{len(folds)} folds, {len(eval_dates)} eval days, "
          f"{len(tickers)}-name cross-section")

    exposures = ds_base.ranked_features[["beta_63"]]
    rows = []

    # univariate news signal (cleanest read): decayed net sentiment as score
    uni = cross_sectional_rank(feats_news["nws_net_decay"]).stack()
    uni.index.names = ["date", "ticker"]
    uni = uni[uni.index.get_level_values("date").isin(eval_dates)]
    uni = neutralize_scores(uni, exposures)
    dfu = pd.DataFrame({"s": uni, "f": ds_base.fwd_ret.reindex(uni.index)}).dropna()
    dfu = _filter_min_names(dfu, MIN_NAMES)
    icu = _spearman_by_date(dfu)
    rows.append({"arm": "UNIVARIATE", "model": "nws_net_decay",
                 "ic": round(float(icu.mean()), 4),
                 "nw_t": round(newey_west_tstat(icu, 2 * cfg.label.horizon), 2),
                 "net_sharpe": np.nan, "n_days": int(len(icu))})

    for arm, ds in (("BASE", ds_base), ("NEWS", ds_news)):
        for model_name, factory in (
            ("ridge", lambda: RidgeModel(alpha=100.0)),
            ("lightgbm", lambda: LightGBMModel(seed=cfg.seed, min_child_samples=40)),
        ):
            parts = []
            for f in folds:
                m = factory()
                m.fit(ds, f.train_dates)
                parts.append(m.predict(ds, f.test_dates))
            scores = pd.concat(parts).sort_index()
            scores = scores[scores.index.get_level_values("date").isin(eval_dates)]
            scores = neutralize_scores(scores, exposures)
            df = pd.DataFrame({"s": scores, "f": ds.fwd_ret.loc[scores.index]}).dropna()
            df = _filter_min_names(df, MIN_NAMES)
            ic = _spearman_by_date(df)
            bt = backtest_long_short(
                f"{arm}/{model_name}", scores, panel.close,
                horizon=cfg.label.horizon, lag=cfg.label.lag,
                n_quantiles=N_QUANTILES, cost_bps=cfg.backtest.cost_bps,
            )
            rows.append({"arm": arm, "model": model_name,
                         "ic": round(float(ic.mean()), 4),
                         "nw_t": round(newey_west_tstat(ic, 2 * cfg.label.horizon), 2),
                         "net_sharpe": round(bt.stats_net.get("sharpe", np.nan), 2),
                         "n_days": int(len(ic))})
            print(rows[-1])

    out = pd.DataFrame(rows)
    outdir = Path("experiments/perstock_news")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "results.csv", index=False)

    deltas = {}
    for mn in ("ridge", "lightgbm"):
        b = out[(out.arm == "BASE") & (out.model == mn)]["ic"].iloc[0]
        n = out[(out.arm == "NEWS") & (out.model == mn)]["ic"].iloc[0]
        deltas[mn] = round(n - b, 4)
    summary = {
        "diagnostics": diag, "void": bool(void),
        "universe": f"{len(tickers)} matched mega-caps (chosen-in-2020 caveat)",
        "ic_delta_news_minus_base": deltas,
        "univariate_news_ic": rows[0]["ic"], "univariate_news_t": rows[0]["nw_t"],
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    print("\nUNIVARIATE news IC:", rows[0]["ic"], "t:", rows[0]["nw_t"])
    print("IC deltas (NEWS-BASE):", deltas)

    append_ledger({
        "at": datetime.now(timezone.utc).isoformat(),
        "out": str(outdir), "models": ["perstock_news_ab"],
        "n_new_trials": 5, "include_holdout": False,
    })
    print("ledger total:", read_ledger()["total_trials"])


if __name__ == "__main__":
    main()
