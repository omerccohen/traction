"""Model interface + shared helpers.

A Model consumes a FeatureDataset restricted to given dates. The walk-forward
runner guarantees train/test date hygiene; models must not look at any date
they were not given (and cannot: they receive row subsets, not the panel).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd

from ..features.pipeline import FeatureDataset


@runtime_checkable
class Model(Protocol):
    name: str

    def fit(self, ds: FeatureDataset, train_dates: pd.DatetimeIndex) -> None: ...

    def predict(self, ds: FeatureDataset, dates: pd.DatetimeIndex) -> pd.Series: ...


def rows_for(ds: FeatureDataset, dates: pd.DatetimeIndex) -> pd.Index:
    mask = ds.X.index.get_level_values("date").isin(dates)
    return ds.X.index[mask]


def date_train_val_split(
    train_dates: pd.DatetimeIndex, val_frac: float = 0.12, purge: int = 6
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Date-based train/validation split with a purge gap.

    Validation is the LAST block of training dates (closest to the test period,
    the most honest early-stopping proxy), separated by `purge` days so
    overlapping labels don't straddle the split.
    """
    n = len(train_dates)
    n_val = max(int(n * val_frac), 30)
    if n_val + purge + 60 > n:
        n_val = max(n // 5, 10)
    val = train_dates[-n_val:]
    tr = train_dates[: n - n_val - purge]
    return tr, val


def to_series(index: pd.Index, values: np.ndarray, name: str) -> pd.Series:
    s = pd.Series(np.asarray(values, dtype=float).ravel(), index=index, name=name)
    return s
