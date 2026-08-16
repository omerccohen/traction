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


def eligibility_mask(
    panel: Panel,
    min_history: int = 260,
    min_price: float = 5.0,
    min_dollar_volume: float = 1e6,
    liquidity_window: int = 63,
) -> pd.DataFrame:
    """POINT-IN-TIME eligibility mask (date x ticker).

    A ticker is in the modeled universe at date t iff, using only information
    available at t:
      * it has accumulated >= min_history observations THROUGH t (this count
        includes t itself — close(t) is in the t information set), and
      * its trailing `liquidity_window`-day median close  >= min_price, and
      * its trailing `liquidity_window`-day median dollar volume >= min_dollar_volume,
      * and it actually has a price at t.

    Why trailing medians and not full-sample medians: a full-sample filter
    decides 2014 membership with 2017 information — genuine lookahead. The
    concrete failure (review finding M2): AMD's full-sample median close is
    $3.85, so a static $5 filter deletes it from the whole sample, including
    2016-2018 when it traded >$10 and was a top momentum name. Trailing
    filters admit and evict names as the information arrives, like a live
    system would. (Penny/illiquid names are still excluded — that is where
    fake backtest alpha lives — just excluded point-in-time.)
    """
    counts = panel.close.notna().cumsum()
    hist_ok = counts >= min_history

    med_price = panel.close.rolling(liquidity_window, min_periods=liquidity_window // 2).median()
    med_dv = panel.dollar_volume().rolling(liquidity_window, min_periods=liquidity_window // 2).median()
    liq_ok = (med_price >= min_price) & (med_dv >= min_dollar_volume)

    return hist_ok & liq_ok & panel.close.notna()


def apply_universe_filters(
    panel: Panel,
    min_history: int = 260,
    min_price: float = 5.0,
    min_dollar_volume: float = 1e6,
) -> tuple[Panel, dict]:
    """Static data-hygiene pass: drop tickers that are NEVER point-in-time
    eligible under `eligibility_mask`.

    This is pure column cleanup (memory/speed) — per-date membership is decided
    solely by the point-in-time `eligibility_mask` downstream, so no date's
    cross-section is shaped by information from another date. (The earlier
    version filtered on FULL-SAMPLE medians, which is lookahead — see
    eligibility_mask docstring and docs/SKEPTIC_LOG.md.)
    """
    mask = eligibility_mask(panel, min_history, min_price, min_dollar_volume)
    ever = mask.any()
    kept = list(panel.tickers[ever])
    report = {
        "n_before": len(panel.tickers),
        "n_after": len(kept),
        "dropped_never_eligible": sorted(panel.tickers[~ever]),
    }
    return panel.select(kept), report


def infer_trading_grid(dates: pd.Series) -> pd.DatetimeIndex:
    """Unique sorted trading dates present in the data (no calendar assumptions)."""
    return pd.DatetimeIndex(pd.Series(pd.to_datetime(dates)).drop_duplicates().sort_values())
