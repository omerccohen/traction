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
    panel: Panel, threshold: float = 0.40, verbose: bool = False,
    dv_calm_ratio: float = 1.5,
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
    2. NEGATIVE STEP: ret(t) < -threshold with no reversal -> *candidate*
       un-adjusted distribution. Rule 2 now requires POSITIVE EVIDENCE before
       it rewrites anything (see below).
    3. POSITIVE moves are left alone (large genuine rallies exist, e.g.
       VRTX +62% on trial results in Apr-2013).

    **Rule 2's evidence test (2026-08-13 audit).** The original rule assumed any
    one-day fall worse than -40% was a data error. That held for the bundled
    500-name set it was written for, where every event had been hand-checked.
    On the 2,992-ticker live store it is false: genuine -40% days are routine.
    Measured across the store, the rule fired 231 times and **210 of those days
    traded at 3x or more of their trailing 60-day median dollar volume** — they
    were panics, not split rows. Only 11 looked like real splits. WAL on
    2023-03-13 (the SVB bank run) fell 47.1% on 28x volume with a $7.46 low
    against a $30.78 high; the rule recorded it as exactly 0.00% and divided
    every WAL close from 2018 to that date by 0.5294 — using a future event to
    rewrite past prices, so the same day read 62.36 from 2023-03-10 and 33.01
    from today.

    The discriminator is dollar volume. A split renumbers shares and leaves
    dollars traded unchanged; a crash multiplies them. Rescaling history is the
    destructive, irreversible action, so it now happens ONLY on evidence that
    the day was NOT a panic (dollar volume at or below `dv_calm_ratio` x its
    trailing median). Absent volume data the day is LEFT ALONE — the safe
    default is to preserve the print, not to rewrite five years behind it.
    Every decision is logged in both directions.
    """
    close = panel.close.copy()
    notes: list[str] = []
    # explicit ffill = the old pad default, kept deliberately: the crash/split
    # judge must compare each print to the LAST REAL price so a move across a
    # halt gap is still seen (fill_method=None would blind it); pandas 3 drops
    # the implicit pad, so spell it out
    ret = close.ffill().pct_change(fill_method=None)
    # trailing dollar-volume baseline for the evidence test above
    dv = (panel.close * panel.volume) if panel.volume is not None else None
    dv_med = (dv.shift(1).rolling(60, min_periods=20).median()
              if dv is not None else None)
    kept = 0
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
                # evidence test: was this a quiet renumbering, or a panic?
                ratio = np.nan
                if dv is not None and tkr in dv.columns:
                    base = dv_med[tkr].iloc[i]
                    if np.isfinite(base) and base > 0:
                        ratio = float(dv[tkr].iloc[i]) / base
                if not np.isfinite(ratio) or ratio > dv_calm_ratio:
                    kept += 1
                    notes.append(
                        f"{tkr} {d.date()}: {r_d:+.1%} LEFT ALONE — "
                        + (f"dollar volume {ratio:.1f}x its 60d median, "
                           "consistent with a real move, not a split row"
                           if np.isfinite(ratio) else
                           "no volume baseline to justify rewriting history")
                    )
                    continue
                factor = 1 + r_d
                close.iloc[:i, close.columns.get_loc(tkr)] *= factor
                notes.append(
                    f"{tkr} {d.date()}: {r_d:+.1%} step treated as un-adjusted "
                    f"distribution (dollar volume only {ratio:.1f}x its 60d "
                    f"median); prior history scaled by {factor:.3f}"
                )
    if kept:
        notes.append(f"SUMMARY: {kept} large declines preserved as real market "
                     f"moves; {len([n for n in notes if 'prior history scaled' in n])} "
                     "treated as un-adjusted distributions.")
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
