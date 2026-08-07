"""Deep models (Keras / tensorflow-cpu): tabular MLP, LSTM, small Transformer.

Deliberately small, per the empirical-finance evidence (GKX 2020: shallow
beats deep; Qlib benchmarks: LSTM/Transformer trail LightGBM on engineered
features). Their job here is to earn their place against the baselines, not
to be impressive.

Seed discipline: single deep fits are unstable; KerasMLP averages `n_seeds`
independent fits. Sequence models default to fewer seeds for CPU-time reasons
— reported results carry that caveat.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from .base import rows_for, to_series, date_train_val_split
from .sequences import SequenceStore
from ..features.pipeline import FeatureDataset


def _tf():
    import tensorflow as tf

    tf.get_logger().setLevel("ERROR")
    return tf


def _fit_keras(model, Xtr, ytr, Xva, yva, epochs: int, batch: int, patience: int):
    tf = _tf()
    es = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=patience, restore_best_weights=True
    )
    model.fit(
        Xtr, ytr,
        validation_data=(Xva, yva),
        epochs=epochs, batch_size=batch,
        callbacks=[es], verbose=0, shuffle=True,
    )
    return model


class KerasMLP:
    """2-hidden-layer MLP on tabular features, averaged over seeds."""

    name = "mlp"

    def __init__(self, n_seeds: int = 3, hidden=(64, 32), dropout: float = 0.3,
                 epochs: int = 30, batch: int = 1024, lr: float = 1e-3):
        self.n_seeds = n_seeds
        self.hidden = hidden
        self.dropout = dropout
        self.epochs = epochs
        self.batch = batch
        self.lr = lr
        self._models: list = []

    def _build(self, n_feats: int, seed: int):
        tf = _tf()
        tf.keras.utils.set_random_seed(seed)
        inp = tf.keras.Input(shape=(n_feats,))
        x = inp
        for h in self.hidden:
            x = tf.keras.layers.Dense(h, activation="relu")(x)
            x = tf.keras.layers.Dropout(self.dropout)(x)
        out = tf.keras.layers.Dense(1)(x)
        m = tf.keras.Model(inp, out)
        m.compile(optimizer=tf.keras.optimizers.Adam(self.lr), loss="mse")
        return m

    def fit(self, ds: FeatureDataset, train_dates: pd.DatetimeIndex) -> None:
        tr_dates, val_dates = date_train_val_split(train_dates, purge=ds.config.purge)
        tr_idx, va_idx = rows_for(ds, tr_dates), rows_for(ds, val_dates)
        Xtr = ds.X.loc[tr_idx].to_numpy(np.float32)
        ytr = ds.y.loc[tr_idx].to_numpy(np.float32)
        Xva = ds.X.loc[va_idx].to_numpy(np.float32)
        yva = ds.y.loc[va_idx].to_numpy(np.float32)
        ok_tr, ok_va = np.isfinite(ytr), np.isfinite(yva)

        self._models = []
        for s in range(self.n_seeds):
            m = self._build(Xtr.shape[1], seed=1000 + s)
            m = _fit_keras(m, Xtr[ok_tr], ytr[ok_tr], Xva[ok_va], yva[ok_va],
                           self.epochs, self.batch, patience=3)
            self._models.append(m)

    def predict(self, ds: FeatureDataset, dates: pd.DatetimeIndex) -> pd.Series:
        idx = rows_for(ds, dates)
        X = ds.X.loc[idx].to_numpy(np.float32)
        preds = np.mean([m.predict(X, verbose=0).ravel() for m in self._models], axis=0)
        return to_series(idx, preds, self.name)


class _SequenceModelBase:
    """Shared fit/predict plumbing for LSTM/Transformer."""

    name = "sequence_base"

    def __init__(self, store: SequenceStore, n_seeds: int = 2,
                 epochs: int = 15, batch: int = 512, lr: float = 1e-3,
                 train_stride: int = 2):
        self.store = store
        self.n_seeds = n_seeds
        self.epochs = epochs
        self.batch = batch
        self.lr = lr
        self.train_stride = train_stride
        self._models: list = []

    def _build(self, L: int, F: int, seed: int):  # pragma: no cover - abstract
        raise NotImplementedError

    def fit(self, ds: FeatureDataset, train_dates: pd.DatetimeIndex) -> None:
        tr_dates, val_dates = date_train_val_split(train_dates, purge=ds.config.purge)
        tr = self.store.batch_for(ds, pd.DatetimeIndex(tr_dates), with_labels=True,
                                  stride=self.train_stride)
        va = self.store.batch_for(ds, pd.DatetimeIndex(val_dates), with_labels=True,
                                  stride=self.train_stride)
        if len(tr.X) < 1000 or len(va.X) < 200:
            raise RuntimeError(f"{self.name}: not enough sequence samples to train")
        self._models = []
        for s in range(self.n_seeds):
            m = self._build(tr.X.shape[1], tr.X.shape[2], seed=2000 + s)
            m = _fit_keras(m, tr.X, tr.y, va.X, va.y, self.epochs, self.batch, patience=2)
            self._models.append(m)

    def predict(self, ds: FeatureDataset, dates: pd.DatetimeIndex) -> pd.Series:
        b = self.store.batch_for(ds, pd.DatetimeIndex(dates), with_labels=False, stride=1)
        preds = np.mean([m.predict(b.X, verbose=0).ravel() for m in self._models], axis=0)
        return pd.Series(preds, index=b.index, name=self.name)


class KerasLSTM(_SequenceModelBase):
    name = "lstm"

    def _build(self, L: int, F: int, seed: int):
        tf = _tf()
        tf.keras.utils.set_random_seed(seed)
        inp = tf.keras.Input(shape=(L, F))
        x = tf.keras.layers.LSTM(32)(inp)
        x = tf.keras.layers.Dropout(0.2)(x)
        out = tf.keras.layers.Dense(1)(x)
        m = tf.keras.Model(inp, out)
        m.compile(optimizer=tf.keras.optimizers.Adam(self.lr), loss="mse")
        return m


class KerasTransformer(_SequenceModelBase):
    name = "transformer"

    def __init__(self, *args, d_model: int = 32, n_heads: int = 2, n_blocks: int = 2,
                 ff_dim: int = 64, **kwargs):
        super().__init__(*args, **kwargs)
        self.d_model = d_model
        self.n_heads = n_heads
        self.n_blocks = n_blocks
        self.ff_dim = ff_dim

    def _build(self, L: int, F: int, seed: int):
        tf = _tf()
        tf.keras.utils.set_random_seed(seed)
        inp = tf.keras.Input(shape=(L, F))
        x = tf.keras.layers.Dense(self.d_model)(inp)

        # learned positional embedding added to the projected sequence
        positions = tf.range(start=0, limit=L, delta=1)
        pos_emb = tf.keras.layers.Embedding(input_dim=L, output_dim=self.d_model)(positions)
        x = x + pos_emb

        for _ in range(self.n_blocks):
            attn = tf.keras.layers.MultiHeadAttention(
                num_heads=self.n_heads, key_dim=self.d_model // self.n_heads
            )(x, x)
            x = tf.keras.layers.LayerNormalization()(x + attn)
            ff = tf.keras.Sequential([
                tf.keras.layers.Dense(self.ff_dim, activation="relu"),
                tf.keras.layers.Dense(self.d_model),
            ])(x)
            x = tf.keras.layers.LayerNormalization()(x + ff)

        x = tf.keras.layers.GlobalAveragePooling1D()(x)
        x = tf.keras.layers.Dropout(0.2)(x)
        out = tf.keras.layers.Dense(1)(x)
        m = tf.keras.Model(inp, out)
        m.compile(optimizer=tf.keras.optimizers.Adam(self.lr), loss="mse")
        return m
