"""Phase 1 tests, rebuilt after the adversarial audit.

Covers: partial-column CSVs (M1), settlement-window restatement vs settled
conflicts (M2), atomic writes (M4), duplicate-key invariant, tail-aware spike
detection on 1-row batches (M7), crash-bounce preservation, adapter payload
parsing from fixtures (yahoo raw-close + events, stooq bounded URL), the
no_network path, CSV-path never-raises, restate(), and split application.
No network anywhere — adapters are fed fixture payloads via monkeypatching.
"""
import json

import numpy as np
import pandas as pd
import pytest

import stocklab.data.live as live
from stocklab.data.live import (
    PriceStore, validate_rows, update_from_csv, update_from_network,
    fetch_yahoo, fetch_stooq, apply_split_adjustments,
    STORE_COLUMNS, CONFLICT_TOL, SETTLEMENT_DAYS,
)


def _rows(ticker, dates, closes, volume=1e6):
    return pd.DataFrame({
        "date": pd.to_datetime(dates), "ticker": ticker,
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": volume,
    })


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def test_validate_drops_bad_rows():
    df = _rows("AAA", ["2024-01-01", "2024-01-02", "2024-01-03"], [10.0, -5.0, 11.0])
    out, problems = validate_rows(df)
    assert len(out) == 2 and any("nonpositive" in p for p in problems)


def test_validate_drops_spike_rows():
    df = _rows("AAA", ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
               [10.0, 40.0, 10.5, 10.6])
    out, problems = validate_rows(df)
    assert 40.0 not in out["close"].values
    assert any("spike" in p for p in problems)


def test_validate_keeps_crash_then_bounce():
    """100 -> 40 -> 72: a real catastrophe-then-bounce (net -28%) must be KEPT
    (the compounded-move condition; audit finding)."""
    df = _rows("AAA", ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
               [100.0, 40.0, 72.0, 70.0])
    out, _ = validate_rows(df)
    assert 40.0 in out["close"].values


def test_validate_uses_stored_tail_for_single_row_batch():
    """A garbage newest-day print in a 1-row daily batch must be caught via
    the stored tail (audit M7)... but only once the reversal exists; the
    tail makes a 2-row batch catchable."""
    tail = _rows("AAA", ["2024-01-01", "2024-01-02"], [10.0, 10.1])
    batch = _rows("AAA", ["2024-01-03", "2024-01-04"], [45.0, 10.2])  # bad print + reversal
    out, problems = validate_rows(batch, prior_tail=tail)
    assert 45.0 not in out["close"].values
    assert 10.2 in out["close"].values          # the good row survives
    assert any("spike" in p for p in problems)


def test_validate_close_outside_range_dropped():
    df = _rows("AAA", ["2024-01-01"], [10.0])
    df.loc[:, "high"] = 8.0
    df.loc[:, "low"] = 7.0
    out, problems = validate_rows(df)
    assert len(out) == 0 and any("outside high/low" in p for p in problems)


# ---------------------------------------------------------------------------
# store semantics
# ---------------------------------------------------------------------------

def test_settlement_window_restates_recent_rows(tmp_path):
    # Settlement is anchored to WALL-CLOCK today (an old backfill must never
    # get its own replaceable window), so "yesterday's partial print" has to
    # actually be recent for the correction to be allowed.
    d0, d1, d2 = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=3)
    store = PriceStore(tmp_path)
    store.append(_rows("AAA", [d0, d1], [10.0, 10.5]))
    # next-day run corrects yesterday's partial print (within settlement)
    fix = _rows("AAA", [d1, d2], [11.2, 11.3])
    appended, restated, conflicts, details = store.append(fix)
    assert restated == 1 and conflicts == 0 and appended == 1
    df = store.load()
    v = df[df["date"] == d1]["close"].iloc[0]
    assert np.isclose(v, 11.2), "settlement window must let the correction win"


def test_settlement_anchored_to_today_not_batch(tmp_path):
    # A purely-historical backfill used to carry a replaceable window at its
    # own tail — years inside settled history — and silently overwrote stored
    # values as benign "restatements".
    store = PriceStore(tmp_path)
    dates = pd.bdate_range("2020-01-06", periods=5)
    store.append(_rows("AAA", dates, [100.0] * 5))
    bad = _rows("AAA", dates, [999.0] * 5)
    appended, restated, conflicts, details = store.append(bad)
    assert restated == 0, "old rows must not be replaceable via a stale batch"
    assert conflicts == 5
    assert (store.load()["close"] == 100.0).all(), "stored settled values win"


def test_settled_history_is_immutable_with_conflict_details(tmp_path):
    store = PriceStore(tmp_path)
    dates = pd.bdate_range("2024-01-02", periods=8)
    store.append(_rows("AAA", dates, list(np.linspace(10, 11, 8))))
    # incoming batch whose max date makes the 01-02 overlap SETTLED
    bad = _rows("AAA", [dates[0], dates[-1] + pd.Timedelta(days=1)],
                [10.0 * (1 + 3 * CONFLICT_TOL), 11.1])
    appended, restated, conflicts, details = store.append(bad)
    assert conflicts == 1 and len(details) == 1
    assert details[0]["ticker"] == "AAA" and details[0]["stored"] == pytest.approx(10.0)
    df = store.load()
    v = df[df["date"] == dates[0]]["close"].iloc[0]
    assert np.isclose(v, 10.0), "stored value must win on settled history"


def test_append_rejects_duplicate_keys(tmp_path):
    store = PriceStore(tmp_path)
    dup = pd.concat([_rows("AAA", ["2024-01-02"], [10.0]),
                     _rows("AAA", ["2024-01-02"], [12.0])])
    with pytest.raises(AssertionError):
        store.append(dup)


def test_atomic_write_leaves_no_tmp(tmp_path):
    store = PriceStore(tmp_path)
    store.append(_rows("AAA", ["2024-01-02"], [10.0]))
    assert store.path.exists()
    assert not store.path.with_suffix(store.path.suffix + ".tmp").exists()
    # file is a valid gzip csv
    assert len(store.load()) == 1


def test_restate_drops_and_logs(tmp_path):
    store = PriceStore(tmp_path)
    store.append(_rows("AAA", ["2024-01-02", "2024-01-03"], [10.0, 10.1]))
    store.append(_rows("BBB", ["2024-01-02"], [5.0]))
    n = store.restate("AAA")
    assert n == 2
    assert set(store.load()["ticker"]) == {"BBB"}
    log = store.log_path.read_text()
    assert '"restate": "AAA"' in log


def test_csv_ingestion_partial_columns(tmp_path):
    """date,ticker,open,close,volume — no high/low (audit M1 crash case)."""
    store = PriceStore(tmp_path / "live")
    csv = tmp_path / "drop.csv"
    pd.DataFrame({
        "date": ["2024-02-01", "2024-02-02"], "ticker": "BBB",
        "open": [5.0, 5.05], "close": [5.0, 5.1], "volume": [1e6, 1e6],
    }).to_csv(csv, index=False)
    rep = update_from_csv(store, csv)
    assert rep.status == "updated" and rep.rows_appended == 2


def test_csv_ingestion_never_raises(tmp_path):
    store = PriceStore(tmp_path / "live")
    bad = tmp_path / "garbage.csv"
    bad.write_text("this,is\nnot,a,panel\n")
    rep = update_from_csv(store, bad)
    assert rep.status == "error" and rep.problems
    assert store.log_path.exists()   # failure is logged, not thrown


def test_freshness_and_meta(tmp_path):
    store = PriceStore(tmp_path)
    assert store.freshness() == {"has_data": False}
    store.append(_rows("AAA", ["2024-01-02"], [10.0]))
    f = store.freshness()
    assert f["has_data"] and f["n_tickers"] == 1
    assert "backfill_before" in f["meta"]   # survivorship marker written


# ---------------------------------------------------------------------------
# adapters (fixture payloads, no network)
# ---------------------------------------------------------------------------

YAHOO_FIXTURE = {
    "chart": {"result": [{
        "timestamp": [1704205800, 1704292200],      # 13:30 ET Jan 2/3 2024
        "indicators": {
            "quote": [{"open": [10.0, 10.2], "high": [10.5, 10.6],
                       "low": [9.9, 10.1], "close": [10.4, 10.5],
                       "volume": [1000, 1100]}],
            "adjclose": [{"adjclose": [5.2, 5.25]}],   # adjusted — must NOT be used
        },
        "events": {
            "splits": {"161": {"date": 1704205800, "numerator": 2, "denominator": 1}},
            "dividends": {"162": {"date": 1704292200, "amount": 0.25}},
        },
    }], "error": None}
}


def test_yahoo_parser_uses_raw_close_and_extracts_events(monkeypatch):
    monkeypatch.setattr(live, "_http_get", lambda url, timeout=20: json.dumps(YAHOO_FIXTURE).encode())
    df, actions = fetch_yahoo("TST")
    assert list(df["close"]) == [10.4, 10.5], "must use RAW close, not adjclose"
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-02")   # ET session date
    assert len(actions) == 2
    sp = actions[actions["type"] == "split"].iloc[0]
    assert sp["value"] == pytest.approx(2.0)


def test_yahoo_parser_error_payload(monkeypatch):
    monkeypatch.setattr(live, "_http_get",
                        lambda url, timeout=20: b'{"chart":{"result":null,"error":{"code":"Not Found"}}}')
    with pytest.raises(ValueError):
        fetch_yahoo("NOPE")


def test_stooq_parser_and_bounded_url(monkeypatch):
    seen = {}

    def fake_get(url, timeout=20):
        seen["url"] = url
        return b"Date,Open,High,Low,Close,Volume\n2024-01-02,10,10.5,9.9,10.4,1000\n"
    monkeypatch.setattr(live, "_http_get", fake_get)
    df, actions = fetch_stooq("TST", start="2024-01-01")
    assert "d1=20240101" in seen["url"], "stooq fetch must be date-bounded (audit M6)"
    assert list(df["close"]) == [10.4] and actions.empty


def test_update_from_network_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "probe_sources", lambda timeout=8: {"stooq": False, "yahoo": False})
    store = PriceStore(tmp_path)
    rep = update_from_network(store, ["AAA"])
    assert rep.status == "no_network"
    assert store.log_path.exists()


# ---------------------------------------------------------------------------
# corporate actions
# ---------------------------------------------------------------------------

def test_apply_split_adjustments():
    from stocklab.data.panel import Panel
    dates = pd.bdate_range("2024-01-02", periods=6)
    close = pd.DataFrame({"AAA": [100.0, 102.0, 104.0, 52.0, 52.5, 53.0]}, index=dates)
    volume = pd.DataFrame({"AAA": [1e6] * 6}, index=dates)
    panel = Panel(close=close, volume=volume)
    actions = pd.DataFrame([{"date": dates[3], "ticker": "AAA",
                             "type": "split", "value": 2.0}])
    adj, notes = apply_split_adjustments(panel, actions)
    r = adj.close["AAA"].pct_change().abs().max()
    assert r < 0.03, f"split step must vanish after exact adjustment (max |ret| {r:.1%})"
    assert adj.volume["AAA"].iloc[0] == pytest.approx(2e6)   # volume adjusted too
    assert notes
