"""Decision journal + scorecard — the system's missing feedback loop.

Everything else in this project describes the world. Nothing recorded what YOU
decided or whether it worked. Without that, there is no way to tell skill from a
bull market — which is exactly the trap every backtest here kept falling into.

The design is deliberately harsh in three ways:

1. **Every decision is scored against SPY, not against zero.** "+12%" means
   nothing if the index did +14%. Only EXCESS return is counted.
2. **Passes are scored too.** The names you looked at and skipped are half your
   process. If your passes keep outperforming your buys, that is the finding.
3. **Every entry needs a falsifier** — a specific thing that would prove the
   thesis wrong. An entry without one cannot be closed honestly, because you can
   always invent a reason to hold.

Small samples lie: the scorecard refuses to report a "hit rate" as meaningful
below MIN_MEANINGFUL_N decisions and says so out loud.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = ["id", "date", "ticker", "action", "thesis", "falsifier",
           "entry_price", "benchmark_price", "status", "close_date",
           "close_reason", "notes"]
ACTIONS = ("watch", "starter", "add", "exit", "pass")
BENCHMARK = "SPY"
MIN_MEANINGFUL_N = 20        # below this, a hit rate is noise and we say so


def load(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype={"id": str})
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    return df[COLUMNS]


def save(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)                       # atomic — never half-write the log


def _price_on(panel, ticker: str, when: pd.Timestamp) -> float | None:
    if ticker not in panel.close.columns:
        return None
    s = panel.close[ticker].loc[:when].dropna()
    return float(s.iloc[-1]) if len(s) else None


def add(path: Path, panel, ticker: str, action: str, thesis: str,
        falsifier: str, when=None, notes: str = "") -> dict:
    """Log one decision, stamping the prices it must later be judged against."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}")
    if not thesis.strip():
        raise ValueError("a decision needs a thesis — one sentence on what you "
                         "believe that the price does not")
    if not falsifier.strip():
        raise ValueError("a decision needs a falsifier — the specific thing that "
                         "would prove it wrong. Without one you can always "
                         "rationalise holding")
    df = load(path)
    when = pd.Timestamp(when) if when is not None else panel.dates[-1]
    ticker = ticker.upper()
    row = {
        "id": f"{len(df) + 1:04d}",
        "date": str(pd.Timestamp(when).date()),
        "ticker": ticker,
        "action": action,
        "thesis": thesis.strip(),
        "falsifier": falsifier.strip(),
        "entry_price": _price_on(panel, ticker, when),
        "benchmark_price": _price_on(panel, BENCHMARK, when),
        "status": "open",
        "close_date": "", "close_reason": "", "notes": notes.strip(),
    }
    if row["entry_price"] is None:
        raise ValueError(f"no price for {ticker} on/before {when.date()} — is it "
                         "in the price store?")
    save(pd.concat([df, pd.DataFrame([row])], ignore_index=True), path)
    return row


def close(path: Path, entry_id: str, reason: str, when=None) -> None:
    df = load(path)
    m = df["id"].astype(str) == str(entry_id)
    if not m.any():
        raise ValueError(f"no journal entry with id {entry_id}")
    df.loc[m, "status"] = "closed"
    df.loc[m, "close_date"] = str(pd.Timestamp(
        when or datetime.now(timezone.utc).date()).date())
    df.loc[m, "close_reason"] = reason
    save(df, path)


def review(path: Path, panel) -> pd.DataFrame:
    """What has happened since each decision — against the benchmark, not zero."""
    df = load(path)
    if df.empty:
        return df
    as_of = panel.dates[-1]
    out = []
    for _, r in df.iterrows():
        # an open entry's close_date round-trips through CSV as NaN, and
        # str(NaN) == "nan" — truthy. That silently produced NaT dates, which
        # made `days` NaN and quietly disabled the falsifier check on every
        # open entry. Test for real emptiness, not truthiness.
        cd = r.get("close_date")
        closed = pd.notna(cd) and str(cd).strip().lower() not in ("", "nan", "nat")
        end = pd.Timestamp(cd) if closed else as_of
        px = _price_on(panel, r["ticker"], end)
        bpx = _price_on(panel, BENCHMARK, end)
        ret = ((px / float(r["entry_price"]) - 1)
               if px and pd.notna(r["entry_price"]) and float(r["entry_price"]) else np.nan)
        bret = ((bpx / float(r["benchmark_price"]) - 1)
                if bpx and pd.notna(r["benchmark_price"]) and float(r["benchmark_price"])
                else np.nan)
        days = int((pd.Timestamp(end) - pd.Timestamp(r["date"])).days)
        out.append({**r.to_dict(), "current_price": px, "return": ret,
                    "benchmark_return": bret, "excess": ret - bret, "days": days,
                    # a falsifier you have not looked at in a month is not a
                    # falsifier, it is a decoration
                    "check_falsifier": bool(r["status"] == "open" and days >= 30)})
    return pd.DataFrame(out)


def score(reviewed: pd.DataFrame) -> dict:
    """Running scorecard. Deliberately refuses to flatter small samples."""
    if reviewed.empty:
        return {"n": 0, "verdict": "no decisions logged yet"}
    # 'pass' = a name you looked at and skipped; it is scored INVERTED, because
    # a good pass is one that went on to underperform.
    held = reviewed[reviewed["action"].isin(["watch", "starter", "add"])]
    passed = reviewed[reviewed["action"] == "pass"]

    def blk(d, invert=False):
        e = d["excess"].dropna()
        if e.empty:
            return {"n": 0}
        v = -e if invert else e
        return {"n": int(len(e)),
                "hit_rate_vs_spy": round(float((v > 0).mean()), 3),
                "mean_excess": round(float(v.mean()), 4),
                "median_excess": round(float(v.median()), 4),
                "best": round(float(v.max()), 4), "worst": round(float(v.min()), 4)}

    n = int(reviewed["excess"].notna().sum())
    out = {"n_decisions": n,
           "held_or_watched": blk(held),
           "passed_scored_inverted": blk(passed, invert=True),
           "open": int((reviewed["status"] == "open").sum()),
           "needing_falsifier_check": int(reviewed["check_falsifier"].sum())}
    if n < MIN_MEANINGFUL_N:
        out["verdict"] = (f"{n} scored decisions — TOO FEW TO MEAN ANYTHING. "
                          f"Do not draw conclusions before {MIN_MEANINGFUL_N}; "
                          "at this size a coin flip looks like skill.")
    else:
        e = held["excess"].dropna()
        t = float(e.mean() / (e.std(ddof=1) / np.sqrt(len(e)))) if len(e) > 1 and e.std(ddof=1) else 0.0
        out["t_stat_vs_spy"] = round(t, 2)
        out["verdict"] = ("beating SPY so far" if t > 2 else
                          "no evidence of an edge vs SPY yet" if abs(t) <= 2 else
                          "underperforming SPY")
    return out
