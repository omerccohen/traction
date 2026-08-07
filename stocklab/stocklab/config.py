"""Central configuration for experiments.

Every timing constant that protects against lookahead lives here, with the
rationale attached. Change them consciously.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class LabelConfig:
    # Forward-return horizon in trading days.
    horizon: int = 5
    # Execution lag: signal at close(t) -> position at close(t + lag).
    # lag=1 means you can never trade the close you computed the signal on.
    lag: int = 1
    # Training target transform: 'rank' (per-date rank in [-1,1], robust) or
    # 'demean' (per-date demeaned raw return).
    target: str = "rank"


@dataclass(frozen=True)
class UniverseConfig:
    min_history: int = 300          # obs needed before a ticker becomes eligible
    min_price: float = 5.0          # median close below this -> excluded (penny names)
    min_dollar_volume: float = 1e6  # median daily dollar volume floor (liquidity)


@dataclass(frozen=True)
class SplitConfig:
    min_train_days: int = 550   # ~2.2 years before the first prediction
    test_span: int = 63         # one quarter per fold, retrain each fold
    embargo: int = 5            # extra buffer beyond the label-overlap purge
    # Purge is computed as label.horizon + label.lag (the label window length);
    # total train/test gap = purge + embargo trading days.


@dataclass(frozen=True)
class BacktestConfig:
    n_quantiles: int = 10
    cost_bps: float = 10.0                     # per side, on traded notional
    cost_grid: tuple = (0.0, 5.0, 10.0, 25.0)  # sensitivity always reported
    ann_factor: int = 252


@dataclass(frozen=True)
class SequenceConfig:
    length: int = 40         # lookback window for LSTM/Transformer
    train_stride: int = 2    # sample every Nth day when building train sequences
    features: tuple = (
        "ret_1d", "ret_5d", "mom_21", "mom_63", "mom_12_1",
        "vol_21", "boll_z", "pct_from_high_252", "rsi_14", "log_adv_21",
    )


@dataclass(frozen=True)
class ExperimentConfig:
    label: LabelConfig = field(default_factory=LabelConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    sequence: SequenceConfig = field(default_factory=SequenceConfig)
    seed: int = 7

    @property
    def purge(self) -> int:
        """Trading days a training label can see past its signal date."""
        return self.label.horizon + self.label.lag

    @property
    def train_test_gap(self) -> int:
        return self.purge + self.split.embargo

    def to_dict(self) -> dict:
        return asdict(self)
