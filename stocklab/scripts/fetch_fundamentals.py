#!/usr/bin/env python3
"""Fetch point-in-time fundamentals from SEC EDGAR XBRL for a liquid universe,
and cache a COMPACT per-ticker series (only the concepts we need, so disk stays
small). Every data point keeps its `filed` date, so downstream code can enforce
strict point-in-time discipline (use only what was filed on/before an as-of).

This is the honest, backtestable substitute for the LLM deep-research ranker
(which cannot be backtested — it and web search already know the future).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stocklab.data.live import PriceStore
from stocklab.data.panel import long_to_panel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_cache" / "xbrl"
OUT.mkdir(parents=True, exist_ok=True)
UA = "stocklab research omerccohen@gmail.com"

# concept FAMILIES — we union all tags in a family and dedupe by (start,end),
# so a company that switched tags (e.g. NVDA) or a financial that reports
# investment income (e.g. a BDC) is still covered.
FAMILIES = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "InterestAndDividendIncomeOperating", "InvestmentIncomeOperating",
                "GrossInvestmentIncomeOperating", "RevenuesNetOfInterestExpense",
                "InterestAndFeeIncomeLoansAndLeases"],
    "op_income": ["OperatingIncomeLoss", "GrossProfit", "NetInvestmentIncome"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "liabilities": ["Liabilities"],
    "assets": ["Assets"],
}


def curl(url: str) -> bytes | None:
    try:
        r = subprocess.run(["curl", "-sS", "--http1.1", "-A", UA, "-m", "25", url],
                           capture_output=True, timeout=35)
        return r.stdout if r.returncode == 0 and r.stdout else None
    except Exception:
        return None


def compact(facts: dict) -> dict:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    out: dict[str, list] = {}
    for fam, concepts in FAMILIES.items():
        seen = {}
        for c in concepts:
            node = gaap.get(c)
            if not node:
                continue
            units = node.get("units", {})
            pts = units.get("USD") or (list(units.values())[0] if units else [])
            for p in pts:
                if "val" not in p or "filed" not in p or "end" not in p:
                    continue
                key = (p.get("start", ""), p["end"])
                # keep the earliest-filed value for each period (first knowledge);
                # a later restatement filed later would leak future knowledge.
                if key not in seen or p["filed"] < seen[key]["filed"]:
                    seen[key] = {"start": p.get("start"), "end": p["end"],
                                 "filed": p["filed"], "val": p["val"]}
        out[fam] = sorted(seen.values(), key=lambda x: (x["end"], x["filed"]))
    return out


def liquid_universe(n: int) -> list[str]:
    p = long_to_panel(PriceStore(ROOT / "data_cache" / "live").load())
    dv = (p.close * p.volume).tail(252).median().sort_values(ascending=False)
    return list(dv.dropna().index[:n])


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    cikmap = json.loads(curl("https://www.sec.gov/files/company_tickers.json") or b"{}")
    by_t = {r["ticker"]: r["cik_str"] for r in cikmap.values()}
    universe = liquid_universe(n)
    got = skipped = missing_cik = failed = 0
    for i, t in enumerate(universe):
        dest = OUT / f"{t}.json"
        if dest.exists():
            skipped += 1
            continue
        cik = by_t.get(t) or by_t.get(t.replace(".", "-")) or by_t.get(t.split(".")[0])
        if not cik:
            missing_cik += 1
            continue
        raw = curl(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
        if not raw:
            failed += 1
            time.sleep(0.3)
            continue
        try:
            dest.write_text(json.dumps(compact(json.loads(raw))))
            got += 1
        except Exception:
            failed += 1
        time.sleep(0.13)                       # ~8/s, under EDGAR's 10/s limit
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(universe)}: got {got} skip {skipped} nocik {missing_cik} fail {failed}",
                  flush=True)
    print(json.dumps({"universe": len(universe), "fetched": got, "cached_already": skipped,
                      "no_cik": missing_cik, "failed": failed}))


if __name__ == "__main__":
    main()
