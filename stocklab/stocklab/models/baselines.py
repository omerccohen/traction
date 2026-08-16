"""Baseline models — the rungs every fancy model must out-climb.

1. MomentumBaseline: score = 12-1 momentum rank. Zero learned parameters.
   Decades of literature; if your neural net can't beat this, it is worse
   than a 1993 paper.
2. RidgeModel: heavily regularized linear model. GKX (2020) found this class
   surprisingly hard to beat.
3. LightGBMModel: gradient boosting — the strongest known prior for tabular
   cross-sectional data (Qlib benchmark leader among single models).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import rows_for, to_series
from ..features.pipeline import FeatureDataset


class MomentumBaseline:
    """score(t) = cross-sectional rank of 12-1 momentum at t. No fitting."""

    name = "momentum_12_1"

    def fit(self, ds: FeatureDataset, train_dates: pd.DatetimeIndex) -> None:
        return None

    def predict(self, ds: FeatureDataset, dates: pd.DatetimeIndex) -> pd.Series:
        idx = rows_for(ds, dates)
        return to_series(idx, ds.X.loc[idx, "mom_12_1"].to_numpy(), self.name)


class RidgeModel:
    name = "ridge"

    def __init__(self, alpha: float = 100.0):
        from sklearn.linear_model import Ridge

        self.alpha = alpha
        self._cls = Ridge
        self._m = None

    def fit(self, ds: FeatureDataset, train_dates: pd.DatetimeIndex) -> None:
        idx = rows_for(ds, train_dates)
        X = ds.X.loc[idx].to_numpy(dtype=np.float64)
        y = ds.y.loc[idx].to_numpy(dtype=np.float64)
        ok = np.isfinite(y)
        self._m = self._cls(alpha=self.alpha)
        self._m.fit(X[ok], y[ok])

    def predict(self, ds: FeatureDataset, dates: pd.DatetimeIndex) -> pd.Series:
        idx = rows_for(ds, dates)
        X = ds.X.loc[idx].to_numpy(dtype=np.float64)
        return to_series(idx, self._m.predict(X), self.name)


class LightGBMModel:
    name = "lightgbm"

    def __init__(self, seed: int = 7, **overrides):
        self.params = dict(
            objective="regression",
            n_estimators=400,
            learning_rate=0.03,
            num_leaves=31,
            max_depth=-1,
            min_child_samples=200,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=seed,
            n_jobs=-1,
            verbose=-1,
        )
        self.params.update(overrides)
        self._m = None

    def fit(self, ds: FeatureDataset, train_dates: pd.DatetimeIndex) -> None:
        import lightgbm as lgb
        from .base import date_train_val_split

        tr_dates, val_dates = date_train_val_split(
            train_dates, purge=ds.config.purge
        )
        tr_idx = rows_for(ds, tr_dates)
        va_idx = rows_for(ds, val_dates)
        Xtr = ds.X.loc[tr_idx].to_numpy(dtype=np.float64)
        ytr = ds.y.loc[tr_idx].to_numpy(dtype=np.float64)
        Xva = ds.X.loc[va_idx].to_numpy(dtype=np.float64)
        yva = ds.y.loc[va_idx].to_numpy(dtype=np.float64)
        ok_tr, ok_va = np.isfinite(ytr), np.isfinite(yva)

        self._m = lgb.LGBMRegressor(**self.params)
        self._m.fit(
            Xtr[ok_tr], ytr[ok_tr],
            eval_set=[(Xva[ok_va], yva[ok_va])],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
        )

    def predict(self, ds: FeatureDataset, dates: pd.DatetimeIndex) -> pd.Series:
        idx = rows_for(ds, dates)
        X = ds.X.loc[idx].to_numpy(dtype=np.float64)
        return to_series(idx, self._m.predict(X), self.name)

    def feature_importance(self, ds: FeatureDataset) -> pd.Series:
        if self._m is None:
            raise RuntimeError("fit first")
        return pd.Series(
            self._m.feature_importances_, index=ds.feature_names
        ).sort_values(ascending=False)
