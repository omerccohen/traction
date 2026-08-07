"""Canonical market panel: wide (date x ticker) OHLCV matrices.

All downstream feature computation is vectorized over these matrices, which
makes point-in-time discipline auditable: every operation is a rolling/shift
on a date-indexed frame, so "uses only the past" is visible in the code.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED_COLS = ("date", "ticker", "close", "volume")


@dataclass
class Panel:
    """Wide-form daily market data. Index: DatetimeIndex (trading days).
    Columns: tickers. Missing entries are NaN (ticker not listed / not traded).
    """

    close: pd.DataFrame
    volume: pd.DataFrame
    open: pd.DataFrame | None = None
    high: pd.DataFrame | None = None
    low: pd.DataFrame | None = None

    def __post_init__(self) -> None:
        idx = self.close.index
        if not idx.is_monotonic_increasing:
            raise ValueError("Panel index must be sorted ascending")
        if idx.has_duplicates:
            raise ValueError("Panel index has duplicate dates")
        for name in ("volume", "open", "high", "low"):
            f = getattr(self, name)
            if f is not None and (not f.index.equals(idx) or not f.columns.equals(self.close.columns)):
                raise ValueError(f"Panel field '{name}' is not aligned with close")

    # ------------------------------------------------------------------
    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.close.index

    @property
    def tickers(self) -> pd.Index:
        return self.close.columns

    @property
    def n_obs(self) -> int:
        return int(self.close.notna().sum().sum())

    def truncate_before(self, date) -> "Panel":
        """Return a panel containing only data strictly up to and including `date`.

        Used by point-in-time tests: features computed on the truncated panel
        must equal features computed on the full panel at `date`.
        """
        m = self.dates <= pd.Timestamp(date)
        return Panel(
            close=self.close.loc[m],
            volume=self.volume.loc[m],
            open=self.open.loc[m] if self.open is not None else None,
            high=self.high.loc[m] if self.high is not None else None,
            low=self.low.loc[m] if self.low is not None else None,
        )

    def select(self, tickers) -> "Panel":
        cols = [t for t in tickers if t in self.close.columns]
        return Panel(
            close=self.close[cols],
            volume=self.volume[cols],
            open=self.open[cols] if self.open is not None else None,
            high=self.high[cols] if self.high is not None else None,
            low=self.low[cols] if self.low is not None else None,
        )

    # ------------------------------------------------------------------
    def dollar_volume(self) -> pd.DataFrame:
        return self.close * self.volume

    def summary(self) -> str:
        return (
            f"Panel: {len(self.dates)} dates ({self.dates[0].date()} -> {self.dates[-1].date()}), "
            f"{len(self.tickers)} tickers, {self.n_obs:,} observations"
        )


def long_to_panel(df: pd.DataFrame) -> Panel:
    """Build a Panel from long-form rows [date, ticker, open?, high?, low?, close, volume]."""
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "ticker"])
    dupes = df.duplicated(["date", "ticker"]).sum()
    if dupes:
        df = df.drop_duplicates(["date", "ticker"], keep="last")

    def pivot(col: str) -> pd.DataFrame | None:
        if col not in df.columns:
            return None
        wide = df.pivot(index="date", columns="ticker", values=col)
        return wide.astype("float64")

    return Panel(
        close=pivot("close"),
        volume=pivot("volume"),
        open=pivot("open"),
        high=pivot("high"),
        low=pivot("low"),
    )


def apply_universe_filters(
    panel: Panel,
    min_history: int = 300,
    min_price: float = 5.0,
    min_dollar_volume: float = 1e6,
) -> tuple[Panel, dict]:
    """Drop tickers that fail basic history/price/liquidity hygiene.

    Fake backtest alpha concentrates in penny and illiquid names whose printed
    prices cannot actually be traded; we remove them up front and report what
    was removed instead of failing silently.
    """
    obs = panel.close.notna().sum()
    med_price = panel.close.median()
    med_dv = panel.dollar_volume().median()

    ok = (obs >= min_history) & (med_price >= min_price) & (med_dv >= min_dollar_volume)
    kept = list(panel.tickers[ok])
    dropped = {
        "short_history": sorted(panel.tickers[obs < min_history]),
        "low_price": sorted(panel.tickers[med_price < min_price]),
        "illiquid": sorted(panel.tickers[med_dv < min_dollar_volume]),
    }
    report = {
        "n_before": len(panel.tickers),
        "n_after": len(kept),
        "dropped": {k: v for k, v in dropped.items() if v},
    }
    return panel.select(kept), report


def eligibility_mask(panel: Panel, min_history: int = 300) -> pd.DataFrame:
    """Point-in-time eligibility: True once a ticker has `min_history` past obs.

    Prevents a subtle bias where a ticker's early, thin history quietly enters
    the cross-section on day one.
    """
    counts = panel.close.notna().cumsum()
    return (counts >= min_history) & panel.close.notna()


def infer_trading_grid(dates: pd.Series) -> pd.DatetimeIndex:
    """Unique sorted trading dates present in the data (no calendar assumptions)."""
    return pd.DatetimeIndex(pd.Series(pd.to_datetime(dates)).drop_duplicates().sort_values())
