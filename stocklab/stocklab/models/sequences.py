"""Sequence sample construction for LSTM/Transformer models.

Builds a float32 cube [n_dates, n_tickers, n_features] from the per-date
rank-transformed feature store, then serves (sample, seq_len, n_features)
windows ending at requested signal dates.

Point-in-time note: a window ending at signal date t contains features from
t-L+1 .. t — strictly past/present information. Windows for early test dates
reach back into the train period's FEATURES, which is correct and unavoidable
(features are observable history); what must never cross the boundary is
LABEL information, which the walk-forward purge handles.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..features.pipeline import FeatureDataset


@dataclass
class SequenceBatch:
    X: np.ndarray            # (n, L, F) float32
    y: np.ndarray | None     # (n,) float32 or None for scoring
    index: pd.Index          # (date, ticker) MultiIndex of samples


class SequenceStore:
    def __init__(self, ds: FeatureDataset, features: list[str], length: int):
        self.length = length
        self.features = list(features)

        wide_per_feat = []
        base = ds.ranked_features[self.features]
        for f in self.features:
            w = base[f].unstack("ticker")
            wide_per_feat.append(w)
        self.dates = wide_per_feat[0].index
        self.tickers = wide_per_feat[0].columns
        # cube: dates x tickers x feats
        self.cube = np.stack(
            [w.to_numpy(dtype=np.float32) for w in wide_per_feat], axis=2
        )
        self.date_pos = {d: i for i, d in enumerate(self.dates)}

        # windows[t] = cube[t-L+1 .. t]  -> shape (n_dates-L+1, L, tickers, feats)
        sw = np.lib.stride_tricks.sliding_window_view(self.cube, length, axis=0)
        # sliding_window_view returns (n_dates-L+1, tickers, feats, L)
        self.windows = np.moveaxis(sw, -1, 1)  # (n_win, L, tickers, feats)
        self.first_full_date_pos = length - 1

    def batch_for(
        self,
        ds: FeatureDataset,
        dates: pd.DatetimeIndex,
        with_labels: bool,
        stride: int = 1,
    ) -> SequenceBatch:
        """Assemble sequence samples for the requested signal dates.

        Samples require: full finite window, and (if with_labels) a finite
        training target for (date, ticker).
        """
        use_dates = [d for d in dates if d in self.date_pos and self.date_pos[d] >= self.first_full_date_pos]
        if stride > 1:
            use_dates = use_dates[::stride]

        def _empty() -> SequenceBatch:
            return SequenceBatch(
                np.empty((0, self.length, len(self.features)), np.float32),
                np.empty((0,), np.float32) if with_labels else None,
                pd.MultiIndex.from_tuples([], names=["date", "ticker"]),
            )

        if not use_dates:
            return _empty()

        y_lookup = ds.y if with_labels else None
        Xs, ys, idx_tuples = [], [], []
        for d in use_dates:
            p = self.date_pos[d]
            win = self.windows[p - self.first_full_date_pos]  # (L, tickers, feats)
            finite = np.isfinite(win).all(axis=(0, 2))         # per ticker
            if with_labels:
                try:
                    yd = y_lookup.xs(d, level="date")
                except KeyError:
                    continue
                yd = yd.reindex(self.tickers)
                ok = finite & np.isfinite(yd.to_numpy(dtype=np.float64))
            else:
                ok = finite
            cols = np.where(ok)[0]
            if len(cols) == 0:
                continue
            Xs.append(win[:, cols, :].transpose(1, 0, 2))  # (n_ok, L, F)
            if with_labels:
                ys.append(yd.to_numpy(dtype=np.float32)[cols])
            idx_tuples.extend((d, self.tickers[c]) for c in cols)

        if not Xs:
            return _empty()
        X = np.concatenate(Xs, axis=0).astype(np.float32, copy=False)
        y = np.concatenate(ys).astype(np.float32, copy=False) if with_labels else None
        index = pd.MultiIndex.from_tuples(idx_tuples, names=["date", "ticker"])
        return SequenceBatch(X=X, y=y, index=index)
