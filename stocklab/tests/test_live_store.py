"""Phase 1 tests: ingestion validation, append-only store semantics, conflicts.

No network in tests — adapters are exercised via fixture payload parsing only.
"""
import io
import json

import numpy as np
import pandas as pd
import pytest

from stocklab.data.live import (
    PriceStore, validate_rows, update_from_csv, STORE_COLUMNS, CONFLICT_TOL,
)


def _rows(ticker, dates, closes):
    return pd.DataFrame({
        "date": pd.to_datetime(dates), "ticker": ticker,
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": 1e6,
    })


def test_validate_drops_bad_rows():
    df = _rows("AAA", ["2024-01-01", "2024-01-02", "2024-01-03"], [10.0, -5.0, 11.0])
    out, problems = validate_rows(df)
    assert len(out) == 2 and any("nonpositive" in p for p in problems)


def test_validate_drops_spike_rows():
    # 10 -> 40 -> 10.5: an implausible V-spike row (bad print), must be dropped
    df = _rows("AAA", ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
               [10.0, 40.0, 10.5, 10.6])
    out, problems = validate_rows(df)
    assert 40.0 not in out["close"].values
    assert any("spike" in p for p in problems)


def test_validate_keeps_genuine_jump():
    # a real level shift (gap up and STAYS up) must be kept
    df = _rows("AAA", ["2024-01-01", "2024-01-02", "2024-01-03"], [10.0, 18.0, 18.2])
    out, _ = validate_rows(df)
    assert 18.0 in out["close"].values


def test_store_append_only_and_conflicts(tmp_path):
    store = PriceStore(tmp_path)
    a = _rows("AAA", ["2024-01-01", "2024-01-02"], [10.0, 10.5])
    n, c = store.append(a)
    assert (n, c) == (2, 0)

    # overlapping fetch: one agreeing row, one conflicting row, one new row
    b = _rows("AAA", ["2024-01-02", "2024-01-03"], [10.5 * (1 + 2 * CONFLICT_TOL), 11.0])
    n, c = store.append(b)
    assert n == 1 and c == 1
    # stored value must win on the conflicting date
    df = store.load()
    v = df[(df["ticker"] == "AAA") & (df["date"] == pd.Timestamp("2024-01-02"))]["close"].iloc[0]
    assert np.isclose(v, 10.5)


def test_csv_ingestion_path(tmp_path):
    store = PriceStore(tmp_path / "live")
    csv = tmp_path / "drop.csv"
    _rows("BBB", ["2024-02-01", "2024-02-02"], [5.0, 5.1]).to_csv(csv, index=False)
    rep = update_from_csv(store, csv)
    assert rep.status == "updated" and rep.rows_appended == 2
    # idempotent re-ingest
    rep2 = update_from_csv(store, csv)
    assert rep2.status == "nothing_new" and rep2.rows_appended == 0
    # log has two lines
    assert len((tmp_path / "live" / "updates.log.jsonl").read_text().strip().splitlines()) == 2


def test_freshness(tmp_path):
    store = PriceStore(tmp_path)
    assert store.freshness() == {"has_data": False}
    store.append(_rows("AAA", ["2024-01-02"], [10.0]))
    f = store.freshness()
    assert f["has_data"] and f["n_tickers"] == 1 and f["newest_date"] == "2024-01-02"
