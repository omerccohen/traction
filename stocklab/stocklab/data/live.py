"""Live price feed: multi-source daily OHLCV updater with an append-only store.

Design (rebuilt after the Phase-1 adversarial audit — docs/SKEPTIC_LOG.md):
* NETWORK-AWARE: sources probed before use; when the environment blocks all of
  them the updater exits cleanly with status "no_network".
* CANONICAL REGIME = RAW PRINTS: every source contributes UNadjusted prices
  (yahoo's raw close, not adjclose — mixing adjusted closes with raw OHLV was
  incoherent). Corporate actions (splits/dividends) are captured into their own
  table and applied EXACTLY at load time; the heuristic sanitizer remains only
  as a fallback for events with no recorded factor.
* SETTLEMENT WINDOW: rows younger than `SETTLEMENT_DAYS` are replaceable
  (intraday partial prints get corrected by the next run — logged as
  restatements). Immutability starts after settlement; conflicts against
  settled history are logged IN DETAIL and the stored value wins. Explicit
  per-ticker `restate()` exists for deliberate history rewrites.
* DURABILITY: atomic tmp+rename writes; an inter-process lock around
  read-modify-write; the store can never be half-written or clobbered by a
  concurrent run.
* One validation path for network and CSV-drop ingestion, run against the
  STORED TAIL so single-new-row batches still get spike protection.
"""
from __future__ import annotations

import fcntl
import io
import json
import os
import subprocess
import time
import urllib.request
import urllib.error
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

STORE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]
ACTION_COLUMNS = ["date", "ticker", "type", "value"]   # type: split|dividend
CONFLICT_TOL = 0.005
MAX_ABS_DAILY_MOVE = 0.75
SETTLEMENT_DAYS = 3          # rows younger than this are replaceable
ABORT_AFTER_CONSECUTIVE_FAILURES = 10
MAX_CONFLICT_DETAILS = 20


# ---------------------------------------------------------------------------
# source adapters — RAW prints only; splits/dividends returned separately
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 20, retries_on_429: int = 3) -> bytes:
    """GET with browser UA (yahoo 429s bot UAs — verified live) and
    exponential backoff on 429 (verified: yahoo throttles bursts per IP)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
    delay = 20.0
    for attempt in range(retries_on_429 + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries_on_429:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")


def _stooq_symbol(ticker: str) -> str:
    return ticker.lower().replace(".", "-") + ".us"


def fetch_stooq(ticker: str, start: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    d1 = pd.Timestamp(start or "2018-01-01").strftime("%Y%m%d")
    d2 = datetime.now(timezone.utc).strftime("%Y%m%d")
    url = (f"https://stooq.com/q/d/l/?s={_stooq_symbol(ticker)}&i=d"
           f"&d1={d1}&d2={d2}")          # bounded fetch (full-history was M6)
    raw = _http_get(url)
    df = pd.read_csv(io.BytesIO(raw))
    if "Close" not in df.columns or df.empty:
        raise ValueError(f"stooq: empty/invalid payload for {ticker}")
    df = df.rename(columns={c: c.lower() for c in df.columns})
    if "volume" not in df.columns:
        df["volume"] = np.nan
    df["ticker"] = ticker
    df["date"] = pd.to_datetime(df["date"])
    actions = pd.DataFrame(columns=ACTION_COLUMNS)   # stooq daily CSV carries none
    return df[STORE_COLUMNS], actions


def fetch_yahoo(ticker: str, start: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    y_t = ticker.replace(".", "-")
    p1 = int(pd.Timestamp(start or "2018-01-01").timestamp())
    p2 = int(time.time()) + 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{y_t}"
           f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit")
    data = json.loads(_http_get(url))
    res = (data.get("chart", {}).get("result") or [None])[0]
    if res is None:
        raise ValueError(f"yahoo: no result for {ticker}: "
                         f"{str(data.get('chart', {}).get('error'))[:120]}")
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    # yahoo timestamps are session-anchored; convert via the exchange tz (US
    # assumption documented — non-US listings would need per-exchange tz)
    dates = (pd.to_datetime(ts, unit="s", utc=True)
             .tz_convert("America/New_York").tz_localize(None).normalize())
    df = pd.DataFrame({
        "date": dates,
        "open": q["open"], "high": q["high"], "low": q["low"],
        "close": q["close"],            # RAW close — canonical regime (M3)
        "volume": q["volume"],
    })
    df["ticker"] = ticker
    df = df.dropna(subset=["close"])

    acts = []
    ev = res.get("events", {}) or {}
    for _, s in (ev.get("splits") or {}).items():
        num, den = float(s.get("numerator", 1)), float(s.get("denominator", 1))
        if den > 0 and num > 0:
            acts.append({"date": pd.to_datetime(s["date"], unit="s", utc=True)
                         .tz_convert("America/New_York").tz_localize(None).normalize(),
                         "ticker": ticker, "type": "split", "value": num / den})
    for _, d in (ev.get("dividends") or {}).items():
        acts.append({"date": pd.to_datetime(d["date"], unit="s", utc=True)
                     .tz_convert("America/New_York").tz_localize(None).normalize(),
                     "ticker": ticker, "type": "dividend", "value": float(d["amount"])})
    actions = pd.DataFrame(acts, columns=ACTION_COLUMNS)
    return df[STORE_COLUMNS], actions


def _http_get_curl(url: str, timeout: int = 15) -> bytes:
    """curl transport — this environment's egress proxy is configured for curl
    (CURL_CA_BUNDLE set); urllib times out through it. HTTP/1.1 forced (proxy
    returns 'HTTP/2 stream not closed cleanly' otherwise). Verified 2026-08-09."""
    r = subprocess.run(
        ["curl", "-sS", "--fail", "--http1.1", "-m", str(timeout),
         "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36", url],
        capture_output=True, timeout=timeout + 8,
    )
    if r.returncode != 0:
        raise RuntimeError(f"curl failed ({r.returncode}) for {url}")
    return r.stdout


def fetch_stockanalysis(ticker: str, start: str | None = None
                        ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """stockanalysis.com keyless daily OHLCV. Reachable and CURRENT where the
    vendors are blocked/challenged (yahoo 429s the shared egress IP; stooq
    serves a bot-challenge). Verified 2026-08-09: 503-ticker coverage incl.
    dotted symbols, data through T-2, 5y history via range=5Y.

    Canonical raw prints: uses 'c' (raw close) + o/h/l/v; the JSON also carries
    'a' (adjusted close) which we ignore to keep the store split-continuity to
    the load-time corporate-action machinery, consistent with the other
    adapters. Data is returned newest-first; we sort ascending."""
    # pick the smallest range that covers `start` (fewer bytes for daily jobs)
    span_days = (datetime.now(timezone.utc) - pd.Timestamp(start or "2018-01-01")
                 .tz_localize("UTC")).days if start else 3650
    rng = "1M" if span_days <= 25 else ("1Y" if span_days <= 366
          else ("5Y" if span_days <= 1830 else "10Y"))
    sym = ticker.replace(".", "-")   # stockanalysis uses BRK-B style
    url = (f"https://stockanalysis.com/api/symbol/s/{sym}/history"
           f"?range={rng}&period=Daily")
    data = json.loads(_http_get_curl(url))
    rows = data.get("data")
    if not rows:
        raise ValueError(f"stockanalysis: empty payload for {ticker} "
                         f"({str(data)[:80]})")
    df = pd.DataFrame(rows)
    df = df.rename(columns={"t": "date", "o": "open", "h": "high",
                            "l": "low", "c": "close", "v": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = ticker
    for c in ("open", "high", "low", "close", "volume"):
        if c not in df.columns:
            df[c] = np.nan
    df = df.sort_values("date")
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    actions = pd.DataFrame(columns=ACTION_COLUMNS)   # not provided by this source
    return df[STORE_COLUMNS], actions


SOURCES = {"stockanalysis": fetch_stockanalysis, "stooq": fetch_stooq, "yahoo": fetch_yahoo}
PROBE_URLS = {
    "stockanalysis": "https://stockanalysis.com/api/symbol/s/AAPL/history?range=1M&period=Daily",
    "stooq": "https://stooq.com/q/d/l/?s=aapl.us&i=d&d1=20240101&d2=20240110",
    "yahoo": "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d",
}


def probe_sources(timeout: int = 8) -> dict[str, bool]:
    """Content-validating probes: stooq answers its bot-challenge page with
    HTTP 200, so a status-only probe selected a source whose every fetch
    then failed (verified live 2026-08-09). A source is usable only if the
    payload parses as what the adapter expects."""
    out = {}
    for name, url in PROBE_URLS.items():
        try:
            getter = _http_get_curl if name == "stockanalysis" else _http_get
            body = getter(url, timeout=timeout)
            if name == "stooq":
                out[name] = body[:5] == b"Date," or b"Date,Open" in body[:200]
            elif name == "yahoo":
                out[name] = b'"chart"' in body[:200]
            elif name == "stockanalysis":
                out[name] = b'"data"' in body[:200] and b'"t"' in body[:400]
            else:
                out[name] = True
        except Exception:
            out[name] = False
    return out


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def validate_rows(df: pd.DataFrame, prior_tail: pd.DataFrame | None = None
                  ) -> tuple[pd.DataFrame, list[str]]:
    """Schema + sanity validation for ANY ingested rows.

    `prior_tail` (recent stored rows per ticker) is prepended for the spike
    check so a one-row daily batch still has context (audit M7) — tail rows
    themselves are never dropped here.
    """
    problems: list[str] = []
    missing = [c for c in STORE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"ingest missing columns: {missing}")
    df = df[STORE_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    n0 = len(df)
    df = df.dropna(subset=["date", "ticker", "close"])
    df = df[df["close"] > 0]
    df = df[~(df["volume"] < 0)]
    if len(df) < n0:
        problems.append(f"dropped {n0 - len(df)} rows (missing/nonpositive close or negative volume)")
    # audit F5: a single future-dated row permanently defeats the briefing's
    # freshness guard (append-only store) — reject at the door
    tomorrow = pd.Timestamp(datetime.now(timezone.utc).date()) + pd.Timedelta(days=1)
    future = df["date"] > tomorrow
    if future.any():
        problems.append(f"dropped {int(future.sum())} future-dated rows")
        df = df[~future]

    # internal consistency where OHL present (cheap; would have caught the
    # adjusted-close-with-raw-high/low adapter bug on day one)
    with np.errstate(invalid="ignore"):
        bad_range = (df["high"].notna() & df["low"].notna()
                     & ((df["close"] > df["high"] * 1.02) | (df["close"] < df["low"] * 0.98)))
    if bad_range.any():
        problems.append(f"dropped {int(bad_range.sum())} rows (close outside high/low)")
        df = df[~bad_range]

    dupes = df.duplicated(["date", "ticker"]).sum()
    if dupes:
        problems.append(f"dropped {dupes} duplicate (date,ticker) rows")
        df = df.drop_duplicates(["date", "ticker"], keep="last")

    # V-spike detection on log returns, WITH stored context, and requiring the
    # two-day compounded move to roughly cancel (a real crash-then-bounce that
    # nets -28% must be kept — audit finding)
    log_thresh = np.log(1.0 + MAX_ABS_DAILY_MOVE)
    incoming_idx = df.index
    ctx = df if prior_tail is None or prior_tail.empty else pd.concat(
        [prior_tail[STORE_COLUMNS], df], ignore_index=False)
    drop: list = []
    for t, g in ctx.groupby("ticker", sort=False):
        g = g.sort_values("date")
        lc = np.log(g["close"].to_numpy(dtype=float))
        lr = np.diff(lc, prepend=np.nan)
        lr_next = np.append(np.diff(lc), np.nan)
        two_day = np.abs(lr + lr_next)
        spike = ((np.abs(lr) > log_thresh) & (np.abs(lr_next) > log_thresh)
                 & (np.sign(lr) == -np.sign(lr_next)) & (two_day < np.log(1.15)))
        for pos in np.where(spike)[0]:
            idx = g.index[pos]
            if idx in incoming_idx:          # never drop stored context rows
                drop.append(idx)
    if drop:
        problems.append(f"dropped {len(drop)} implausible spike rows")
        df = df.drop(index=drop)
    return df, problems


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

@dataclass
class UpdateReport:
    started_at: str
    sources_available: dict = field(default_factory=dict)
    source_used: str | None = None
    tickers_requested: int = 0
    tickers_updated: int = 0
    tickers_failed: list = field(default_factory=list)
    tickers_skipped: int = 0
    rows_appended: int = 0
    rows_restated: int = 0            # settlement-window replacements
    conflicts: int = 0                # settled-history disagreements (stored wins)
    conflict_details: list = field(default_factory=list)
    actions_recorded: int = 0
    aborted_after_failures: bool = False
    problems: list = field(default_factory=list)
    status: str = "unknown"   # updated | partial | no_network | nothing_new | error

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class PriceStore:
    """Long-form store with settlement-window semantics, atomic writes and an
    inter-process lock. Files: prices.csv.gz, corporate_actions.csv,
    updates.log.jsonl, meta.json."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "prices.csv.gz"
        self.actions_path = self.root / "corporate_actions.csv"
        self.log_path = self.root / "updates.log.jsonl"
        self.meta_path = self.root / "meta.json"
        self.lock_path = self.root / ".lock"
        self.root.mkdir(parents=True, exist_ok=True)

    # -- concurrency + atomicity -------------------------------------------
    @contextmanager
    def _locked(self):
        with open(self.lock_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def _atomic_write(df: pd.DataFrame, path: Path, **to_csv_kw) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_csv(tmp, index=False, **to_csv_kw)
        os.replace(tmp, path)

    # -- IO -----------------------------------------------------------------
    def load(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame(columns=STORE_COLUMNS)
        df = pd.read_csv(self.path, parse_dates=["date"],
                         converters={"ticker": str})   # ticker "NA" stays "NA"
        return df[STORE_COLUMNS]

    def load_actions(self) -> pd.DataFrame:
        if not self.actions_path.exists():
            return pd.DataFrame(columns=ACTION_COLUMNS)
        return pd.read_csv(self.actions_path, parse_dates=["date"],
                           converters={"ticker": str})

    def last_dates(self) -> pd.Series:
        df = self.load()
        if df.empty:
            return pd.Series(dtype="datetime64[ns]")
        return df.groupby("ticker")["date"].max()

    def meta(self) -> dict:
        return json.loads(self.meta_path.read_text()) if self.meta_path.exists() else {}

    def _write_meta_once(self) -> None:
        if not self.meta_path.exists():
            self.meta_path.write_text(json.dumps({
                "backfill_before": datetime.now(timezone.utc).date().isoformat(),
                "note": "rows dated before first live update inherit current-"
                        "constituent survivorship bias (audit note)",
            }, indent=2))

    # -- mutation ------------------------------------------------------------
    def append(self, new: pd.DataFrame) -> tuple[int, int, int, list]:
        """Merge validated rows under the settlement policy.

        Returns (appended, restated, conflicts, conflict_details).
        * dates within SETTLEMENT_DAYS of the newest incoming date are
          REPLACEABLE: incoming wins, counted as restatements;
        * older overlaps are immutable: stored wins; disagreements beyond
          CONFLICT_TOL are logged with detail.
        """
        if new.empty:
            return 0, 0, 0, []
        assert not new.duplicated(["date", "ticker"]).any(), \
            "append() requires unique (date,ticker) — run validate_rows first"
        with self._locked():
            cur = self.load()
            self._write_meta_once()
            if cur.empty:
                self._atomic_write(new.sort_values(["ticker", "date"]),
                                   self.path, compression="gzip")
                return len(new), 0, 0, []

            settle_cut = new["date"].max() - pd.Timedelta(days=SETTLEMENT_DAYS)
            incoming = new.set_index(["date", "ticker"])
            key_cur = cur.set_index(["date", "ticker"])
            overlap = incoming.index.intersection(key_cur.index)

            ov_dates = overlap.get_level_values("date")
            recent_ov = overlap[ov_dates >= settle_cut]
            settled_ov = overlap[ov_dates < settle_cut]

            conflicts, details = 0, []
            if len(settled_ov):
                a = incoming.loc[settled_ov, "close"].astype(float)
                b = key_cur.loc[settled_ov, "close"].astype(float)
                rel = (a - b).abs() / b.clip(lower=1e-9)
                bad = rel[rel > CONFLICT_TOL]
                conflicts = int(len(bad))
                for (d, t), r in bad.iloc[:MAX_CONFLICT_DETAILS].items():
                    details.append({"date": str(pd.Timestamp(d).date()), "ticker": t,
                                    "stored": float(key_cur.loc[(d, t), "close"]),
                                    "incoming": float(incoming.loc[(d, t), "close"]),
                                    "rel": round(float(r), 4)})

            restated = int(len(recent_ov))
            keep_cur = key_cur.drop(index=recent_ov)          # replaceable rows out
            fresh_idx = incoming.index.difference(keep_cur.index)
            fresh = incoming.loc[fresh_idx].reset_index()
            appended = int(len(fresh_idx.difference(recent_ov)))
            merged = pd.concat([keep_cur.reset_index(), fresh[STORE_COLUMNS]])
            merged = merged.drop_duplicates(["date", "ticker"], keep="last") \
                           .sort_values(["ticker", "date"])
            self._atomic_write(merged, self.path, compression="gzip")
            return appended, restated, conflicts, details

    def append_actions(self, actions: pd.DataFrame) -> int:
        if actions is None or actions.empty:
            return 0
        with self._locked():
            cur = self.load_actions()
            merged = pd.concat([cur, actions[ACTION_COLUMNS]])
            merged = merged.drop_duplicates(["date", "ticker", "type"], keep="first")
            n_new = len(merged) - len(cur)
            if n_new > 0:
                self._atomic_write(merged.sort_values(["ticker", "date"]),
                                   self.actions_path)
            return int(max(n_new, 0))

    def restate(self, ticker: str) -> int:
        """Explicit history rewrite: drop a ticker's rows (logged); the next
        update refetches it in full. THE sanctioned path for fixing settled
        history (audit M3)."""
        with self._locked():
            cur = self.load()
            n = int((cur["ticker"] == ticker).sum())
            if n:
                self._atomic_write(cur[cur["ticker"] != ticker],
                                   self.path, compression="gzip")
        with open(self.log_path, "a") as f:
            f.write(json.dumps({"restate": ticker, "rows_dropped": n,
                                "at": datetime.now(timezone.utc).isoformat()}) + "\n")
        return n

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
            "days_stale_calendar": int(
                (pd.Timestamp.now(tz=timezone.utc).tz_localize(None) - newest).days),
            "meta": self.meta(),
        }


# ---------------------------------------------------------------------------
# corporate-action application (exact factors; heuristics only as fallback)
# ---------------------------------------------------------------------------

def apply_split_adjustments(panel, actions: pd.DataFrame):
    """Back-adjust close AND volume by exact split factors so the series is
    split-continuous (price-return regime; dividends stay unapplied and
    documented). Returns (panel, notes)."""
    from .panel import Panel
    notes = []
    if actions is None or actions.empty:
        return panel, notes
    close = panel.close.copy()
    volume = panel.volume.copy()
    splits = actions[actions["type"] == "split"]
    for _, row in splits.iterrows():
        t, d, f = row["ticker"], pd.Timestamp(row["date"]), float(row["value"])
        if t not in close.columns or f <= 0 or abs(f - 1) < 1e-9:
            continue
        mask = close.index < d
        close.loc[mask, t] = close.loc[mask, t] / f
        volume.loc[mask, t] = volume.loc[mask, t] * f
        notes.append(f"{t} {d.date()}: split factor {f:g} back-applied (close/volume)")
    return Panel(close=close, volume=volume, open=panel.open,
                 high=panel.high, low=panel.low), notes


# ---------------------------------------------------------------------------
# update flows
# ---------------------------------------------------------------------------

def _tail_for(store: PriceStore, tickers: list[str], n: int = 5) -> pd.DataFrame:
    cur = store.load()
    if cur.empty:
        return cur
    cur = cur[cur["ticker"].isin(tickers)]
    return cur.sort_values("date").groupby("ticker", sort=False).tail(n)


def update_from_network(
    store: PriceStore,
    tickers: list[str],
    default_start: str = "2018-01-01",
    source_order: tuple = ("stockanalysis", "stooq", "yahoo"),
    max_tickers_per_run: int = 600,
    pause_s: float = 0.4,
) -> UpdateReport:
    rep = UpdateReport(started_at=datetime.now(timezone.utc).isoformat(),
                       tickers_requested=len(tickers))
    rep.sources_available = probe_sources()
    usable = [s for s in source_order if rep.sources_available.get(s)]
    if not usable:
        rep.status = "no_network"
        store.log(rep)
        return rep

    src = usable[0]
    rep.source_used = src
    fetch = SOURCES[src]
    last = store.last_dates()

    # stalest-first ordering: a hit-limit cutoff must not starve the same
    # alphabetical tail forever (audit M6)
    order = sorted(tickers, key=lambda t: (last.get(t, pd.Timestamp("1900-01-01")), t))
    rep.tickers_skipped = max(len(order) - max_tickers_per_run, 0)
    order = order[:max_tickers_per_run]

    frames, all_actions = [], []
    consecutive_failures = 0
    for t in order:
        start = (str(last[t].date()) if t in last.index else default_start)
        try:
            df, acts = fetch(t, start=start)
            frames.append(df)
            if acts is not None and not acts.empty:
                all_actions.append(acts)
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            rep.tickers_failed.append(f"{t}: {type(e).__name__}: {str(e)[:80]}")
            if consecutive_failures >= ABORT_AFTER_CONSECUTIVE_FAILURES:
                rep.aborted_after_failures = True
                break
        time.sleep(pause_s)

    try:
        if frames:
            new = pd.concat(frames, ignore_index=True)
            tail = _tail_for(store, list(new["ticker"].unique()))
            new, problems = validate_rows(new, prior_tail=tail)
            rep.problems = problems
            appended, restated, conflicts, details = store.append(new)
            rep.rows_appended, rep.rows_restated = appended, restated
            rep.conflicts, rep.conflict_details = conflicts, details
            rep.tickers_updated = int(new["ticker"].nunique())
            if all_actions:
                rep.actions_recorded = store.append_actions(pd.concat(all_actions))
            fail_share = len(rep.tickers_failed) / max(len(order), 1)
            rep.status = ("partial" if fail_share > 0.10 or rep.aborted_after_failures
                          else ("updated" if appended or restated else "nothing_new"))
        else:
            rep.status = "error" if rep.tickers_failed else "nothing_new"
    except Exception as e:
        rep.problems.append(f"merge failed: {type(e).__name__}: {str(e)[:200]}")
        rep.status = "error"
    store.log(rep)
    return rep


def update_from_csv(store: PriceStore, csv_path: str | Path) -> UpdateReport:
    """Path B/C ingestion: a user-dropped CSV through the SAME validation.
    Never raises — failures become a logged report with status='error'."""
    rep = UpdateReport(started_at=datetime.now(timezone.utc).isoformat())
    try:
        from .loaders import _normalize_columns
        df = pd.read_csv(csv_path)
        df, _note = _normalize_columns(df)
        for c in ("open", "high", "low"):     # per-column fill (audit M1)
            if c not in df.columns:
                df[c] = np.nan
        if "volume" not in df.columns:
            df["volume"] = np.nan
        tickers = df["ticker"].astype(str).unique().tolist() if "ticker" in df.columns else []
        tail = _tail_for(store, tickers)
        df, problems = validate_rows(df, prior_tail=tail)
        rep.problems = problems
        appended, restated, conflicts, details = store.append(df)
        rep.rows_appended, rep.rows_restated = appended, restated
        rep.conflicts, rep.conflict_details = conflicts, details
        rep.tickers_requested = rep.tickers_updated = int(df["ticker"].nunique())
        rep.status = "updated" if (appended or restated) else "nothing_new"
    except Exception as e:
        rep.problems.append(f"{type(e).__name__}: {str(e)[:200]}")
        rep.status = "error"
    store.log(rep)
    return rep
