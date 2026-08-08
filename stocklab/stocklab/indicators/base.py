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


def fetch_fred_csv(series_id: str) -> pd.DataFrame:
    """FRED's keyless CSV endpoint. Returns columns [date, value]."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = _http_get(url)
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()


FETCHERS = {"fred": fetch_fred_csv}


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
        self.source = spec["source"]
        self.series_id = spec["series_id"]
        self.description = spec.get("description", "")
        self.transform = spec.get("transform", "level")   # level | yoy | yoy_diff
        self.thresholds = spec.get("thresholds", {})      # {elevated: expr, triggered: expr}
        self.cache_path = CACHE_DIR / f"{name}.csv"

    # -- data ---------------------------------------------------------------
    def refresh(self) -> str:
        """Fetch and append new observations. Returns 'fresh'|'cache'|'none'."""
        try:
            new = FETCHERS[self.source](self.series_id)
        except Exception:
            return "cache" if self.cache_path.exists() else "none"
        new["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            cur = pd.read_csv(self.cache_path, parse_dates=["date"])
            fresh = new[~new["date"].isin(cur["date"])]
            if len(fresh):
                pd.concat([cur, fresh]).to_csv(self.cache_path, index=False)
        else:
            new.to_csv(self.cache_path, index=False)
        return "fresh"

    def series(self) -> pd.Series | None:
        if not self.cache_path.exists():
            return None
        df = pd.read_csv(self.cache_path, parse_dates=["date"])
        s = df.set_index("date")["value"].sort_index()
        return s[~s.index.duplicated(keep="last")]

    # -- evaluation ---------------------------------------------------------
    def _transformed(self, s: pd.Series) -> pd.Series:
        if self.transform == "yoy":
            return s.pct_change(_periods_per_year(s))
        if self.transform == "yoy_diff":
            return s.diff(_periods_per_year(s))
        return s

    def status(self, source_state: str = "cache") -> IndicatorStatus:
        s = self.series()
        if s is None or len(s) < 8:
            return IndicatorStatus(self.name, self.description, None, None,
                                   self.transform, None, None, "NO_DATA",
                                   "no cached data (network blocked and no snapshot)",
                                   None, "none")
        t = self._transformed(s).dropna()
        if len(t) == 0:
            return IndicatorStatus(self.name, self.description,
                                   str(s.index[-1].date()), float(s.iloc[-1]),
                                   self.transform, None, None, "NO_DATA",
                                   "insufficient history for transform", None, source_state)
        val = float(t.iloc[-1])
        window = t.iloc[-(_periods_per_year(s) * 5):]
        pct = float((window <= val).mean()) if len(window) >= 8 else None

        state, note = "OK", "inside normal range"
        for level in ("elevated", "triggered"):
            rule = self.thresholds.get(level)
            if rule is None:
                continue
            if _eval_rule(rule, val, pct):
                state = "ELEVATED" if level == "elevated" else "TRIGGERED"
                note = f"{level}: {rule}"
        age = int((pd.Timestamp(datetime.now(timezone.utc).date()) - s.index[-1]).days)
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


def _eval_rule(rule: str, value: float, pctile: float | None) -> bool:
    """Tiny safe rule language: 'value > 0.05', 'value < 0', 'pctile > 0.9'."""
    try:
        var, op, num = rule.split()
        x = {"value": value, "pctile": pctile}[var]
        if x is None:
            return False
        num = float(num)
        return {"<": x < num, ">": x > num, "<=": x <= num, ">=": x >= num}[op]
    except Exception:
        return False


# ---------------------------------------------------------------------------

def load_registry(path: Path | None = None) -> list[Indicator]:
    p = path or REGISTRY
    spec = yaml.safe_load(p.read_text())
    return [Indicator(name, s) for name, s in spec["indicators"].items()]


def refresh_all(indicators: list[Indicator]) -> dict[str, str]:
    return {ind.name: ind.refresh() for ind in indicators}


def dashboard_markdown(indicators: list[Indicator], states: dict[str, str] | None = None) -> str:
    lines = [
        "## Physical & macro indicators (pre-registered thresholds)",
        "",
        "| indicator | latest | transform | value | 5y pctile | state | age |",
        "|---|---|---|---|---|---|---|",
    ]
    any_data = False
    for ind in indicators:
        st = ind.status((states or {}).get(ind.name, "cache"))
        if st.threshold_state != "NO_DATA":
            any_data = True
        flag = {"OK": "", "ELEVATED": " (!)", "TRIGGERED": " (!!)", "NO_DATA": ""}[st.threshold_state]
        lines.append(
            f"| {ind.name}{flag} | {st.latest_date or '—'} | {st.transform} | "
            f"{'—' if st.transformed_value is None else st.transformed_value} | "
            f"{'—' if st.pctile_5y is None else f'p{st.pctile_5y*100:.0f}'} | "
            f"{st.threshold_state} | {'—' if st.data_age_days is None else f'{st.data_age_days}d'} |"
        )
    if not any_data:
        lines.append("")
        lines.append("*No indicator data cached yet and the network policy blocks the "
                     "sources — this section fills on the first run in a "
                     "network-permitted environment.*")
    lines.append("")
    lines.append("*Thresholds are pre-registered in `stocklab/indicators/registry.yml`; "
                 "crossings are events to research, not signals to trade.*")
    return "\n".join(lines)
