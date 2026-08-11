"""Point-in-time fundamental features from the cached SEC XBRL facts.

Every function here takes an `as_of` and uses ONLY data points whose `filed`
date is on or before it — the discipline that makes any backtest built on this
honest. Restatements filed later are invisible by construction.

Three feature families:
  * `improvement_features` — how fast the business is getting better
    (growth, growth acceleration, margin change, margin acceleration)
  * `level_features`       — how good it is right now (margin, leverage)
  * `valuation_features`   — what the market already charges for that
    (earnings yield, book/price, sales/price; higher = cheaper)

The project measured that LEVELS alone sort backwards (they are already in the
price). Valuation is the missing half of that story: positioning is only
interesting relative to what you pay for it.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path


def _d(s: str) -> date:
    return date.fromisoformat(s)


def load_facts(xbrl_dir: Path) -> dict[str, dict]:
    return {f.stem: json.loads(f.read_text()) for f in Path(xbrl_dir).glob("*.json")}


def quarterly(points, as_of_iso: str) -> list[dict]:
    """Point-in-time quarterly (flow) series, deduped by period end."""
    q = [p for p in points if p["filed"] <= as_of_iso and p.get("start")
         and 80 <= (_d(p["end"]) - _d(p["start"])).days <= 100]
    q.sort(key=lambda p: p["end"])
    seen: dict[str, dict] = {}
    for p in q:
        seen.setdefault(p["end"], p)      # earliest-filed wins = first knowledge
    return sorted(seen.values(), key=lambda p: p["end"])


def annual(points, as_of_iso: str) -> list[dict]:
    """Point-in-time annual (10-K) flow series."""
    a = [p for p in points if p["filed"] <= as_of_iso and p.get("start")
         and 350 <= (_d(p["end"]) - _d(p["start"])).days <= 380]
    seen: dict[str, dict] = {}
    for p in sorted(a, key=lambda p: p["end"]):
        seen.setdefault(p["end"], p)
    return sorted(seen.values(), key=lambda p: p["end"])


def quarterly_complete(points, as_of_iso: str) -> list[dict]:
    """Quarterly series with the MISSING Q4 reconstructed.

    Companies file no 10-Q for their fourth quarter — it exists only inside the
    10-K as an annual figure. So a naive quarterly series has a hole every year,
    and "the last four quarters" silently spans ~455 days. Here Q4 is derived as
    (annual - the three filed quarters) and stamped with the 10-K's filing date,
    which keeps it strictly point-in-time: you learn Q4 when the 10-K lands.
    """
    q = quarterly(points, as_of_iso)
    by_end = {p["end"]: p for p in q}
    for a in annual(points, as_of_iso):
        inside = [p for p in q if p["start"] and p["start"] >= a["start"] and p["end"] <= a["end"]]
        if len(inside) != 3:
            continue
        inside.sort(key=lambda p: p["end"])
        # the gap is whichever quarter of the annual period is absent
        covered_end = inside[-1]["end"]
        if covered_end == a["end"]:                       # gap is not the last quarter
            gap_start, gap_end = a["start"], inside[0]["start"]
            span = (_d(gap_end) - _d(gap_start)).days
        else:
            gap_start, gap_end = covered_end, a["end"]
            span = (_d(gap_end) - _d(gap_start)).days
        if not (80 <= span <= 100) or gap_end in by_end:
            continue
        derived = {"start": gap_start, "end": gap_end, "filed": a["filed"],
                   "val": a["val"] - sum(p["val"] for p in inside), "derived": True}
        by_end[gap_end] = derived
    return sorted(by_end.values(), key=lambda p: p["end"])


def instant(points, as_of_iso: str) -> dict | None:
    """Latest balance-sheet (stock) value known at as_of."""
    i = [p for p in points if p["filed"] <= as_of_iso and not p.get("start")]
    i.sort(key=lambda p: (p["end"], p["filed"]))
    return i[-1] if i else None


def latest_any(points, as_of_iso: str) -> dict | None:
    """Latest value of any shape known at as_of (shares can be tagged either way)."""
    i = [p for p in points if p["filed"] <= as_of_iso]
    i.sort(key=lambda p: (p["end"], p["filed"]))
    return i[-1] if i else None


def year_ago(q: list[dict], ref: dict) -> dict | None:
    tgt = _d(ref["end"]) - timedelta(days=365)
    c = [p for p in q if p["end"] < ref["end"] and abs((_d(p["end"]) - tgt).days) <= 45]
    return min(c, key=lambda p: abs((_d(p["end"]) - tgt).days)) if c else None


def ttm(q: list[dict], n: int = 4) -> float | None:
    """Trailing-twelve-month sum of a quarterly flow, if 4 quarters spanning ~1y."""
    if len(q) < n:
        return None
    last = q[-n:]
    span = (_d(last[-1]["end"]) - _d(last[0]["start"] or last[0]["end"])).days
    if not (300 <= span <= 430):
        return None
    return float(sum(p["val"] for p in last))


def _margin(oi: dict, rv: dict, p: dict | None) -> float | None:
    if p and p["end"] in oi and rv.get(p["end"]):
        m = oi[p["end"]] / rv[p["end"]]
        return m if -2 < m < 2 else None
    return None


def improvement_features(fam: dict, as_of_iso: str) -> dict | None:
    """How fast is it getting better? (change + acceleration)"""
    rev_q = quarterly(fam.get("revenue", []), as_of_iso)
    if len(rev_q) < 6:
        return None
    cur, prev = rev_q[-1], rev_q[-2]
    cur_ya, prev_ya = year_ago(rev_q, cur), year_ago(rev_q, prev)
    if not cur_ya or not cur_ya["val"] or cur["val"] <= 0:
        return None
    g_now = cur["val"] / cur_ya["val"] - 1
    if not (-0.9 < g_now < 5):
        return None
    g_prev = (prev["val"] / prev_ya["val"] - 1) if (prev_ya and prev_ya["val"]) else None
    rev_accel = (g_now - g_prev) if g_prev is not None else None
    if rev_accel is not None and not (-3 < rev_accel < 3):
        rev_accel = None

    oi = {p["end"]: p["val"] for p in quarterly(fam.get("op_income", []), as_of_iso)}
    rv = {p["end"]: p["val"] for p in rev_q}
    m_now, m_ya = _margin(oi, rv, cur), _margin(oi, rv, cur_ya)
    m_prev, m_prev_ya = _margin(oi, rv, prev), _margin(oi, rv, prev_ya)
    chg = (m_now - m_ya) if (m_now is not None and m_ya is not None) else None
    chg_prev = (m_prev - m_prev_ya) if (m_prev is not None and m_prev_ya is not None) else None
    return {"rev_growth": g_now, "rev_accel": rev_accel, "margin": m_now,
            "margin_chg": chg,
            "margin_accel": (chg - chg_prev) if (chg is not None and chg_prev is not None) else None}


def level_features(fam: dict, as_of_iso: str) -> dict:
    """How good is it right now? (already-in-the-price side)"""
    eq = instant(fam.get("equity", []), as_of_iso)
    li = instant(fam.get("liabilities", []), as_of_iso)
    lev = (li["val"] / eq["val"]) if (eq and li and eq["val"] > 0) else None
    if lev is not None and not (0 <= lev < 50):
        lev = None
    return {"leverage": lev, "book_equity": eq["val"] if eq else None}


def valuation_features(fam: dict, as_of_iso: str, price: float) -> dict | None:
    """What does the market already charge? Yields, so higher = CHEAPER.

    Yields rather than P/E-style ratios: monotone, and they degrade gracefully
    for loss-making companies instead of exploding through infinity.
    """
    sh = latest_any(fam.get("shares", []), as_of_iso)
    if not sh or not sh["val"] or sh["val"] < 1e5 or not price or price <= 0:
        return None
    mktcap = float(sh["val"]) * float(price)
    if mktcap <= 0:
        return None

    rev_ttm = ttm(quarterly_complete(fam.get("revenue", []), as_of_iso))
    ni_ttm = ttm(quarterly_complete(fam.get("net_income", []), as_of_iso))
    eq = instant(fam.get("equity", []), as_of_iso)

    out = {"market_cap": mktcap,
           "earnings_yield": (ni_ttm / mktcap) if ni_ttm is not None else None,
           "book_to_price": (eq["val"] / mktcap) if (eq and eq["val"] is not None) else None,
           "sales_to_price": (rev_ttm / mktcap) if rev_ttm is not None else None}
    # sanity gates: absurd values mean mis-tagged XBRL, so drop the metric
    if out["earnings_yield"] is not None and not (-2 < out["earnings_yield"] < 2):
        out["earnings_yield"] = None
    if out["book_to_price"] is not None and not (-5 < out["book_to_price"] < 20):
        out["book_to_price"] = None
    if out["sales_to_price"] is not None and not (0 <= out["sales_to_price"] < 50):
        out["sales_to_price"] = None
    if all(out[k] is None for k in ("earnings_yield", "book_to_price", "sales_to_price")):
        return None
    return out
