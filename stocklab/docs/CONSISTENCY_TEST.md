# Is the system consistent? — two measured tests

The deterministic layers can be proven reproducible. The *reasoning* layers are
written by LLM analysts, and until now nobody had checked whether they say the
same thing twice. If the analyst says "look at utilities" one run and
"look at advertising" the next **on identical data**, every weekly note is a
coin flip. So it was measured.

## Test 1 — the arithmetic reproduces exactly

Re-ran `analyze.py` on unchanged prices and diffed the output.

| Component | Result |
|---|---|
| Top fields, characters, movers | **byte-identical** |
| Physical-proxy panel (20 ETFs) | **byte-identical** |
| `regime` | differed — *correctly* |

The only drift was the genuinely time-varying part: every `age_days` counter
incremented by exactly 1 (a calendar day had passed) and the VIX — the one live
macro input — advanced 15.46 → 15.28. Same inputs give the same analysis; the
live input correctly updates. That is the desired behaviour, not a defect.

## Test 2 — is the "where to look" map stable week to week?

All 130 fields, 2026-08-07 vs 2026-08-11:

- **rank correlation +0.907**, mean score change 0.044, top-10 overlap 6/10.
- The churn is explainable, not random: Engineering & Construction dropped out
  (matching the prior note's call that the contractor crack would not spread),
  Food Chains entered (the new grocery stress).

*Caveat, stated plainly:* those runs are two trading days apart, so a high
correlation is expected and proves little by itself. The meaningful measurement
is the backtest's 21-day regime persistence — **IC +0.109, t 4.13** across 44
dates and 128 fields (`docs/BACKTEST_FIELDWATCH.md`). That is the real evidence.

## Test 3 — do three independent analysts agree? (the one that mattered)

Three analysts read the **identical** 2026-08-11 pack, with no knowledge of one
another, and wrote independent notes.

**Agreement was near-total on substance:**

| Checked | A | B | C |
|---|---|---|---|
| Chose theme: power/utility complex | ✓ | ✓ | ✓ |
| Chose theme: Oil & Gas Field Machinery | ✓ | ✓ | ✓ |
| Chose theme: Food Chains | ✓ | ✓ | ✓ |
| Bottom line = "selection market, 4 of 6 fields splitting" | ✓ | ✓ | ✓ |
| Flagged the backdrop as **thin** (2 of 12 indicators, 1,076-day staleness) | ✓ | ✓ | ✓ |
| Called the top-scoring field weakly supported | ✓ | ✓ | ✓ |
| Handled the QUIET trap correctly (said it did not fire rather than inventing one) | ✓ | ✓ | ✓ |

All three cited the same proxy set (COPX, DBA, GLD, NLR, SLX, SOXX, URA, USO,
XME) and reached the same physical contradictions: grocery stress with flat
agriculture, semis down while single names melt up, commodities up on 21 days
and down on 63.

**Where they diverged — and it is worth knowing:**

1. **Ordering of #1 vs #2.** The committed production note led with the
   *commodity bounce*; all three replicates led with the *power complex*. Same
   three subjects, different headline. So **the ranking of the top two themes is
   not stable; the set of themes is.**
2. **All three found something the production run missed.** Independently, and
   in their own words — A called it a "reverse gap", B an "orphan signal", C
   "negative space" — every replicate flagged that copper +19.2%, metals +15.4%
   and steel +11.1% are the loudest physical moves on the board while **no
   materials or mining field appears in the top six at all**: physical movement
   with no equity theme attached. The committed production note did not
   emphasise it. Three-for-three agreement against the single run is the
   strongest argument in this document for replicating the analyst.

## What this means for using it

- **Trust the set of flagged areas.** Three independent analysts converged on
  the same three, from the same data, with the same caveats. That is not
  improvisation.
- **Do not over-read which one is "#1".** The ordering moved between runs. Treat
  the top two or three as a set to investigate, not a ranked instruction.
- **The guardrails hold under replication.** Every replicate honoured the
  degraded-macro warning with the same specifics, and none manufactured a QUIET
  de-prioritisation when none existed. The prompt constraints are doing real
  work rather than being politely ignored.
- **A cheap upgrade is available:** two of three replicates found a real signal
  the single production run missed. Running 2-3 analysts and taking the *union*
  of their flagged contradictions would strictly dominate a single run, at the
  cost of a few minutes.

*Reproduce: re-run `scripts/analyze.py` and diff; compare `briefings/state.json`
across two commits; spawn N analysts on one pack and compare their themes.*
