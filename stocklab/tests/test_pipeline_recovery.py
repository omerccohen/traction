"""End-to-end pipeline verification on synthetic markets.

1. PLANTED SIGNAL: on a market with planted momentum+reversal, the pipeline
   (features -> walk-forward ridge) must recover positive OOS IC.
2. NULL MARKET: with no planted signal, the same pipeline must report IC ~ 0.
3. SHUFFLED LABELS: IC must collapse on date-shuffled labels.
4. CANARY: an injected future-return feature must send IC through the roof
   (proves the metric detects leakage when it exists).

A pipeline that fails 1 is broken; a pipeline that "passes" 2-4 wrongly is
worse than broken — it is a leak-generating machine.
"""
import numpy as np
import pandas as pd
import pytest

from stocklab.config import ExperimentConfig, SplitConfig, UniverseConfig
from stocklab.data.synthetic import make_synthetic_market
from stocklab.features.pipeline import build_dataset, FeatureDataset
from stocklab.models.baselines import RidgeModel
from stocklab.validation.walkforward import WalkForwardSplitter
from stocklab.validation import leakage
from stocklab.backtest.metrics import signal_report


CFG = ExperimentConfig(
    universe=UniverseConfig(min_history=260, min_price=0.0, min_dollar_volume=0.0),
    split=SplitConfig(min_train_days=320, test_span=63, embargo=5),
)


def _oos_ic(panel, cfg=CFG, shuffle_seed=None, canary=False):
    ds = build_dataset(panel, cfg)
    if shuffle_seed is not None:
        y = leakage.shuffle_labels_within_dates(ds.y, seed=shuffle_seed)
        ds = FeatureDataset(X=ds.X, y=y, fwd_ret=ds.fwd_ret,
                            feature_names=ds.feature_names, config=cfg,
                            ranked_features=ds.ranked_features)
    if canary:
        X = leakage.inject_canary(ds.X, ds.fwd_ret)
        ds = FeatureDataset(X=X, y=ds.y, fwd_ret=ds.fwd_ret,
                            feature_names=ds.feature_names + ["__canary"], config=cfg,
                            ranked_features=ds.ranked_features)

    labeled = pd.DatetimeIndex(ds.fwd_ret.dropna().index.get_level_values("date").unique()).sort_values()
    folds = WalkForwardSplitter(cfg).split(labeled)
    parts = []
    for f in folds:
        m = RidgeModel(alpha=10.0)
        m.fit(ds, f.train_dates)
        parts.append(m.predict(ds, f.test_dates))
    scores = pd.concat(parts).sort_index()
    target = ds.y if shuffle_seed is not None else ds.fwd_ret
    rep = signal_report("t", scores, target.loc[scores.index], horizon=cfg.label.horizon, n_quantiles=5)
    return rep.ic_mean


@pytest.fixture(scope="module")
def planted():
    return make_synthetic_market(n_days=750, n_tickers=60, momentum_strength=0.12,
                                 reversal_strength=0.12, seed=11)


@pytest.fixture(scope="module")
def null_market():
    return make_synthetic_market(n_days=750, n_tickers=60, momentum_strength=0.0,
                                 reversal_strength=0.0, seed=12)


def test_recovers_planted_signal(planted):
    ic = _oos_ic(planted)
    assert ic > 0.02, f"pipeline failed to recover planted signal (IC={ic:.4f})"


def test_null_market_reports_nothing(null_market):
    ic = _oos_ic(null_market)
    assert abs(ic) < 0.02, f"pipeline hallucinates signal on pure noise (IC={ic:.4f})"


def test_shuffled_labels_collapse(planted):
    ic = _oos_ic(planted, shuffle_seed=1)
    assert abs(ic) < 0.02, f"pipeline leaks: shuffled-label IC={ic:.4f}"


def test_canary_detected(planted):
    ic = _oos_ic(planted, canary=True)
    assert ic > 0.30, f"planted future-return feature NOT detected (IC={ic:.4f}) — metric is broken"
