"""Walk-forward split hygiene: purge + embargo, no overlap, audit works."""
import pandas as pd
import pytest

from stocklab.config import ExperimentConfig, SplitConfig, LabelConfig
from stocklab.validation.walkforward import WalkForwardSplitter


def _dates(n=900):
    return pd.bdate_range("2015-01-01", periods=n)


def test_gap_between_train_and_test():
    cfg = ExperimentConfig()
    sp = WalkForwardSplitter(cfg)
    folds = sp.split(_dates())
    grid = _dates()
    for f in folds:
        last_train, first_test = f.train_dates[-1], f.test_dates[0]
        between = grid[(grid > last_train) & (grid < first_test)]
        # gap = purge + embargo trading days means exactly gap-1 dates strictly between
        assert len(between) >= sp.gap - 1, f"fold {f.index}: gap violated"


def test_no_overlap_and_monotone():
    cfg = ExperimentConfig()
    folds = WalkForwardSplitter(cfg).split(_dates())
    for f in folds:
        assert len(f.train_dates.intersection(f.test_dates)) == 0
        assert f.train_dates[-1] < f.test_dates[0]
    for a, b in zip(folds[:-1], folds[1:]):
        assert a.test_dates[-1] < b.test_dates[0]


def test_audit_passes_and_catches_violation():
    cfg = ExperimentConfig()
    sp = WalkForwardSplitter(cfg)
    grid = _dates()
    folds = sp.split(grid)
    sp.audit(folds, grid)  # must not raise

    # forge a violating fold: train reaching into the gap
    from stocklab.validation.walkforward import Fold
    bad = Fold(
        index=99,
        train_dates=grid[:700],  # train right up to test start
        test_dates=grid[701:750],
    )
    with pytest.raises(AssertionError):
        sp.audit([bad], grid)


def test_purge_scales_with_horizon():
    cfg_short = ExperimentConfig(label=LabelConfig(horizon=1))
    cfg_long = ExperimentConfig(label=LabelConfig(horizon=21))
    assert WalkForwardSplitter(cfg_long).gap > WalkForwardSplitter(cfg_short).gap
