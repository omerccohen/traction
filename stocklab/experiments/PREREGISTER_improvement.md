# Pre-registration — "improvement beats levels" test

Written and committed **BEFORE** running `scripts/backtest_improvement.py`.
Purpose: stop me from grading my own homework. The prior test found that
*margin change* looked predictive (6m IC +0.042, t 2.89) **inside the 2024-01 →
2026-01 window**. That finding is snooped: I discovered it by looking. Anything
re-tested on that same window is confirmation, not evidence.

## Hypothesis (primary, one number decides it)

**H1:** A composite of *improvement* features — revenue growth, revenue-growth
acceleration, margin change, margin-change acceleration — has a **positive**
forward cross-sectional rank IC, and beats the *levels* composite (margin level,
low leverage) on the same dates.

**Decision rule, fixed in advance:**
- The primary evidence is the **held-out period 2022-03 → 2023-12**, which I have
  never examined. The 2024-01 → 2026-01 period is reported but treated as
  **tainted** (that is where the idea came from).
- H1 is **supported** only if IMPROVEMENT has positive mean IC in **both**
  sub-periods AND |t| >= 2 over the full sample.
- H1 is **weakly supported** if positive in both sub-periods but t < 2.
- H1 is **rejected** if the held-out period IC is <= 0.

## What is being tested (fixed list — no adding variants after seeing results)

Composites: `IMPROVEMENT`, `LEVELS`, `momentum` (reference), `IMPROV+momentum`.
Components reported for diagnosis only, not for cherry-picking a new headline.
Horizons: 63d and 126d. Both reported; neither is allowed to be picked post hoc
as "the" result.

## Discipline

- Point-in-time: only filings with `filed <= as_of`; only prices <= as_of.
- Same universe, same code path, same winsorized cross-sectional z-scores.
- Sector-neutral variant reported alongside raw (the levels test showed the raw
  version smuggles in a Finance short).
- Overlapping forward windows -> Newey-West t. ~45 monthly dates at 126d is
  ~8-9 independent observations. A t just above 2 is NOT strong evidence here.

## Pre-committed interpretation

Even full support would mean a **weak tilt**, not a stock-picking edge: an IC
around 0.04 explains well under 1% of cross-sectional return variance, before
costs and turnover. It would justify saying "rank research attention by
improvement, not by quality" — never "these stocks will rise."
