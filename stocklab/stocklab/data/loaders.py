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

import pandas as pd

from .panel import Panel, long_to_panel

_PKG_ROOT = Path(__file__).resolve().parents[2]
BUNDLED_PATH = _PKG_ROOT / "data_cache" / "all_stocks_5yr.csv.gz"

BUNDLED_BIASES = [
    "SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; "
    "delisted/failed companies are missing. Long-side results are inflated.",
    "SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.",
]

COLUMN_ALIASES = {
    "name": "ticker", "symbol": "ticker", "tic": "ticker",
    "adj close": "close", "adj_close": "close", "adjclose": "close",
    "vol": "volume", "datetime": "date", "timestamp": "date",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})
    return df.rename(columns={c: COLUMN_ALIASES.get(c, c) for c in df.columns})


def load_csv(path: str | Path) -> Panel:
    """Load a long-form CSV with columns date,ticker,close,volume[,open,high,low].

    Common aliases (Name/symbol, adj close, vol...) are normalized.
    """
    df = pd.read_csv(path)
    df = _normalize_columns(df)
    return long_to_panel(df)


def load_bundled(path: str | Path | None = None) -> tuple[Panel, list[str]]:
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
    return load_csv(p), list(BUNDLED_BIASES)
