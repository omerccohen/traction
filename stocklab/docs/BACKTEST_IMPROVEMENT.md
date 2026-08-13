# Does ranking by IMPROVEMENT beat ranking by LEVELS? — pre-registered test

> ## RETRACTED 2026-08-13 — the comparison had no legs on either side
>
> This page's verdict rests on improvement (t 1.93) beating levels (t −3.15).
> Both numbers came from a universe chosen by **today's** liquidity applied back
> to 2018 (full detail in the banner on `docs/BACKTEST_VALUATION.md`). Screened
> to names actually tradeable on each date, at $150M/day:
>
> | signal, 126d | as published | tradeable universe |
> |---|---|---|
> | IMPROVEMENT | +0.018, t 1.93 | **+0.003, t 0.17** |
> | LEVELS | −0.053, t −3.15 | **−0.029, t −0.96** |
>
> Improvement is **zero**, not faint. Levels do **not** sort backwards. So H1's
> comparison is not "weakly supported" — it is untestable on this evidence,
> because neither side is distinguishable from noise once the sample is
> restricted to companies a book could have owned.
>
> The audit also found the pre-registration was written first (git confirms the
> order) but **not applied**: the primary "combination beats either alone" test
> fails on IC (0.045 < 0.051) and this page states it backwards, and the
> held-out window had already been opened 2h31m earlier by the improvement run
> without being logged in `HOLDOUT_OPENED.json`.
>
> Kept below unedited as the record.

**Verdict, by the rule fixed in advance: H1 is WEAKLY SUPPORTED.**
Improvement beats levels decisively — but improvement on its own is a faint
tilt, not a stock-picking edge, and the one number that looked exciting last
round turned out to be mostly **my own data-snooping**.

Hypothesis and decision rule were committed **before** running, in
`experiments/PREREGISTER_improvement.md`.

## Setup

- 592 liquid US names, ~500 per date, **47 monthly as-of dates, 2022-03 → 2026-01**.
- Strict point-in-time: only filings with `filed <= as_of`, only prices <= as_of.
- **HELD-OUT: 22 dates (2022-03 → 2023-12)** — never examined before this run.
  **TAINTED: 25 dates (2024-01 → 2026-01)** — where margin-change was discovered.
- IMPROVEMENT = revenue growth + revenue-growth acceleration + margin change +
  margin-change acceleration. LEVELS = margin level + low leverage.

## Result 1 — the pre-registration did its job: margin-change was mostly snooped

| component (6-month IC) | full | **held-out** | tainted |
|---|---|---|---|
| **margin change** | +0.036 (t 2.68) | **+0.007** | **+0.062** |
| revenue growth | +0.022 | +0.008 | +0.034 |
| revenue-growth acceleration | −0.020 | −0.016 | −0.024 |
| margin acceleration | −0.007 | −0.020 | +0.004 |

Margin-change's apparent significance (t 2.68) lives almost entirely in the
window where I found it: **+0.062 tainted vs +0.007 held-out — effectively zero
out-of-sample.** Had I skipped pre-registration I would have reported a t 2.7
"edge" that is largely an artifact of having looked first. *Acceleration — the
second derivative — did not work at all; it was negative.*

## Result 2 — improvement DOES beat levels (this part is solid)

| signal (6-month IC) | full | NW t | held-out | tainted |
|---|---|---|---|---|
| IMPROVEMENT | +0.014 | +1.06 | +0.009 | +0.018 |
| IMPROVEMENT (sector-neutral) | +0.017 | +1.85 | +0.011 | +0.022 |
| **LEVELS** | **−0.058** | **−2.48** | **−0.037** | **−0.077** |
| **LEVELS (sector-neutral)** | **−0.053** | **−3.13** | **−0.024** | **−0.078** |

The *relative* claim replicates cleanly: **levels are reliably negative in both
sub-periods** (and stronger sector-neutral), improvement is consistently
positive in both. Ranking by "how good a company is" is a persistently losing
sort; ranking by "how fast it's improving" is at worst harmless.

**But the absolute claim fails the pre-registered bar.** IMPROVEMENT never
reaches |t| >= 2 (best: 1.85). Per the rule fixed in advance — positive in both
sub-periods but t < 2 — this is **weakly supported, not supported.**

And the tradable version is worse than the IC suggests: the top-decile-minus-
bottom-decile spread for IMPROVEMENT was **+1.6% mean but −1.3% median, 45% hit
rate, and −0.1% in the held-out period** — i.e. **out-of-sample it did nothing.**

## Result 3 — momentum was the only thing that truly replicated (with big caveats)

6-month IC **+0.080 (t 2.88)**, and strikingly stable: **held-out +0.081 vs
tainted +0.080**. Improvement+momentum reached t 3.09 with a 66% hit rate — but
that is momentum carrying it.

Do not get excited. Three reasons this is weaker than it looks:
1. **It is the most documented anomaly in finance** (Jegadeesh-Titman 1993).
   Finding it validates that the pipeline works; it is not a discovery.
2. **Survivorship inflates it.** The universe is the top-600 liquid names *today*,
   so names that survived and compounded are over-represented — exactly the
   population momentum flatters.
3. **The sample excludes momentum's known failure mode.** No 2020 COVID crash,
   no 2009 — momentum's crashes are violent and absent here, so +0.08 is an
   optimistic estimate. With 47 overlapping dates this is ~8 independent
   observations.

## Bottom line

- **Confirmed and useful:** rank by *improvement*, never by *quality level*.
  "How good is this company" is a reliably backwards sort — that result now
  replicates out-of-sample, sector-neutral, across two sub-periods.
- **Not established:** that improvement *predicts* which stocks rise. It is a
  faint positive tilt (IC ~0.015) that produced no out-of-sample decile spread.
- **The methodological win:** pre-registering caught a t-2.68 "finding" that was
  really my own snooping. That is the single most valuable thing this run
  produced, and it is a warning about every backtest that was not pre-registered.

An IC of 0.015-0.08 explains well under 1% of cross-sectional return variance
before costs and turnover. Nothing here changes the project's standing
conclusion: this system is a **research map**, not a stock picker.

*Reproduce: `python scripts/fetch_fundamentals.py 600 && python
scripts/backtest_improvement.py`. Caveats: one 2022-26 window, no crash regime,
current-liquid universe (survivorship-tilted), XBRL tagging imperfect across
sectors (mis-parses dropped, not fed in).*
