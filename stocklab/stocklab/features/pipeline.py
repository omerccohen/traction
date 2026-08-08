"""Assemble the modeling dataset: features + labels in aligned long form.

Normalization policy (leakage-safe by construction — no fitted scalers):
* stock features  -> per-date cross-sectional rank in [-1, 1]
* market features -> trailing 252d z-score (rolling window ending at t)

The result keeps THREE aligned pieces:
  X          long-form feature matrix, index (date, ticker)
  y          training target (rank/demeaned forward return)
  fwd_ret    raw forward returns for evaluation & backtesting
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import ExperimentConfig
from ..data.panel import Panel, eligibility_mask
from ..labels import forward_returns, cross_sectional_rank, make_target
from .technical import (
    compute_stock_features,
    compute_market_features,
    trailing_zscore,
    STOCK_FEATURES,
    MARKET_FEATURES,
)


@dataclass
class FeatureDataset:
    X: pd.DataFrame            # index (date, ticker), columns = feature names
    y: pd.Series               # training target aligned with X
    fwd_ret: pd.Series         # raw forward return aligned with X (NaN for live rows)
    feature_names: list[str]
    config: ExperimentConfig
    ranked_features: pd.DataFrame = field(repr=False, default=None)  # wide store for sequences

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.X.index.get_level_values("date").unique()).sort_values()

    def rows_for_dates(self, dates: pd.DatetimeIndex) -> pd.Index:
        mask = self.X.index.get_level_values("date").isin(dates)
        return self.X.index[mask]

    def summary(self) -> str:
        return (
            f"FeatureDataset: {len(self.X):,} rows, {len(self.feature_names)} features, "
            f"{len(self.dates)} dates ({self.dates[0].date()} -> {self.dates[-1].date()})"
        )


def build_dataset(
    panel: Panel,
    config: ExperimentConfig | None = None,
    include_live_rows: bool = True,
) -> FeatureDataset:
    """Compute features + labels and return the aligned modeling dataset.

    Rows are kept when: ticker is point-in-time eligible, all features are
    finite, and the label exists — except the trailing `horizon+lag` dates,
    which are kept with NaN labels when include_live_rows=True (these are the
    rows you score for a live ranking; they can never enter training).
    """
    cfg = config or ExperimentConfig()

    stock_feats = compute_stock_features(panel)
    mkt_feats_raw = compute_market_features(panel)
    eligible = eligibility_mask(
        panel, cfg.universe.min_history, cfg.universe.min_price,
        cfg.universe.min_dollar_volume,
    )
    fwd = forward_returns(panel, cfg.label.horizon, cfg.label.lag)
    # target ranks are computed WITHIN the eligible universe: a not-yet-eligible
    # listing's extreme week must not perturb eligible names' training target
    # (review finding m2 — features and labels must describe the same universe)
    target = make_target(fwd.where(eligible), cfg.label.target)

    # --- normalize -----------------------------------------------------------
    ranked: dict[str, pd.DataFrame] = {}
    for name in STOCK_FEATURES:
        wide = stock_feats[name].where(eligible)
        ranked[name] = cross_sectional_rank(wide)

    mkt_norm = pd.DataFrame(
        {name: trailing_zscore(mkt_feats_raw[name]) for name in MARKET_FEATURES}
    )

    # --- stack to long form --------------------------------------------------
    long_parts = {}
    for name in STOCK_FEATURES:
        s = ranked[name].stack()
        s.name = name
        long_parts[name] = s
    X = pd.DataFrame(long_parts)
    X.index.names = ["date", "ticker"]

    for name in MARKET_FEATURES:
        X[name] = mkt_norm[name].reindex(X.index.get_level_values("date")).to_numpy()

    y_long = target.stack()
    fwd_long = fwd.stack()
    X["__y"] = y_long
    X["__fwd"] = fwd_long

    feature_names = STOCK_FEATURES + MARKET_FEATURES

    # completeness: all features finite
    feat_ok = np.isfinite(X[feature_names].to_numpy()).all(axis=1)
    has_label = X["__fwd"].notna().to_numpy()

    dates_all = X.index.get_level_values("date")
    last_labelable = panel.dates[-(cfg.label.horizon + cfg.label.lag) - 1]
    is_live = dates_all > last_labelable

    keep = feat_ok & (has_label | (is_live if include_live_rows else False))
    X = X.loc[keep]

    y = X.pop("__y")
    fwd_ret = X.pop("__fwd")
    X = X.sort_index()
    y = y.loc[X.index]
    fwd_ret = fwd_ret.loc[X.index]

    ranked_store = pd.DataFrame({k: v.stack() for k, v in ranked.items()})
    ranked_store.index.names = ["date", "ticker"]

    return FeatureDataset(
        X=X, y=y, fwd_ret=fwd_ret, feature_names=feature_names,
        config=cfg, ranked_features=ranked_store,
    )
