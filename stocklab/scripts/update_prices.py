#!/usr/bin/env python3
"""Daily/weekly price update entry point (BUILD_PLAN Phase 1).

Usage:
    python scripts/update_prices.py                  # network update (graceful if blocked)
    python scripts/update_prices.py --from-csv f.csv # ingest a dropped CSV instead
    python scripts/update_prices.py --status         # store freshness only

Exit code is 0 even when the network is blocked — scheduled runs must stay
green and simply report status; they become productive the moment the
environment's network policy allows a source.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklab.data.live import PriceStore, update_from_network, update_from_csv

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data_cache" / "live"
SECTORS = ROOT / "data_cache" / "sp500_sectors.csv"


def universe() -> list[str]:
    if SECTORS.exists():
        return sorted(pd.read_csv(SECTORS)["Symbol"].dropna().unique().tolist())
    from stocklab.data.loaders import load_bundled
    panel, _ = load_bundled()
    return sorted(panel.tickers)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-csv", default=None)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--restate", default=None, metavar="TICKER",
                    help="drop one ticker's history (refetched next run) — the "
                         "sanctioned path for fixing settled history")
    ap.add_argument("--start", default="2018-01-01",
                    help="history start for first-time fetches")
    args = ap.parse_args()

    store = PriceStore(STORE)
    if args.status:
        print(json.dumps(store.freshness(), indent=2))
        return
    if args.restate:
        n = store.restate(args.restate)
        print(f"restated {args.restate}: {n} rows dropped (refetch on next update)")
        return

    if args.from_csv:
        rep = update_from_csv(store, args.from_csv)
    else:
        rep = update_from_network(store, universe(), default_start=args.start)

    print(json.dumps(rep.to_dict(), indent=2, default=str))
    if rep.status == "no_network":
        print("\nNETWORK BLOCKED: no data source reachable under the current "
              "environment network policy.\nFix (one-time, owner action): "
              "claude.ai/code -> environment settings -> allow a market-data "
              "domain (e.g. stooq.com or query1.finance.yahoo.com),\nor use "
              "--from-csv with a dropped file. The store and all downstream "
              "steps continue to work on existing data.")
    # exit codes: green for expected idle states, loud for real failures
    # (audit finding: 'error' previously exited 0 and let the store rot silently)
    if rep.status == "error":
        sys.exit(2)
    if rep.status == "partial":
        print(f"\nWARNING: partial update — {len(rep.tickers_failed)} tickers failed"
              + (" (aborted after consecutive failures)" if rep.aborted_after_failures else ""))


if __name__ == "__main__":
    main()
