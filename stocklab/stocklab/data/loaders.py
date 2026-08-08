"""Data ingestion: bundled real dataset + generic CSV loader.

The bundled dataset is real S&P 500 daily OHLCV (Feb-2013 .. Feb-2018, ~505
tickers, public "all_stocks_5yr" dataset). Two documented biases — surfaced by
the skeptic module, never hidden:

* SURVIVORSHIP: tickers are index constituents as of early 2018. Companies that
  failed or were delisted before then are absent, which flatters long-side
  results and mutes short-side ones.
* SINGLE REGIME: one 5-year bull market with two corrections. Results say
  nothing about bear-market behavior.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .panel import Panel, long_to_panel

_PKG_ROOT = Path(__file__).resolve().parents[2]
BUNDLED_PATH = _PKG_ROOT / "data_cache" / "all_stocks_5yr.csv.gz"

BUNDLED_BIASES = [
    "SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; "
    "delisted/failed companies are missing. Long-side results are inflated.",
    "SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.",
    "PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT "
    "dividend-adjusted, so every ex-div date injects ~-(div/price) into the "
    "payer's label. Labels carry a small systematic anti-yield tilt; the long "
    "leg's P&L understates by roughly the universe's ~2%/yr dividend yield.",
]

COLUMN_ALIASES = {
    "name": "ticker", "symbol": "ticker", "tic": "ticker",
    "vol": "volume", "datetime": "date", "timestamp": "date",
}

# price-column priority: prefer adjusted when both are present (yfinance-style
# exports carry Close AND Adj Close; blind aliasing produced duplicate 'close'
# columns and crashed the pivot — review finding M5)
ADJUSTED_ALIASES = ("adj close", "adj_close", "adjclose", "adjusted close", "adj. close")


def _normalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})
    price_note = "close"
    adj = next((c for c in ADJUSTED_ALIASES if c in df.columns), None)
    if adj is not None:
        if "close" in df.columns:
            df = df.drop(columns=["close"])
        df = df.rename(columns={adj: "close"})
        price_note = f"{adj} (adjusted; raw close dropped)"
    df = df.rename(columns={c: COLUMN_ALIASES.get(c, c) for c in df.columns})
    dupes = df.columns[df.columns.duplicated()].unique().tolist()
    if dupes:
        raise ValueError(f"ambiguous columns after normalization: {dupes}")
    return df, price_note


def load_csv(path: str | Path, verbose: bool = False) -> Panel:
    """Load a long-form CSV with columns date,ticker,close,volume[,open,high,low].

    Common aliases (Name/symbol, vol...) are normalized. When both a raw and
    an adjusted close are present, the ADJUSTED one is used for prices and the
    raw one is dropped (stated explicitly with verbose=True).
    """
    df = pd.read_csv(path)
    df, price_note = _normalize_columns(df)
    if verbose:
        print(f"load_csv: price column = {price_note}")
    return long_to_panel(df)


def sanitize_corporate_actions(
    panel: Panel, threshold: float = 0.40, verbose: bool = False
) -> tuple[Panel, list[str]]:
    """Repair mechanically-identifiable corporate-action data errors.

    The bundled dataset contains a handful of un-adjusted events (spin-off
    share distributions printed as ~-50% price days; one mis-adjusted split
    that prints -49% then +101% on consecutive days). Left alone, these fake
    returns enter labels, features and the backtest (review finding M4).

    Rules (deliberately mechanical and logged, never silent):
    1. REVERSAL-PAIR: |ret(t)| > threshold and ret(t+1) reverses it so the
       two-day compounded move is small (<15%) -> a data error (bad split
       row). Both days are respliced so each carries the same fraction of the
       true two-day move.
    2. NEGATIVE STEP: ret(t) < -threshold with no reversal -> treated as an
       un-adjusted distribution (spin-off): all PRIOR closes are scaled by
       (1+ret) — exactly what a split/distribution adjustment does — so the
       event day becomes a 0% return. (The true total return of the event is
       unknowable from this data; 0 is far closer than -50%.)
    3. POSITIVE moves are left alone (large genuine rallies exist, e.g.
       VRTX +62% on trial results in Apr-2013).
    """
    close = panel.close.copy()
    notes: list[str] = []
    ret = close.pct_change()
    for tkr in close.columns:
        r = ret[tkr]
        hits = r.index[(r.abs() > threshold) & r.notna()]
        for d in hits:
            i = close.index.get_loc(d)
            r_d = (close[tkr].iloc[i] / close[tkr].iloc[i - 1]) - 1.0  # re-read (may be repaired)
            if not np.isfinite(r_d) or abs(r_d) <= threshold:
                continue
            r_next = (
                close[tkr].iloc[i + 1] / close[tkr].iloc[i] - 1.0
                if i + 1 < len(close) and np.isfinite(close[tkr].iloc[i + 1])
                else np.nan
            )
            two_day = (1 + r_d) * (1 + r_next) - 1.0 if np.isfinite(r_next) else np.nan
            if np.isfinite(two_day) and np.sign(r_next) == -np.sign(r_d) and abs(two_day) < 0.15:
                per_day = np.sqrt(1 + two_day) - 1.0
                close.loc[close.index[i], tkr] = close[tkr].iloc[i - 1] * (1 + per_day)
                notes.append(
                    f"{tkr} {d.date()}: reversal pair ({r_d:+.1%} then {r_next:+.1%}) "
                    f"respliced to {per_day:+.2%}/day"
                )
            elif r_d < -threshold:
                factor = 1 + r_d
                close.iloc[:i, close.columns.get_loc(tkr)] *= factor
                notes.append(
                    f"{tkr} {d.date()}: {r_d:+.1%} step treated as un-adjusted "
                    f"distribution; prior history scaled by {factor:.3f}"
                )
    if verbose:
        for n in notes:
            print("sanitize:", n)
    return (
        Panel(close=close, volume=panel.volume, open=panel.open,
              high=panel.high, low=panel.low),
        notes,
    )


def load_bundled(
    path: str | Path | None = None, sanitize: bool = True
) -> tuple[Panel, list[str]]:
    """Load the bundled real S&P 500 dataset. Returns (panel, known_biases)."""
    p = Path(path) if path is not None else BUNDLED_PATH
    if not p.exists():
        # fall back to uncompressed variant if present
        alt = p.with_suffix("") if p.suffix == ".gz" else None
        if alt is not None and alt.exists():
            p = alt
        else:
            raise FileNotFoundError(
                f"Bundled dataset not found at {p}. "
                "Fetch it with scripts/fetch_data.py or pass your own CSV to load_csv()."
            )
    panel = load_csv(p)
    biases = list(BUNDLED_BIASES)
    if sanitize:
        panel, notes = sanitize_corporate_actions(panel)
        if notes:
            biases.append(
                f"DATA REPAIRS: {len(notes)} corporate-action rows mechanically "
                "repaired at load (see loaders.sanitize_corporate_actions): "
                + "; ".join(notes)
            )
    return panel, biases
