# Can you rank stocks by "best positioned" and predict which rise? — Point-in-time test

**Short answer: no.** Ranking a 592-name liquid universe by real, point-in-time
fundamentals ("who's best positioned to solve the thesis") did **not** point to
the stocks that rose. If anything it pointed mildly to the *laggards*. The only
thing with a weak positive edge was plain price momentum — and it's not robust.

This is the honest, backtestable stand-in for the LLM deep-research ranker. The
LLM ranker **cannot** be backtested — it and its web searches already know how
the story ended, so pointing it at 2024 bakes in hindsight. So this tests the
*measurable* core of what it rewards — revenue growth, margins, margin trend,
low leverage — computed **strictly from filings filed on/before each as-of
date**, plus momentum for reference.

## Setup (real data, no lookahead)

- **Universe:** 592 most-liquid US names (median >$150M/day), the ones a desk
  could actually trade. Fundamentals from SEC EDGAR XBRL, each data point kept
  with its **filing date** so features use only what was public at the time.
- **Grid:** 25 monthly as-of dates, **2024-01 → 2026-01**, ~512 names each.
- **Signals per name per date (all point-in-time):** revenue growth YoY, operating
  margin, margin change, leverage; a `fundamental` composite of those; 6-month
  price momentum; a `combined` (fundamental + momentum).
- **Test:** cross-sectional rank-IC of each signal vs forward 63-day (3m) and
  126-day (6m) return, Newey-West t (overlap-robust); plus the top-decile-minus-
  bottom-decile forward return and how often the top actually beat the bottom.

## What the data says

### 1. The fundamental "positioning" ranking did NOT predict winners — the opposite, mildly.

| horizon | fundamental composite IC | NW t | top-decile beat bottom-decile |
|---|---|---|---|
| 3 months | **−0.031** | **−2.27** | only **28%** of months |
| 6 months | −0.029 | −1.74 | only **32%** of months |

The composite's IC is **zero-to-slightly-negative** — and the intuitive number
is the hit rate: the "best-fundamentals" decile beat the "worst" decile in only
**28–32% of months**, i.e. most of the time the *cheaper/lower-quality* names won.
That's the classic **value effect**: high-growth, high-margin, low-leverage names
are already richly priced, so they mean-revert. Being demonstrably well-run is
**already in the price**.

### 2. The only positive edge was price momentum — weak, one-horizon, regime-flavored.

| signal | 6-month IC | NW t |
|---|---|---|
| **momentum only** | **+0.077** | **+2.31** |
| revenue growth only | +0.036 | 0.93 |
| margin only | −0.064 | −1.72 |
| low-leverage only | −0.043 | −1.23 |

Momentum is the lone signal with a real positive 6-month IC (t 2.3). But by this
project's own skeptic standard it is **not** trustworthy: it's **~0 at 3 months**
(+0.015, t 0.4), stronger in the second half (a 2024–26 momentum/AI regime), and
rests on ~25 overlapping windows (~4–5 independent). A single one-regime t≈2.3 is
exactly the kind of number the FieldWatch backtest watched evaporate when
stressed. Margin and low-leverage were **negative** — rich, safe names lagged in
a risk-on tape.

### 3. The combined signal looks tempting but isn't robust.

Top-decile-minus-bottom-decile of `fundamental+momentum` was **+15.2% over 6
months (64% of months)** — but t 1.89, and it's carried entirely by momentum, not
by the fundamental "positioning" it was supposed to test. Not a dependable edge.

## Bottom line

**Ranking by "best positioned to solve the thesis" does not forecast which
stocks rise.** The mechanical proxy of that ranking had ~zero (slightly negative)
forward correlation; the top-ranked names beat the bottom in under a third of
months. Only momentum showed a faint, non-robust, horizon-specific pulse.

This is not a failure of the deep-research ranker — it is the ranker being
**correct and useless for timing at the same time**. PWR really does have the
biggest data-center backlog; ARCC really is the most diversified book. But those
facts are **public**, so the market has already priced them. *Best-positioned ≠
about-to-rise.*

It lands exactly where every other honest test in this project landed: the
system is real value for **understanding where to look and who is exposed** — a
research map — and has **no reliable power to call which names go up**. Anyone
who tells you a fundamental screen reliably picks the winners in liquid US
stocks is selling something.

*Caveats: one 2-year window, one broadly risk-on/AI regime; ~512 current-liquid
names (survivorship-tilted); XBRL fundamentals are imperfectly tagged across
sectors (mis-parses dropped, not fed in). Reproduce: `python
scripts/fetch_fundamentals.py 600 && python scripts/backtest_positioning.py`.*
