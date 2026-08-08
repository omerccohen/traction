"""Live price feed: multi-source daily OHLCV updater with an append-only store.

Design constraints (from docs/BUILD_PLAN.md Phase 1):
* NETWORK-AWARE: every source is probed before use; when the environment's
  network policy blocks all sources, the updater exits cleanly with a clear
  status instead of failing — scheduled runs stay green and become productive
  the moment the policy allows a source.
* APPEND-ONLY + REVISION LOG: existing rows are never silently rewritten.
  Overlapping fetches that disagree with stored history beyond a tolerance are
  logged as conflicts and the STORED value wins (restatements must be explicit).
* SANITIZE ON LOAD, NOT ON WRITE: the store keeps raw prints; the
  corporate-action sanitizer runs at load time (same policy as the bundled
  dataset), so repairs are reproducible and never destructive.
* One code path for all ingestion: network sources and user-dropped CSVs go
  through the same validation.
"""
from __future__ import annotations

import gzip
import io
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

STORE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]
CONFLICT_TOL = 0.005          # >0.5% disagreement with stored history = conflict
MAX_ABS_DAILY_MOVE = 0.75     # reject prints implying >75% single-day moves as bad rows


# ---------------------------------------------------------------------------
# source adapters — each returns a long-form frame in STORE_COLUMNS, or raises
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "stocklab/0.3"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _stooq_symbol(ticker: str) -> str:
    return ticker.lower().replace(".", "-") + ".us"


def fetch_stooq(ticker: str, start: str | None = None) -> pd.DataFrame:
    url = f"https://stooq.com/q/d/l/?s={_stooq_symbol(ticker)}&i=d"
    raw = _http_get(url)
    df = pd.read_csv(io.BytesIO(raw))
    if "Close" not in df.columns or df.empty:
        raise ValueError(f"stooq: empty/invalid payload for {ticker}")
    df = df.rename(columns={c: c.lower() for c in df.columns})
    df["ticker"] = ticker
    df["date"] = pd.to_datetime(df["date"])
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    return df[STORE_COLUMNS]


def fetch_yahoo(ticker: str, start: str | None = None) -> pd.DataFrame:
    y_t = ticker.replace(".", "-")
    p1 = int(pd.Timestamp(start or "2000-01-01").timestamp())
    p2 = int(time.time()) + 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{y_t}"
           f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit")
    data = json.loads(_http_get(url))
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    df = pd.DataFrame({
        "date": pd.to_datetime(ts, unit="s").normalize(),
        "open": q["open"], "high": q["high"], "low": q["low"],
        "close": adj if adj is not None else q["close"],
        "volume": q["volume"],
    })
    df["ticker"] = ticker
    df = df.dropna(subset=["close"])
    return df[STORE_COLUMNS]


SOURCES = {"stooq": fetch_stooq, "yahoo": fetch_yahoo}
PROBE_URLS = {
    "stooq": "https://stooq.com/q/d/l/?s=aapl.us&i=d",
    "yahoo": "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d",
}


def probe_sources(timeout: int = 8) -> dict[str, bool]:
    """Which sources does the current network policy allow?"""
    out = {}
    for name, url in PROBE_URLS.items():
        try:
            _http_get(url, timeout=timeout)
            out[name] = True
        except Exception:
            out[name] = False
    return out


# ---------------------------------------------------------------------------
# validation + store
# ---------------------------------------------------------------------------

def validate_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Schema + sanity validation for ANY ingested rows (network or CSV drop)."""
    problems: list[str] = []
    missing = [c for c in STORE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"ingest missing columns: {missing}")
    df = df[STORE_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    n0 = len(df)
    df = df.dropna(subset=["date", "ticker", "close"])
    df = df[df["close"] > 0]
    if len(df) < n0:
        problems.append(f"dropped {n0 - len(df)} rows (missing/nonpositive close)")

    dupes = df.duplicated(["date", "ticker"]).sum()
    if dupes:
        problems.append(f"dropped {dupes} duplicate (date,ticker) rows")
        df = df.drop_duplicates(["date", "ticker"], keep="last")

    # implausible single prints: a large move into a day that immediately
    # reverses out of it is a bad row, not a real move. LOG returns make the
    # test symmetric (+300% and its -75% reversal have equal magnitude —
    # simple returns let V-spikes slip under a linear threshold).
    log_thresh = np.log(1.0 + MAX_ABS_DAILY_MOVE)
    bad_rows = 0
    for t, g in df.groupby("ticker", sort=False):
        g = g.sort_values("date")
        lr = np.log(g["close"]).diff()
        lr_next = np.log(g["close"]).shift(-1) - np.log(g["close"])
        spike = (lr.abs() > log_thresh) & (lr_next.abs() > log_thresh) & \
                (np.sign(lr) == -np.sign(lr_next))
        if spike.any():
            bad_rows += int(spike.sum())
            df = df.drop(g.index[spike])
    if bad_rows:
        problems.append(f"dropped {bad_rows} implausible spike rows")
    return df, problems


@dataclass
class UpdateReport:
    started_at: str
    sources_available: dict = field(default_factory=dict)
    source_used: str | None = None
    tickers_requested: int = 0
    tickers_updated: int = 0
    tickers_failed: list = field(default_factory=list)
    rows_appended: int = 0
    conflicts: int = 0
    problems: list = field(default_factory=list)
    status: str = "unknown"   # updated | no_network | nothing_new | error

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class PriceStore:
    """Append-only long-form store: data_cache/live/prices.csv.gz + update log."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "prices.csv.gz"
        self.log_path = self.root / "updates.log.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame(columns=STORE_COLUMNS)
        df = pd.read_csv(self.path, parse_dates=["date"])
        return df[STORE_COLUMNS]

    def last_dates(self) -> pd.Series:
        df = self.load()
        if df.empty:
            return pd.Series(dtype="datetime64[ns]")
        return df.groupby("ticker")["date"].max()

    def append(self, new: pd.DataFrame) -> tuple[int, int]:
        """Merge validated rows. Returns (rows_appended, conflicts).

        Existing (date,ticker) rows are immutable: incoming rows that disagree
        with stored close by > CONFLICT_TOL are counted and DISCARDED (the
        stored value wins); agreeing overlaps are discarded silently.
        """
        cur = self.load()
        if cur.empty:
            merged = new.sort_values(["ticker", "date"])
            merged.to_csv(self.path, index=False, compression="gzip")
            return len(new), 0

        key_cur = cur.set_index(["date", "ticker"])
        incoming = new.set_index(["date", "ticker"])
        overlap = incoming.index.intersection(key_cur.index)
        conflicts = 0
        if len(overlap) > 0:
            a = incoming.loc[overlap, "close"].astype(float)
            b = key_cur.loc[overlap, "close"].astype(float)
            rel = (a - b).abs() / b.clip(lower=1e-9)
            conflicts = int((rel > CONFLICT_TOL).sum())
        fresh = incoming.loc[incoming.index.difference(key_cur.index)].reset_index()
        if len(fresh) == 0:
            return 0, conflicts
        merged = pd.concat([cur, fresh[STORE_COLUMNS]]).sort_values(["ticker", "date"])
        merged.to_csv(self.path, index=False, compression="gzip")
        return len(fresh), conflicts

    def log(self, report: UpdateReport) -> None:
        with open(self.log_path, "a") as f:
            f.write(json.dumps(report.to_dict(), default=str) + "\n")

    def freshness(self) -> dict:
        ld = self.last_dates()
        if ld.empty:
            return {"has_data": False}
        newest = ld.max()
        return {
            "has_data": True,
            "newest_date": str(newest.date()),
            "n_tickers": int(len(ld)),
            "days_stale": int((pd.Timestamp.now(tz=timezone.utc).tz_localize(None)
                               - newest).days),
        }


def update_from_network(
    store: PriceStore,
    tickers: list[str],
    default_start: str = "2018-01-01",
    max_tickers_per_run: int = 600,
    pause_s: float = 0.4,
) -> UpdateReport:
    rep = UpdateReport(started_at=datetime.now(timezone.utc).isoformat(),
                       tickers_requested=len(tickers))
    rep.sources_available = probe_sources()
    usable = [s for s, ok in rep.sources_available.items() if ok]
    if not usable:
        rep.status = "no_network"
        store.log(rep)
        return rep

    src = usable[0]
    rep.source_used = src
    fetch = SOURCES[src]
    last = store.last_dates()

    frames = []
    for t in tickers[:max_tickers_per_run]:
        start = str(last.get(t, pd.Timestamp(default_start)).date()) if t in last.index \
            else default_start
        try:
            frames.append(fetch(t, start=start))
        except Exception as e:
            rep.tickers_failed.append(f"{t}: {type(e).__name__}")
        time.sleep(pause_s)

    if frames:
        new = pd.concat(frames, ignore_index=True)
        new, problems = validate_rows(new)
        rep.problems = problems
        appended, conflicts = store.append(new)
        rep.rows_appended = appended
        rep.conflicts = conflicts
        rep.tickers_updated = int(new["ticker"].nunique())
        rep.status = "updated" if appended else "nothing_new"
    else:
        rep.status = "error" if rep.tickers_failed else "nothing_new"
    store.log(rep)
    return rep


def update_from_csv(store: PriceStore, csv_path: str | Path) -> UpdateReport:
    """Path B/C ingestion: a user-dropped CSV through the SAME validation."""
    rep = UpdateReport(started_at=datetime.now(timezone.utc).isoformat())
    from .loaders import _normalize_columns
    df = pd.read_csv(csv_path)
    df, _note = _normalize_columns(df)
    if "open" not in df.columns:
        for c in ("open", "high", "low"):
            if c not in df.columns:
                df[c] = np.nan
    df, problems = validate_rows(df)
    rep.problems = problems
    appended, conflicts = store.append(df)
    rep.rows_appended, rep.conflicts = appended, conflicts
    rep.tickers_requested = rep.tickers_updated = int(df["ticker"].nunique())
    rep.status = "updated" if appended else "nothing_new"
    store.log(rep)
    return rep
