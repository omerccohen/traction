#!/usr/bin/env python3
"""Decision journal CLI — log what you decided, then find out if it worked.

    # log a decision (thesis and falsifier are REQUIRED, by design)
    python scripts/journal.py add --ticker EME --action watch \
        --thesis "data-center backlog growth is not in a P/E of 25" \
        --falsifier "RPO growth drops below 20% y/y in the next print"

    python scripts/journal.py review     # what happened since, vs SPY
    python scripts/journal.py score      # running record
    python scripts/journal.py close --id 0001 --reason "falsifier tripped"

Every entry is judged against SPY over the same window, so a rising market
cannot be mistaken for skill.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stocklab.data.live import PriceStore, apply_split_adjustments
from stocklab.data.loaders import sanitize_corporate_actions
from stocklab.data.panel import long_to_panel
from stocklab import journal as J

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "journal" / "decisions.csv"


def _panel():
    store = PriceStore(ROOT / "data_cache" / "live")
    p = long_to_panel(store.load())
    p, _ = apply_split_adjustments(p, store.load_actions())
    p, _ = sanitize_corporate_actions(p)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="log a decision")
    a.add_argument("--ticker", required=True)
    a.add_argument("--action", required=True, choices=list(J.ACTIONS))
    a.add_argument("--thesis", required=True,
                   help="one sentence: what you believe that the price does not")
    a.add_argument("--falsifier", required=True,
                   help="the specific thing that would prove you wrong")
    a.add_argument("--date", default=None, help="backdate (default: latest data)")
    a.add_argument("--notes", default="")

    sub.add_parser("review", help="what happened since each decision, vs SPY")
    sub.add_parser("score", help="running record")

    c = sub.add_parser("close", help="close an entry")
    c.add_argument("--id", required=True)
    c.add_argument("--reason", required=True)

    args = ap.parse_args()
    panel = _panel()

    if args.cmd == "add":
        row = J.add(JOURNAL, panel, args.ticker, args.action, args.thesis,
                    args.falsifier, when=args.date, notes=args.notes)
        print(f"logged #{row['id']}  {row['ticker']} {row['action']} "
              f"@ ${row['entry_price']:.2f} on {row['date']} "
              f"(SPY ${row['benchmark_price']:.2f})")
        print(f"  thesis:    {row['thesis']}")
        print(f"  falsifier: {row['falsifier']}")
        return

    if args.cmd == "close":
        J.close(JOURNAL, args.id, args.reason)
        print(f"closed #{args.id}: {args.reason}")
        return

    rev = J.review(JOURNAL, panel)
    if rev.empty:
        print("journal is empty — log your first decision with `add`.")
        return

    if args.cmd == "review":
        print(f"{'id':4s} {'date':11s} {'tkr':6s} {'action':8s} {'days':>5s} "
              f"{'ret':>8s} {'SPY':>8s} {'excess':>8s}  flag")
        print("-" * 72)
        for _, r in rev.iterrows():
            f = "CHECK FALSIFIER" if r["check_falsifier"] else ""
            fmt = lambda v: f"{v*100:+.1f}%" if pd.notna(v) else "    n/a"
            print(f"{str(r['id']):4s} {r['date']:11s} {r['ticker']:6s} "
                  f"{r['action']:8s} {r['days']:5d} {fmt(r['return']):>8s} "
                  f"{fmt(r['benchmark_return']):>8s} {fmt(r['excess']):>8s}  {f}")
            if r["check_falsifier"]:
                print(f"     -> {r['falsifier']}")
        return

    if args.cmd == "score":
        print(json.dumps(J.score(rev), indent=2, default=float))


if __name__ == "__main__":
    main()
