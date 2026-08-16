#!/usr/bin/env python3
"""News + sentiment experiment (user hypothesis: "add news plus sentiment").

Data reality in this sandbox: the only reachable timestamped news dataset is
INDEX-LEVEL (Reddit r/worldnews top-25 daily headlines, 2008-06..2016-07 —
the Kaggle 'stocknews' set via a GitHub mirror). Per-stock news (the form
with actual literature support for cross-sectional alpha) is not reachable.

What index-level sentiment can and cannot do for a CROSS-SECTIONAL ranker:
it is constant across stocks on a date, so it cannot rank stocks by itself;
it can only help nonlinear models CONDITION stock features on the news regime
(e.g. momentum behaves differently after bad-news weeks). Expected effect
per the literature: ~0 at this granularity. This experiment measures it
anyway, honestly:

  ARM A (BASE): the 25 existing features
  ARM B (NEWS): + 2 news features (mean VADER compound, share of negative
                headlines), trailing-252d z-scored (point-in-time), aligned
                so signal date t uses only headlines dated <= t
  Same models (ridge, lightgbm), same folds, IDENTICAL evaluation dates
  (news-covered test days only). 4 trials -> ledger.

Timestamp discipline: headlines are the day's top-voted posts, dated day t;
execution is at close(t+1) — a full trading day after the news day closes.
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
from stocklab.data.panel import apply_universe_filters
from stocklab.features.pipeline import build_dataset, FeatureDataset
from stocklab.features.technical import trailing_zscore
from stocklab.validation.walkforward import WalkForwardSplitter
from stocklab.models.baselines import RidgeModel, LightGBMModel
from stocklab.backtest.metrics import _filter_min_names, _spearman_by_date, newey_west_tstat
from stocklab.backtest.engine import backtest_long_short
from stocklab.neutralize import neutralize_scores
from run_experiment import read_ledger, append_ledger

NEWS_CSV = Path(__file__).resolve().parents[1] / "data_cache" / "Combined_News_DJIA.csv"


def build_news_features() -> pd.DataFrame:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    df = pd.read_csv(NEWS_CSV, parse_dates=["Date"]).set_index("Date").sort_index()
    heads = df[[c for c in df.columns if c.startswith("Top")]]

    an = SentimentIntensityAnalyzer()
    cache: dict[str, float] = {}

    def score(x) -> float:
        if not isinstance(x, str) or not x:
            return np.nan
        t = x.strip()
        if t.startswith(("b'", 'b"')):
            t = t[2:-1]
        if t in cache:
            return cache[t]
        v = an.polarity_scores(t)["compound"]
        cache[t] = v
        return v

    comp = heads.map(score)
    out = pd.DataFrame(index=df.index)
    out["news_compound"] = comp.mean(axis=1)
    out["news_neg_share"] = (comp < -0.05).mean(axis=1)
    return out


def main() -> None:
    cfg = ExperimentConfig(backtest=BacktestConfig(neutralize=("beta_63",)))
    panel, _ = load_bundled()
    panel, _ = apply_universe_filters(
        panel, cfg.universe.min_history, cfg.universe.min_price,
        cfg.universe.min_dollar_volume,
    )
    ds_base = build_dataset(panel, cfg)

    news = build_news_features()
    news_end = news.index.max()
    print(f"news coverage: {news.index.min().date()} .. {news_end.date()} ({len(news)} days)")

    # PIT normalization, then align to the trading grid: signal date t gets the
    # most recent news dated <= t (weekend/holiday carry, max 3 days)
    news_z = pd.DataFrame({c: trailing_zscore(news[c]) for c in news.columns})
    news_on_grid = news_z.reindex(
        news_z.index.union(panel.dates)).ffill(limit=3).reindex(panel.dates)

    X_news = ds_base.X.copy()
    for c in news_z.columns:
        X_news[c] = news_on_grid[c].reindex(
            X_news.index.get_level_values("date")).to_numpy()
    ok = np.isfinite(X_news[list(news_z.columns)].to_numpy()).all(axis=1)
    X_news = X_news.loc[ok]
    ds_news = FeatureDataset(
        X=X_news, y=ds_base.y.loc[X_news.index], fwd_ret=ds_base.fwd_ret.loc[X_news.index],
        feature_names=list(X_news.columns), config=cfg,
        ranked_features=ds_base.ranked_features,
    )

    labeled = pd.DatetimeIndex(
        ds_news.fwd_ret.dropna().index.get_level_values("date").unique()
    ).sort_values()
    labeled = labeled[labeled <= news_end - pd.Timedelta(days=10)]
    folds = WalkForwardSplitter(cfg).split(labeled)
    cutoff = pd.Timestamp(cfg.split.holdout_start)
    folds = [f for f in folds if f.test_dates[-1] < cutoff]
    eval_dates = pd.DatetimeIndex(
        sorted({d for f in folds for d in f.test_dates}))
    print(f"{len(folds)} folds, {len(eval_dates)} news-covered evaluation days "
          f"({eval_dates.min().date()} .. {eval_dates.max().date()})")

    exposures = ds_base.ranked_features[["beta_63"]]
    rows = []
    for arm, ds in (("BASE", ds_base), ("NEWS", ds_news)):
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
            scores = scores[scores.index.get_level_values("date").isin(eval_dates)]
            scores = neutralize_scores(scores, exposures)
            df = pd.DataFrame({"s": scores, "f": ds.fwd_ret.loc[scores.index]}).dropna()
            df = _filter_min_names(df, 20)
            ic = _spearman_by_date(df)
            bt = backtest_long_short(
                f"{arm}/{model_name}", scores, panel.close,
                horizon=cfg.label.horizon, lag=cfg.label.lag,
                n_quantiles=cfg.backtest.n_quantiles, cost_bps=cfg.backtest.cost_bps,
            )
            row = {
                "arm": arm, "model": model_name,
                "ic": round(float(ic.mean()), 4),
                "nw_t": round(newey_west_tstat(ic, 2 * cfg.label.horizon), 2),
                "net_sharpe": round(bt.stats_net.get("sharpe", np.nan), 2),
                "n_days": int(len(ic)),
            }
            rows.append(row)
            print(f"{arm:5s} {model_name:9s} IC={row['ic']:+.4f} t={row['nw_t']:+.2f} "
                  f"netShp={row['net_sharpe']:+.2f} n={row['n_days']}")

    out = pd.DataFrame(rows)
    outdir = Path("experiments/news_sentiment")
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "results.csv", index=False)

    deltas = {}
    for mn in ("ridge", "lightgbm"):
        b = out[(out.arm == "BASE") & (out.model == mn)]["ic"].iloc[0]
        n = out[(out.arm == "NEWS") & (out.model == mn)]["ic"].iloc[0]
        deltas[mn] = round(n - b, 4)
    summary = {
        "news_dataset": "Reddit r/worldnews top-25 daily (index-level), Kaggle "
                        "'stocknews' via GitHub mirror; VADER sentiment",
        "limitation": "index-level sentiment is constant per date; it cannot rank "
                      "stocks directly, only condition nonlinear models",
        "ic_delta_news_minus_base": deltas,
        "verdict": "no meaningful improvement" if all(abs(v) < 0.01 for v in deltas.values())
                   else "delta exceeds 0.01 — inspect before believing",
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\nIC deltas (NEWS - BASE):", deltas)
    print("verdict:", summary["verdict"])

    append_ledger({
        "at": datetime.now(timezone.utc).isoformat(),
        "out": str(outdir), "models": ["news_sentiment_ab"],
        "n_new_trials": 4, "include_holdout": False,
    })
    print("ledger total:", read_ledger()["total_trials"])


if __name__ == "__main__":
    main()
