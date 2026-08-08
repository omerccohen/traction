# Pre-registration of the final holdout evaluation

Committed BEFORE the holdout lockbox is opened. The holdout is evaluated once;
this document fixes, in advance, what will be run, what counts as evidence,
and what will be said in each outcome — so the conclusion cannot be quietly
fitted to the result (SKEPTIC CHECKLIST #6; round-2 review, angle 6).

## Primary configuration (the only pre-registered claim)

- **Model:** LightGBM (the strongest prior for tabular cross-sections per
  GKX 2020 / Qlib benchmarks, and the least-bad performer across our
  iteration runs).
- **Label:** 5-day forward return, 1-day execution lag (`horizon=5, lag=1`) —
  the original design default. The horizon sweep found no significant
  alternative (all deltas t < 1), so the default stands; switching on those
  numbers would be noise-mining.
- **Features:** the 22 stock + 3 market features in
  `stocklab/features/technical.py` as of this commit.
- **Neutralization:** scores residualized per date against ranked `beta_63`
  (single exposure, fixed here; no exposure-set search happened or will).
- **Portfolio:** decile long-short, overlapping tranches, 10 bps/side.

All other models (momentum, ridge, MLP, LSTM, Transformer, ensemble) are
**secondaries**: reported in full, but no headline claim attaches to them and
no post-hoc promotion of whichever looks best is permitted.

## Decision rule (fixed in advance)

The primary configuration "clears the bar" only if, on the HOLDOUT-ONLY
window (test dates >= 2017-06-01), ALL of:

1. 5d rank IC Newey-West t >= 2 (lags = 2×horizon), AND
2. net Sharpe at 10 bps/side > 0 with break-even cost > 10 bps, AND
3. the result survives the pre-committed sensitivity checks below.

Anything less is reported as **null** — including "positive but below the
bar", which will NOT be narrated as encouraging.

## Power statement (computed before opening)

The holdout holds ~168 trading days. With daily IC sd ≈ 0.20 and NW variance
inflation ≈ 3.6 (measured on the iteration window), se(holdout IC) ≈ 0.029:

- minimum detectable IC at t=2 ≈ **0.058**; at t=3 ≈ 0.088;
- power to confirm a TRUE IC of 0.02 ≈ 9%; of 0.03 ≈ 17%.

Honest daily-equity edges live at IC 0.02-0.05. **This test can catch
leakage-scale artifacts; it cannot confirm an edge of realistic size.** The
likely outcome is null and that is stated here, in advance.

## Pre-committed sensitivity checks (run whatever the outcome)

- Per-month holdout IC, and IC with January-2018 dropped: the data ends
  2018-02-07 — a momentum melt-up peak, immediately before the Feb-2018
  reversal. A result that lives in Jan-2018 alone is regime luck at a
  window boundary and will be labeled as such.
- Drop-top-5-days IC (concentration check).
- 1d-horizon IC profile (a 1d spike is the classic leakage signature).
- Deflated Sharpe against the full trial ledger (36 trials at this commit;
  the final run adds its own).

## What will be said if NULL (the expected case)

> The pre-registered configuration (neutralized LightGBM, 5d horizon) scored
> holdout rank IC = X (NW t = Y), net Sharpe = Z at 10 bps/side, against a
> pre-registered bar of t >= 2. It did not clear the bar. The test's minimum
> detectable IC is ~0.06 — several times larger than honest published
> daily-equity signals — so this run excludes leakage-scale artifacts but can
> neither demonstrate nor exclude an edge of realistic size. Across ~40
> logged trials on 2013-2018 S&P-500 survivors, no model family produced
> evidence distinguishable from a zero-signal system with ~1.5 effective
> independent bets. No trading conclusion follows in either direction —
> in particular, NOT "short the signal".

## What will be said if the bar is cleared

Only: "one 8-month, single-regime, survivorship-biased window cleared t=2
after ~40 trials; classified as suggestive, not a discovery (the t>=3
standard of Harvey-Liu-Zhu is unattainable at this power); pre-registered
replication on fresh post-2018 data is the required next test." Before even
that wording: fresh-seed replication for any deep model involved, leakage
suite re-run on a holdout fold, and the sensitivity checks above must pass.

## Forbidden moves (listed so their absence is checkable)

- Ranking models on holdout differences (se of any pairwise difference over
  168 days exceeds every gap we could observe).
- Annualizing the 8-month window into "X%/yr alpha".
- Converting null into "no edge exists", or sign-flipping a negative result
  into a contrarian strategy.
- Re-opening the holdout after this run (the marker file records any
  violation).
- Retroactive edits to this document (it is in git; the commit predating the
  holdout-opened marker is the binding version).
