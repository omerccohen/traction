"""Purged walk-forward splits with embargo.

Why not plain K-fold: k-day forward labels overlap in time, so a random split
puts rows in the training set whose label windows cover test dates — textbook
leakage (López de Prado, *Advances in Financial ML*, ch. 7). We therefore:

1. split by DATE, never by row;
2. train only on dates whose ENTIRE label window [t+lag, t+lag+horizon] ends
   before the first test date ("purging");
3. leave an extra `embargo` days of buffer for slower-moving dependence
   (volatility clustering, feature autocorrelation).

Folds roll forward through time and models are retrained each fold — the only
honest simulation of how the system would actually have been run.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import ExperimentConfig


@dataclass(frozen=True)
class Fold:
    index: int
    train_dates: pd.DatetimeIndex
    test_dates: pd.DatetimeIndex

    def __repr__(self) -> str:  # readable fold logging
        return (
            f"Fold {self.index}: train {self.train_dates[0].date()}..{self.train_dates[-1].date()} "
            f"({len(self.train_dates)}d) -> test {self.test_dates[0].date()}..{self.test_dates[-1].date()} "
            f"({len(self.test_dates)}d)"
        )


class WalkForwardSplitter:
    """Expanding-window walk-forward over the trading-date grid."""

    def __init__(self, config: ExperimentConfig):
        self.cfg = config

    @property
    def gap(self) -> int:
        """Trading days between last train date and first test date."""
        return self.cfg.train_test_gap  # purge (horizon+lag) + embargo

    def split(self, dates: pd.DatetimeIndex) -> list[Fold]:
        dates = pd.DatetimeIndex(dates).sort_values().unique()
        n = len(dates)
        min_train = self.cfg.split.min_train_days
        span = self.cfg.split.test_span
        gap = self.gap

        folds: list[Fold] = []
        start = min_train + gap  # first test index
        i = 0
        while start < n:
            test = dates[start : start + span]
            # last train index = start - gap, leaving exactly gap-1 dates
            # strictly between train end and test start — the minimal spacing
            # that satisfies purge+embargo (off-by-one forfeited a train day
            # per fold; review finding N3)
            train = dates[: start - gap + 1]
            if len(train) >= min_train and len(test) > 0:
                folds.append(Fold(index=i, train_dates=train, test_dates=test))
                i += 1
            start += span
        if not folds:
            raise ValueError(
                f"Not enough dates ({n}) for min_train_days={min_train} + gap={gap}"
            )
        return folds

    def audit(self, folds: list[Fold], dates: pd.DatetimeIndex) -> None:
        """Assert the purge property against the FULL trading grid.

        The gap days belong to neither train nor test, so the distance must be
        measured on the complete date grid — measuring on train∪test (an
        earlier bug caught by tests) always reports zero gap.
        """
        gap = self.gap
        grid = pd.DatetimeIndex(dates).sort_values().unique()
        for f in folds:
            if len(f.train_dates.intersection(f.test_dates)) > 0:
                raise AssertionError(f"fold {f.index}: train/test overlap")
            last_train = f.train_dates[-1]
            first_test = f.test_dates[0]
            if last_train >= first_test:
                raise AssertionError(f"fold {f.index}: train does not precede test")
            n_between = int(((grid > last_train) & (grid < first_test)).sum())
            if n_between < gap - 1:
                raise AssertionError(
                    f"fold {f.index}: only {n_between} dates between train end and "
                    f"test start; need >= {gap - 1} (purge+embargo)"
                )
