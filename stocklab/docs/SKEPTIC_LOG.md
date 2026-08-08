# Skeptic Log — critique → fix → re-verify

Every layer of this system gets attacked (by automated tests, by review agents,
and by tripwires in `stocklab.skeptic`). This log records what was found, what
was done about it, and how the fix was verified. Findings are numbered
chronologically; severity: FATAL (invalidates results) / MAJOR / MINOR / NOTE.

---

## Round 0 — self-caught during initial build (pre-review)

### S0-1 [MAJOR] Shuffled-label null was too weak
- **Found by:** `tests/test_pipeline_recovery.py::test_shuffled_labels_collapse`
  failing with IC = 0.18 on the "null".
- **Problem:** the first implementation permuted whole per-date label vectors
  *across dates*, keeping ticker alignment. Per-ticker persistent drift
  survives that shuffle (a stock that trends all sample keeps a mostly-positive
  label at every date), so genuine momentum signal "leaked" into the null and
  the test could never pass — and a real pipeline leak could have hidden inside
  that residual signal.
- **Fix:** permute the ticker assignment *within* each date, independently per
  date (`shuffle_labels_within_dates`) — the correct null for a cross-sectional
  ranker: exact per-date label distribution preserved, feature↔label pairing
  destroyed.
- **Verified:** shuffled-label IC on synthetic = ~0.00; on real data = 0.0012.

### S0-2 [MAJOR] Walk-forward audit measured the gap on the wrong grid
- **Found by:** `tests/test_splits.py::test_audit_passes_and_catches_violation`
  failing on legitimate folds.
- **Problem:** the audit computed "trading days between train end and test
  start" on `train ∪ test` — but the purge/embargo days belong to *neither*
  set, so the audit always saw a zero gap and raised on every valid fold. Had
  the sign of the check been inverted, it would have *passed everything*
  instead — an audit auditing nothing.
- **Fix:** `audit(folds, dates)` now requires the full trading grid and
  measures the gap on it; also asserts train strictly precedes test.
- **Verified:** audit passes valid folds, raises on a forged
  train-touches-test fold.

---

## Round 1 — adversarial review agents on design & code

Three independent review passes attacked (A) data/features/labels/splits,
(B) backtest/statistics, (C) models/runner/experiment design. Both B and C
**verified the core machinery correct by hand-trace and numerical
reproduction** (label timing, purge geometry, sequence-window indexing,
Newey-West, deflated-Sharpe formula, per-side cost accounting) — and then
found real problems at the edges. Every MAJOR was reproduced numerically by
the reviewing agent before being accepted. All fixes verified by the expanded
test suite (26 tests) and a clean re-run (`experiments/v2_baselines_fixed`).

### Accepted and fixed — MAJOR

| # | Finding | Fix |
|---|---|---|
| R1-1 | **Universe filter used full-sample medians — genuine lookahead.** AMD (full-sample median $3.85) was deleted from the whole sample including 2016-18 when it traded >$10; CHK stayed shortable through its 2016 collapse because its full-sample median was fine. Both directions decided by the future. | `eligibility_mask` now applies **trailing** 63d median price/dollar-volume screens point-in-time; `apply_universe_filters` only drops never-eligible tickers (pure column hygiene). PIT test with liquidity filters added. |
| R1-2 | **Ensemble membership was selected on the same OOS data the ensemble was then graded on** (winner's curse at the meta level; "beat the baseline" ≈ "IC>0" ≈ coin flip for noise). | Walk-forward admission: membership for fold k decided only on folds < k; fold 0 has no ensemble. Membership per fold reported. |
| R1-3 | **Trailing dead-capital never trimmed**: scores ending before the price panel left years of flat zeros in every statistic (Sharpe diluted ~sqrt(active fraction), DSR n_obs inflated, ghost years). Direction "conservative", magnitude wrong. | Engine trims to [first, last] active day and charges the terminal unwind on the last day (symmetric with the initial build). Test added. |
| R1-4 | **NaN closes while held earned exactly 0%** — an engine-level survivorship subsidy (delisting losses on longs and gains on shorts silently erased). | Names with no printed close are force-exited (exit cost charged), re-entered when trading resumes; `forced_exit_days` reported and surfaced by the skeptic. Test added. |
| R1-5 | **Boundary ties could empty a leg** (average-rank buckets move tie groups en bloc; tree models tie routinely) → silent one-sided book violating the dollar-neutral claim. | Ordinal ranks (`method='first'`), exactly n//q names per leg, plus a neutrality-violation counter. Test with a 25-way tie added. |
| R1-6 | **IC tripwires miscalibrated by horizon**: literature ranges are ~1d-label ICs; a 5d-label IC is ~sqrt(5) larger, so honest signals tripped the leakage alarm and a genuinely leaky 1d signal would have passed. | Thresholds scale by sqrt(horizon); the skeptic prefers the 1d-horizon IC (directly comparable to the literature) when available. |
| R1-7 | **Corrupt corporate-action rows in the bundled data**: un-adjusted spin-off distributions printed as -44% to -63% price days (BAX, DISCA/K, EBAY, NI) and one mis-adjusted split (LNT -49% then +101%). Fake returns entered labels, features and the backtest. | `sanitize_corporate_actions`: reversal pairs respliced; negative steps back-adjusted like split factors (event day -> 0%); positive moves untouched (VRTX +62% is real). All 6 repairs logged into the bias disclosure. Tests added. |
| R1-8 | **Timing test could not catch same-close execution** (the classic bug): zeros asserted one day short, and a `shift(lag)` engine passed. | Test pinned from both sides: zero through signal+lag, nonzero at signal+lag+1. |
| R1-9 | **Lockbox produced no observable holdout number**: the final run concatenated holdout + iterated folds into one tear sheet, and nothing recorded that the holdout was opened. | Final runs emit a HOLDOUT-ONLY section (the headline); `HOLDOUT_OPENED.json` marker warns loudly on any second opening. |
| R1-10 | **Leakage suite never tested the sequence path** (the only code doing manual index arithmetic) and picked its fold ignoring the lockbox. | Suite now runs shuffled-label + canary on flattened SequenceStore windows too (canary = rank of future return as an extra feature plane; fires at IC 0.9999) and selects a pre-holdout fold. |
| R1-11 | **Shuffled-label verdict over-claimed**: the within-date shuffle destroys feature→label links including leaked ones, so it detects train/test row contamination — NOT lookahead features. Reviewer proved a planted future-return feature gets "PASS". | Verdict reworded to what it actually tests; feature lookahead is owned by the dataset-level point-in-time test (new, staggered-NaN panel, multiple dates). |
| R1-12 | **Bundled closes are split- but not dividend-adjusted** → labels are price returns with a small systematic anti-yield tilt. Not fixable offline. | Added to `BUNDLED_BIASES` with the same prominence as survivorship; ships with every report. |
| R1-13 | **Ensemble weighted branch shrank partial-coverage rows toward zero** (fixed divisor over missing members) and accepted zero-sum weights. | Per-row renormalization over present members; non-negative-weights guard; unknown member names now raise. |
| R1-14 | **`load_csv` crashed on yfinance-style CSVs** (Close + Adj Close both aliased to `close` → duplicate columns → pivot error). | Adjusted close preferred with the raw column dropped (and said so); ambiguous columns raise. |

### Accepted and fixed — MINOR (selection)

- Purge off-by-one forfeited one training day per fold (safe direction) — reclaimed.
- Synthetic generator printed **tomorrow's** |return| in today's volume (leak-adjacent for any future volume feature) — lagged.
- Training-target ranks were computed over ALL names including not-yet-eligible listings while features saw only eligible ones — target now ranked within the eligible universe.
- `cross_sectional_rank` range was asymmetric ([-1+2/n, +1], mean +1/n, drifting with universe size) — now symmetric [-1, +1].
- DSR treated overlapping daily returns as independent (`n_obs` ~5x optimistic — the deflation tool itself was optimistic) — effective n = n/horizon; trial-Sharpe spread now excludes the ensemble.
- NW lags = horizon under-covered persistent-signal IC autocorrelation — now 2*horizon.
- Trial ledger (`experiments/trial_ledger.json`) accumulates every run's model count as the DSR prior — iteration can no longer forget its own search history.
- Cost test was circular (verified the engine against its own identity) — replaced with a hand-computed scripted lifecycle (build 2.0 / flip 4.0 / unwind 2.0).
- SequenceStore cache keyed on nothing (stale features if factories reused across datasets); empty-batch paths; float32 double-copies — all fixed.
- Silent cross-fold dedup replaced with a hard assertion; degenerate train/val split guard; validation stride 1; pandas>=3.0 pinned (2.x pct_change padding fabricates 0.0 returns after gaps); blanket FutureWarning suppression removed.
- IC tear sheet and quantile panel now share one min-names date filter (they described different universes).
- Short-leg-dependence flag mislabeled a money-LOSING short leg as the alpha source (|abs| attribution) — now conditions on a profitable short leg.

### Reviewed and NOT changed (rejected or accepted-as-documented)

- **Per-date cross-sectional label ranking uses other stocks' future returns at the same date** — that is the definition of a cross-sectional target, fully covered by the purge; evaluation uses raw returns. No leak (confirmed by reviewer A's N4 walkthrough).
- **Early stopping on the last block of train dates** — the val block's labels are fully realized before the test window at simulated decision time; a production system could do exactly this. Kept (shared-adaptivity cost absorbed into trial accounting).
- **Sequence windows reaching back into train-period FEATURES** — features are observable history; only label windows must respect the boundary (they do).
- **Returns quoted on single-leg notional (gross 2.0)** — standard academic convention; now documented in the engine docstring rather than changed.
- **`min_child_samples=200` etc.** — conservative-by-design; early stopping governs capacity (reviewer C measured fold-0 stop at 60 of 400 trees).

### Post-fix verification

- 26/26 tests pass (was 18), including the new both-sides timing pin,
  scripted turnover, tie neutrality, forced exits, dataset-level PIT on
  staggered listings, and sanitizer behavior.
- `experiments/v2_baselines_fixed`: leakage suite green on both paths
  (tabular shuffled -0.002 / canary 0.981; sequence shuffled -0.005 /
  canary 1.000). Baselines on the iteration window remain honestly null
  (momentum -0.022, ridge -0.014, LightGBM -0.006) — early 2016 was a
  momentum crash and the pipeline reports it as such.
