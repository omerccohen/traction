#!/usr/bin/env python3
"""Run the weekly pipeline in order, with hard gates between dependent stages.

Why this exists
---------------
The stage order used to live in prose and in whoever was driving. That failed in
practice: stage 4 was started while stage 3 was still running, and a briefing
once shipped on 4.5% of the universe because the freshness check reported the
NEWEST ticker rather than the alignment of the cross-section.

So the dependencies are declared here and enforced mechanically. A stage runs
only if every stage it depends on SUCCEEDED, and gated stages additionally have
to pass a data check before the next stage may start. Nothing downstream of a
failure runs at all — it is reported as SKIPPED, never silently omitted.

The LLM stages (desk note, target finder, deep per-company rankings) are not run
here; they read the artifacts these stages produce. The runner prints which ones
are now ready.

Run:  python scripts/run_pipeline.py [--dry-run] [--from STAGE]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# name -> (argv, depends_on, gate)
# gate() runs AFTER the stage and must return (ok, message); a False blocks
# everything downstream.
MIN_ALIGNMENT = 0.95


def gate_store_aligned() -> tuple[bool, str]:
    """The cross-section must be priced on ONE day before anything ranks it."""
    sys.path.insert(0, str(ROOT))
    from stocklab.data.live import PriceStore
    f = PriceStore(ROOT / "data_cache" / "live").freshness()
    share = f.get("share_on_newest", 0.0)
    ok = share >= MIN_ALIGNMENT
    return ok, (f"{share:.2%} of {f['n_tickers']} tickers on {f['newest_date']}"
                + ("" if ok else f" — below the {MIN_ALIGNMENT:.0%} floor; "
                                 f"{f.get('n_behind')} behind, comparing them "
                                 "would mix trading days"))


def gate_pack_coverage() -> tuple[bool, str]:
    """The pack must say what it was built on, and it must be enough."""
    packs = sorted(ROOT.glob("briefings/analysis_pack_*.json"))
    if not packs:
        return False, "no analysis pack written"
    pack = json.loads(packs[-1].read_text())
    cov = pack.get("coverage")
    if not cov:
        return False, f"{packs[-1].name} carries no coverage block"
    share = cov.get("share_on_as_of", 0.0)
    return (share >= MIN_ALIGNMENT,
            f"{packs[-1].name}: {share:.2%} priced on {cov.get('as_of')}")


def gate_positions_parsed() -> tuple[bool, str]:
    """The price table must actually contain the researched companies."""
    tables = sorted(ROOT.glob("briefings/price_vs_position_*.md"))
    if not tables:
        return False, "no price table written"
    text = tables[-1].read_text()
    import re
    n = len(re.findall(r"^\| \*\*[A-Z]", text, re.M))
    groups = len(re.findall(r"^## .+researched", text, re.M))
    return n > 0, f"{tables[-1].name}: {n} companies across {groups} groups"


STAGES: dict[str, tuple[list[str], list[str], object]] = {
    "prices":     (["scripts/update_prices.py"],      [],           gate_store_aligned),
    "briefing":   (["scripts/weekly_briefing.py"],    ["prices"],   None),
    "pack":       (["scripts/analyze.py"],            ["prices"],   gate_pack_coverage),
    "targets":    (["scripts/find_targets.py"],       ["pack"],     None),
    "positions":  (["scripts/price_vs_position.py"],  ["prices"],   gate_positions_parsed),
    "questions":  (["scripts/open_questions.py"],     ["pack", "positions"], None),
}

# artifacts each LLM stage needs, so the runner can say what is ready
LLM_STAGES = {
    "desk note (analyst subagent)":        ["pack"],
    "target finder (subagent)":            ["targets"],
    "deep per-company rankings (subagent)": ["targets"],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from", dest="start", default=None,
                    help="skip stages before this one (they must already have run)")
    args = ap.parse_args()

    order = list(STAGES)
    if args.start:
        if args.start not in order:
            sys.exit(f"unknown stage {args.start!r}; known: {', '.join(order)}")
        order = order[order.index(args.start):]

    if args.dry_run:
        for name in order:
            argv, deps, gate = STAGES[name]
            print(f"{name:10s} <- {', '.join(deps) or '(nothing)':22s} "
                  f"{'gated' if gate else ''}")
        return

    status: dict[str, str] = {}
    for name in order:
        argv, deps, gate = STAGES[name]
        blocked = [d for d in deps if status.get(d, "ok") != "ok"]
        if blocked:
            status[name] = "skipped"
            print(f"\n=== {name}: SKIPPED — depends on {', '.join(blocked)}, "
                  f"which did not pass", flush=True)
            continue

        print(f"\n=== {name}: running {' '.join(argv)}", flush=True)
        t0 = time.time()
        r = subprocess.run([sys.executable, *argv], cwd=ROOT,
                           capture_output=True, text=True)
        dt = time.time() - t0
        tail = (r.stdout or r.stderr or "").strip().splitlines()[-2:]
        for line in tail:
            print(f"    {line[:160]}", flush=True)
        if r.returncode != 0:
            status[name] = "failed"
            print(f"=== {name}: FAILED (exit {r.returncode}, {dt:.0f}s)", flush=True)
            err = (r.stderr or "").strip().splitlines()[-4:]
            for line in err:
                print(f"    ! {line[:160]}", flush=True)
            continue

        if gate is not None:
            ok, msg = gate()
            print(f"    gate: {msg}", flush=True)
            if not ok:
                status[name] = "gate-failed"
                print(f"=== {name}: GATE FAILED after {dt:.0f}s — downstream "
                      "stages will not run", flush=True)
                continue
        status[name] = "ok"
        print(f"=== {name}: ok ({dt:.0f}s)", flush=True)

    print("\n" + "=" * 62)
    for name in order:
        print(f"  {name:10s} {status.get(name, 'not run')}")
    bad = [n for n, s in status.items() if s != "ok"]
    ready = [k for k, need in LLM_STAGES.items()
             if all(status.get(d) == "ok" for d in need)]
    print(f"\nready for the reasoning stages: "
          f"{'; '.join(ready) if ready else 'NONE — fix the failures above first'}")
    if bad:
        print(f"NOT ok: {', '.join(bad)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
