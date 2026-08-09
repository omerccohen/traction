# Does the FieldWatch mechanism point in the right direction?

A point-in-time backtest of the attention mechanism over the last 2 years.
**Real data only, no lookahead, no LLM** (the desk-note LLM knows the future
from training and cannot be honestly backtested — so this tests the
deterministic engine that feeds it).

## Setup

- Store: 501 S&P names, adjusted daily closes.
- 44 as-of dates, every ~10 trading days, **2024-08-07 → 2026-05-07**.
- At each date: truncate to data ≤ that date, run FieldWatch on 47 fields,
  record attention score + character + regime percentiles. Then measure
  forward outcomes (next 21d / 63d) from the real data.
- 2,068 (date × field) observations. Significance via per-date rank IC with a
  Newey-West t-stat (overlapping windows autocorrelate).

## What was tested, and what the data says

### 1. Does "attention" predict which field goes UP? — **No. (Correct — it never claimed to.)**

| horizon | mean rank IC | NW t | sub-period stability |
|---|---|---|---|
| next 21d | **+0.014** | 0.39 | 1st half −0.05, 2nd half +0.08 (**sign flips**) |
| next 63d | +0.108 | 3.88 | 1st half +0.07, 2nd half +0.15 (**both +, but…**) |

The 21d result is a clean **zero** — attention does not predict next-month
field returns, exactly as the system asserts. The 63d number *looks*
significant, but it fails the project's own skepticism: the forward windows
overlap ~6× (44 dates ≈ **7 effectively-independent quarters**), it sits
entirely inside one 2024–26 bull regime, and it strengthens in the second
half — the signature of a regime artifact, not an edge. **Verdict: the
mechanism does not predict direction, and the apparent long-horizon signal is
not trustworthy.** This *confirms* the system's honesty rather than
contradicting it.

### 2. Does it correctly read persistent REGIME STATE? — **Yes, robustly. (This is its actual job.)**

| signal → forward outcome | mean IC | NW t | 1st half | 2nd half |
|---|---|---|---|---|
| volatility percentile → forward realized vol | **+0.122** | 2.87 | +0.09 | +0.15 |
| dispersion percentile → forward dispersion | **+0.138** | 3.58 | +0.15 | +0.13 |

Both are statistically significant **and stable across both sub-periods**.
When the mechanism flags a field as "volatile" or "in a stock-picker's phase
(high dispersion)," that state genuinely **persists** over the next month.
This is the real, defensible value of an attention allocator: it tells you
*where the action is and whether it's a durable regime* — not where prices go.

### 3. Do the character labels carry information? — **The volatility content is real; the return-direction content is weak.**

Forward behavior by character (demeaned per date = relative to other fields):

| character | n | fwd vol (21d) | fwd return 21d (rel.) | fwd return 63d (rel.) |
|---|---|---|---|---|
| STRESS (falling + high vol) | 195 | **0.33 (highest)** | ~flat | +0.023 |
| MOMENTUM (rising + inflow) | 175 | 0.24 | +0.008 | +0.017 |
| DISPERSION (stock-picker) | 211 | 0.23 | ~flat | +0.020 |
| QUIET (draining/ignored) | 292 | **0.19 (lowest)** | −0.009 | −0.022 |
| VOLATILE | 147 | 0.21 | ~flat | −0.016 |

- **Robust:** STRESS ⇒ highest forward volatility, QUIET ⇒ lowest — the labels
  correctly sort fields by *how turbulent they'll stay* (this is finding #2 in
  disguise, and it's stable).
- **Weak / not robust:** the *return-direction* tilts (QUIET underperforms,
  STRESS/MOMENTUM drift up) do NOT hold across sub-periods — QUIET's
  underperformance was +0.001 in the first half, −0.040 in the second. Do not
  rely on character for direction. (The analyst de-prioritizing a
  QUIET-but-high-score field is still defensible — on the *low-turbulence*
  logic, which is robust — just not as a return call.)

### 4. Field trend-following

Trailing field trend → forward return: 21d IC +0.106 (t 1.9, borderline),
63d +0.064 (t 0.8, not significant). A weak, decaying short-term field-momentum
effect — consistent with the literature, not something to lean on.

## Bottom line

**Does the mechanism point in the right direction?**

- **For price direction — no, and it correctly doesn't pretend to.** Attention →
  next-month return IC ≈ 0.01 (t 0.4) and flips sign across sub-periods. The
  one positive-looking number (63d) fails the stability + overlap tests and is
  a single-regime artifact. The backtest *confirms* the system's core honesty
  claim on its own data.
- **For regime state — yes, robustly.** It reliably identifies fields that will
  stay volatile (t 2.9) and stay dispersed (t 3.6), stable across both halves
  of the 2-year window. That is precisely what an *attention allocator* is
  supposed to deliver: durable "where to look," not "what to buy."

So the mechanism works **for exactly what it claims and refuses to do what it
disclaims** — which, given how the whole project began (killing the "AI that
predicts prices" fantasy), is the right and honest outcome. The desk note's
job — pointing research attention at genuinely unusual, persistent field
activity and asking the right supply-demand question — is validated. Its job is
*not* to call direction, and this test shows why that restraint is correct.

*Caveats: one 2-year window, one broad bull/AI-led regime, 501 current
constituents (survivorship-flagged), ~7 independent quarters at the 63d
horizon. These results describe this sample; they are not a promise about
other regimes. Reproduce with `python scripts/backtest_fieldwatch.py`.*

---

## Broad-universe replication (2,969 stocks, 128 fields) — the verdict holds, and gets *cleaner*

Re-ran the identical test on the full liquid US universe: **2,969 companies,
128 fields, 5,632 (date × field) observations**, same 44 as-of dates. This is a
much harder, more honest test — 2.7× the fields, no S&P survivorship tilt.

| what was tested | S&P (47 fields) | Broad (128 fields) | read |
|---|---|---|---|
| H1 attention → 21d return | IC +0.014, t 0.39 | IC +0.013, **t 0.67** | still a clean **zero** ✓ |
| H1 attention → 63d return | IC +0.108, **t 3.88** | IC +0.027, **t 1.13** | **the "signal" collapsed to noise** |
| H2 vol state → forward vol | IC +0.122, t 2.87 | IC +0.109, **t 4.13** | real job, **stronger** ✓ |
| H2 dispersion → forward disp | IC +0.138, t 3.58 | IC +0.056, t 1.54 | weaker, now marginal |
| H4 trend → 21d return | IC +0.106, t 1.9 | IC +0.070, t 2.43 | weak momentum, consistent |

**The headline:** the one number this doc flagged as *"a single-regime artifact,
not an edge"* (the 63d attention IC, t 3.88 on the S&P set) **fell apart when the
universe broadened — t 3.88 → t 1.13.** Broadening the test *removed a false
signal*, exactly as predicted. Meanwhile the mechanism's actual job —
volatility-regime persistence — got **more** significant (t 2.87 → 4.13). H3
character labels replicate too: STRESS fields carry the highest forward vol
(0.348) and QUIET the lowest (0.233); the return-direction tilts stay tiny.

**Conclusion:** the honest result is not fragile. On 6× the universe it is the
same and better — *cannot predict direction, reliably reads volatility regime.*
Reproduce with `python scripts/backtest_fieldwatch.py` (auto-detects
`data_cache/universe/broad_sectors.csv`).
