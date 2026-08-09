"""Physical/macro indicator registry (BUILD_PLAN Phase 3).

The field-verification layer of the funnel: slow, countable series with
PRE-REGISTERED thresholds (indicators/registry.yml — committed before use,
same discipline as docs/PREREGISTRATION.md). No forecasting: an indicator is
either inside its normal range or it isn't, and threshold crossings are the
events the weekly briefing surfaces.

Point-in-time discipline: every fetch APPENDS to a local cache with a
`retrieved_at` stamp; historical cache rows are never rewritten, so "what did
we know on date X" stays answerable. When the network policy blocks the
source, the cache serves the last-good data, clearly aged.
"""
from __future__ import annotations

import io
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PKG_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PKG_ROOT / "data_cache" / "indicators"
REGISTRY = Path(__file__).resolve().parent / "registry.yml"


def _http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "stocklab/0.3"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_fred_csv(spec: dict) -> pd.DataFrame:
    """FRED's keyless CSV endpoint. Returns columns [date, value]."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={spec['series_id']}"
    raw = _http_get(url)
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()


def fetch_github_csv(spec: dict) -> pd.DataFrame:
    """Auto-updated CSV mirrors on raw.githubusercontent.com (datahub core
    datasets et al.) — the one host the default network policy allows, and
    several are refreshed by upstream GitHub Actions (VIX daily is current).

    spec fields: series_id = raw URL, date_col, value_col, and
    zero_as_missing (the Shiller dataset pads recent rows of derived columns
    with 0.0 — impossible values for CPI/rates/PE10 — which would poison yoy
    transforms if kept).
    """
    raw = _http_get(spec["series_id"])
    df = pd.read_csv(io.BytesIO(raw))
    date_col = spec.get("date_col", "date")
    value_col = spec["value_col"]
    if date_col not in df.columns or value_col not in df.columns:
        raise ValueError(f"github_csv: columns {date_col!r}/{value_col!r} not in "
                         f"{list(df.columns)[:8]}")
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col]),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    })
    if spec.get("zero_as_missing"):
        out.loc[out["value"] == 0.0, "value"] = np.nan
    return out.dropna()


FETCHERS = {"fred": fetch_fred_csv, "github_csv": fetch_github_csv}


@dataclass
class IndicatorStatus:
    name: str
    description: str
    latest_date: str | None
    latest_value: float | None
    transform: str
    transformed_value: float | None
    pctile_5y: float | None          # trailing percentile of transformed value
    threshold_state: str             # OK | ELEVATED | TRIGGERED | NO_DATA
    threshold_note: str
    data_age_days: int | None
    source_state: str                # fresh | cache | none


class Indicator:
    def __init__(self, name: str, spec: dict):
        self.name = name
        self.spec = dict(spec)
        self.source = spec["source"]
        self.series_id = spec["series_id"]
        self.description = spec.get("description", "")
        self.transform = spec.get("transform", "level")   # level | yoy | yoy_diff
        self.thresholds = spec.get("thresholds", {})      # {elevated: expr, triggered: expr}
        self.registered_on = str(spec.get("registered_on", ""))
        self.cache_path = CACHE_DIR / f"{name}.csv"

    # -- data ---------------------------------------------------------------
    def refresh(self) -> str:
        """Fetch and append new observations AND revisions as vintages.

        FRED revises several registered series routinely (IP, new orders,
        PPI). First-print-wins made status() evaluate stale prints forever
        while also failing the PIT promise (audit F13). Policy now: a changed
        value for an existing date is APPENDED with its own retrieved_at —
        the cache is a vintage log. series() reads the latest vintage;
        series_asof() answers "what did we know on date X".
        """
        try:
            new = FETCHERS[self.source](self.spec)
        except Exception:
            return "cache" if self.cache_path.exists() else "none"
        new = new.copy()
        new["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            cur = pd.read_csv(self.cache_path, parse_dates=["date"])
            latest = (cur.sort_values(["date", "retrieved_at"])
                      .drop_duplicates("date", keep="last")
                      .set_index("date")["value"])
            aligned = latest.reindex(new["date"])
            changed = (aligned.isna().to_numpy()
                       | ~np.isclose(aligned.to_numpy(dtype=float),
                                     new["value"].to_numpy(dtype=float),
                                     rtol=1e-9, atol=1e-12))
            fresh = new[changed]
            if len(fresh):
                pd.concat([cur, fresh]).to_csv(self.cache_path, index=False)
        else:
            new.to_csv(self.cache_path, index=False)
        return "fresh"

    def _cache(self) -> pd.DataFrame | None:
        if not self.cache_path.exists():
            return None
        return pd.read_csv(self.cache_path, parse_dates=["date"])

    def series(self) -> pd.Series | None:
        """Latest vintage per observation date."""
        df = self._cache()
        if df is None:
            return None
        df = df.sort_values(["date", "retrieved_at"]).drop_duplicates("date", keep="last")
        return df.set_index("date")["value"].sort_index()

    def series_asof(self, retrieved_before: str) -> pd.Series | None:
        """Point-in-time view: only vintages retrieved before the cutoff."""
        df = self._cache()
        if df is None:
            return None
        df = df[df["retrieved_at"] < retrieved_before]
        if df.empty:
            return None
        df = df.sort_values(["date", "retrieved_at"]).drop_duplicates("date", keep="last")
        return df.set_index("date")["value"].sort_index()

    # -- evaluation ---------------------------------------------------------
    def _transformed(self, s: pd.Series) -> pd.Series:
        if self.transform == "yoy":
            return s.pct_change(_periods_per_year(s))
        if self.transform == "yoy_diff":
            return s.diff(_periods_per_year(s))
        return s

    def status(self, source_state: str = "cache") -> IndicatorStatus:
        s = self.series()
        if s is None:
            return IndicatorStatus(self.name, self.description, None, None,
                                   self.transform, None, None, "NO_DATA",
                                   "no cached data (network blocked and no snapshot)",
                                   None, "none")
        if len(s) < 8:
            return IndicatorStatus(self.name, self.description,
                                   str(s.index[-1].date()), float(s.iloc[-1]),
                                   self.transform, None, None, "NO_DATA",
                                   f"insufficient history ({len(s)} rows)",
                                   None, source_state)
        t = self._transformed(s).dropna()
        if len(t) == 0:
            return IndicatorStatus(self.name, self.description,
                                   str(s.index[-1].date()), float(s.iloc[-1]),
                                   self.transform, None, None, "NO_DATA",
                                   "insufficient history for transform", None, source_state)
        val = float(t.iloc[-1])
        ppy = _periods_per_year(s)
        window = t.iloc[-(ppy * 5):]
        # midrank ties + minimum window of one year of periods: a 9-point
        # window must not fire a "5y percentile" alarm, and a flat series
        # must not read as p100 (audit F15)
        if len(window) >= max(ppy, 8):
            pct = float(((window < val).mean() + (window <= val).mean()) / 2.0)
            pct_n = int(len(window))
        else:
            pct, pct_n = None, int(len(window))

        uses_pctile = any("pctile" in str(r) for r in self.thresholds.values())
        if pct is None and uses_pctile:
            # a pctile rule with no usable percentile is UNKNOWN, not OK
            # (audit F16: "inside normal range" claimed knowledge we lack)
            state, note = "UNKNOWN", f"short history for percentile (n={pct_n})"
        else:
            state, note = "OK", "inside normal range"
            for level in ("elevated", "triggered"):
                rule = self.thresholds.get(level)
                if rule is None:
                    continue
                if _eval_rule(rule, val, pct):
                    state = "ELEVATED" if level == "elevated" else "TRIGGERED"
                    note = f"{level}: {rule}"
        age = int((pd.Timestamp(datetime.now(timezone.utc).date()) - s.index[-1]).days)
        # staleness relative to the series' own frequency (audit F19): a
        # monthly series is fine at 60d; a daily one is dead at 60d
        expected_lag = 2.5 * (365.0 / ppy) + 15
        if age > expected_lag and state in ("OK", "UNKNOWN"):
            note += f"; STALE ({age}d old vs ~{int(expected_lag)}d expected)"
        return IndicatorStatus(
            self.name, self.description, str(s.index[-1].date()), float(s.iloc[-1]),
            self.transform, round(val, 4), None if pct is None else round(pct, 2),
            state, note, age, source_state,
        )


def _periods_per_year(s: pd.Series) -> int:
    if len(s) < 3:
        return 12
    med_days = float(s.index.to_series().diff().dt.days.median())
    if med_days <= 4:
        return 252
    if med_days <= 9:
        return 52
    if med_days <= 45:
        return 12
    return 4


def parse_rule(rule: str) -> tuple[str, str, float]:
    """Parse 'var op number'. RAISES on malformed rules — a silent False
    turned a threshold typo into a permanently disabled alarm rendered as OK
    (audit F14). load_registry() dry-runs every rule at load time."""
    parts = str(rule).split()
    if len(parts) != 3:
        raise ValueError(f"malformed threshold rule {rule!r} (need 'var op number')")
    var, op, num_s = parts
    if var not in ("value", "pctile"):
        raise ValueError(f"unknown variable {var!r} in rule {rule!r}")
    if op not in ("<", ">", "<=", ">="):
        raise ValueError(f"unknown operator {op!r} in rule {rule!r}")
    try:
        num = float(num_s)
    except ValueError:
        raise ValueError(f"bad number {num_s!r} in rule {rule!r}") from None
    return var, op, num


def _eval_rule(rule: str, value: float, pctile: float | None) -> bool:
    var, op, num = parse_rule(rule)
    x = value if var == "value" else pctile
    if x is None:
        return False
    return {"<": x < num, ">": x > num, "<=": x <= num, ">=": x >= num}[op]


# ---------------------------------------------------------------------------

def load_registry(path: Path | None = None) -> list[Indicator]:
    p = path or REGISTRY
    spec = yaml.safe_load(p.read_text())
    today = datetime.now(timezone.utc).date().isoformat()
    inds = []
    for name, s in spec["indicators"].items():
        # pre-registration enforcement (audit F23): every indicator carries a
        # registered_on date, refused if missing or in the future; the date is
        # rendered in the dashboard so the artifact carries its own audit trail
        reg = s.get("registered_on")
        if not reg:
            raise ValueError(f"indicator {name!r}: missing registered_on date")
        if str(reg) > today:
            raise ValueError(f"indicator {name!r}: registered_on {reg} is in the future")
        for level, rule in (s.get("thresholds") or {}).items():
            parse_rule(rule)   # raises loudly on malformed rules (audit F14)
        inds.append(Indicator(name, s))
    return inds


def refresh_all(indicators: list[Indicator]) -> dict[str, str]:
    return {ind.name: ind.refresh() for ind in indicators}


def _fmt_value(v: float | None, transform: str) -> str:
    """Per-transform formatting: an unlabeled 0.03 reads as 0.03 when it means
    3% yoy (audit F24)."""
    if v is None:
        return "—"
    if transform == "yoy":
        return f"{v:+.1%}"
    if transform == "yoy_diff":
        return f"{v:+.2f}pp"
    return f"{v:.2f}"


def dashboard_markdown(indicators: list[Indicator], states: dict[str, str] | None = None) -> str:
    lines = [
        "## Physical & macro indicators (pre-registered thresholds)",
        "",
        "| indicator | latest | value | 5y pctile | state | age | src | registered |",
        "|---|---|---|---|---|---|---|---|",
    ]
    any_data = False
    for ind in indicators:
        st = ind.status((states or {}).get(ind.name, "cache"))
        if st.threshold_state != "NO_DATA":
            any_data = True
        flag = {"OK": "", "ELEVATED": " (!)", "TRIGGERED": " (!!)",
                "NO_DATA": "", "UNKNOWN": " (?)"}[st.threshold_state]
        lines.append(
            f"| {ind.name}{flag} | {st.latest_date or '—'} | "
            f"{_fmt_value(st.transformed_value, st.transform)} | "
            f"{'—' if st.pctile_5y is None else f'p{st.pctile_5y*100:.0f}'} | "
            f"{st.threshold_state} | "
            f"{'—' if st.data_age_days is None else f'{st.data_age_days}d'} | "
            f"{st.source_state} | {ind.registered_on or '—'} |"
        )
    if not any_data:
        lines.append("")
        lines.append("*No indicator data cached yet and the network policy blocks the "
                     "sources — this section fills on the first run in a "
                     "network-permitted environment.*")
    lines.append("")
    lines.append("*Thresholds are pre-registered in `stocklab/indicators/registry.yml` "
                 "(dates shown); crossings are events to research, not signals to trade.*")
    return "\n".join(lines)
