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

---

## Round 2 — adversarial review of the RESULTS (v2/v3/v4 + sweep)

A results-skeptic agent recomputed every headline number independently
(scipy on the raw bundled prices and the shipped score files, no repo metric
code) and attacked the interpretation and the plan. Full transcript summary:

### Verified clean (with receipts)

- **Sign-error hypothesis REFUTED four ways.** A label inversion would leave
  the fit-free momentum baseline untouched while flipping learned models
  (trained on +0.035-IC 2014-15 data they'd have learned ANTI-momentum and
  scored positive in 2016); a return inversion contradicts the raw data; a
  feature inversion would split baseline from learners; a metric inversion
  is excluded by exact independent reproduction (all reported ICs matched
  to 4 decimals). Raw-data yearly momentum ICs: 2014 +0.015, 2015 +0.065,
  **2016 -0.049**, 2017 +0.023, Jan-2018 +0.098 — sign structure varying by
  year cannot come from a global inversion, and 2016 matches the external
  record (worst US momentum year since 2009, Ken French UMD ~ -20%).
- **IC ↔ P&L coherence exact**: Grinold-Kahn arithmetic reproduces the
  backtest gross to within measurement, the cost drag to the decimal
  (0.1256 turnover × 252 × 10 bps = 3.17%/yr), and the hand-computed NW
  t equals the reported one. "t=-0.99 but -35% in 2016" is one fact, not a
  contradiction: one se of IC IS ±12%/yr at this dispersion.
- **"All seven negative" is a P≈0.26 event** under a zero-signal null with
  the measured 0.685 mean pairwise IC correlation (~1.4-1.7 effective
  independent bets; moving-block bootstrap B=20k). It deserves no narrative.
- **mlp-vs-lightgbm ordering is noise** (paired NW t -1.58, sign flips
  across folds; no model distinguishable from the free baseline either).
- Ensemble admission arithmetic, determinism across runs (byte-identical
  score files), forced-exit counts, cost asymmetries: all verified coherent.

### Findings and dispositions

| # | Finding | Disposition |
|---|---|---|
| R2-1 | **NW lags fix recorded in round 1 was in the docs but NOT in the code** (metrics.py still passed lags=horizon). Numeric impact negligible here, but a "verified" fix missing from code is a process failure. | Fixed (lags=2×horizon); full grep audit of all 12 round-1 fixes run — all present. |
| R2-2 | Trial ledger never backfilled v1's pre-ledger trials. | Backfilled +4 (3 models + 1 nominal for the fold-layout change); total 36 before the final run. |
| R2-3 | v3's blanket narrative "deep nets amplified the momentum bet" is half wrong: in the crash quarter itself LightGBM scored +0.092; LightGBM's losses are 2017-concentrated (a decaying 1d effect), a different failure mode. | Narrative corrected here and in the final report. |
| R2-4 | v4 confounds the new features with neutralization (one bundled step). | Accepted as one design step; no ablation trials will be spent (2^4 noise-mining refused). ~60% of the momentum book's 2016 loss was un-hedged beta — v4's improvement is precisely the predicted de-beta effect, and at t=0.66 it is a noise-level positive, not "an edge revealed". |
| R2-5 | Ensemble admission could admit negative-IC members when the baseline was more negative. | Bar raised to max(baseline, 0). |
| R2-6 | Horizon sweep's expected best-of-N under pure noise ≈ +0.014..+0.022 IC — a manufactured winner. | Pre-registered rule applied: no switch without paired NW t≥2 vs h=5 (observed deltas t<1) → **h=5 kept**. |
| R2-7 | Holdout has ~9-17% power to confirm a realistic edge; Jan-2018 is a momentum melt-up ending at the data boundary (Feb-2018 reversal missing). | docs/PREREGISTRATION.md commits the primary config, decision rule, power statement, per-month + drop-Jan-2018 sensitivities, and the exact null/positive wording BEFORE opening the lockbox. |
| R2-8 | Report presentation: ensemble rows cover fewer days than others; edge "years" are calendar fragments. | Annotations added to the report generator. |
| R2-9 | mom_consistency comment said 12 blocks; code (correctly) uses 11. | Comment fixed. |

---

## Round 3 — the pre-registered final run (outcome record)

- Lockbox opened ONCE (`experiments/HOLDOUT_OPENED.json`, one entry).
- Primary (neutralized LightGBM, h=5): holdout IC +0.0230, NW t +1.39,
  net Sharpe −0.64, break-even 3.8 bps → **fails all three pre-registered
  bars → NULL**, reported with the pre-committed wording in FINAL_REPORT.md.
- All pre-committed sensitivities run and clean: no Jan-2018 dependence
  (+0.0241 without it), no concentration (drop-top-5 raises IC), smooth IC
  horizon profile (no 1d leakage spike), leakage suite green on both paths.
- Ridge (secondary) t=2.45: recorded under the pre-registered constraint —
  best-of-7-correlated-rows winner's-curse shape; "suggestive, not a
  discovery"; requires fresh post-2018 replication. NOT promoted.
- Trial ledger final count: 43. The ranking deliverable
  (`experiments/final/ranking.md`) ships bound to the null evidence, with
  the model's honest tie structure surfaced (LightGBM assigns few distinct
  score levels; within-tie order is arbitrary).
- Post-final display fixes (cosmetic, no metrics touched): per-stock
  notable-features exclude market-context columns; tie count stated.

---

## Round 4 — user-hypothesis tests (post-final; holdout stays sealed)

User asked for (a) "the combination of inputs that solves this" and
(b) "news plus sentiment", and authorized a data-sourcing hunt.

### Combination sweep (experiments/combination_sweep)
30 trials over 15 feature-family combinations x {ridge, lightgbm}, noise
expectation pre-declared IN THE SCRIPT (+0.025..+0.035 expected max under
pure noise). Best: VOLA+LIQ lightgbm IC +0.0154 (t 2.15), net Sharpe
-0.23, breakeven 8.4 bps. **Verdict: noise-consistent** — below even the
noise band and fails the economic bar. Live demonstration that combination
search manufactures its own winners.

### Data-sourcing hunt
Blocked: Ken French library, GDELT, Wikimedia pageviews, SEC EDGAR,
HuggingFace, Kaggle, all market-data vendors, GitHub codeload/LFS/release
assets. Reachable: raw.githubusercontent.com only. Found and used:
1. Index-level Reddit r/worldnews top-25 daily headlines 2008-2016
   (Kaggle 'stocknews' mirror), VADER-scored.
2. **Per-stock** news sentiment for 34 mega-caps 2010-2020 (research-repo
   processing of the Kaggle Benzinga headlines; transformer-scored).
   FNSPID confirmed HuggingFace-only.

### Index-level news A/B (experiments/news_sentiment)
Ridge delta exactly 0.000 — structural proof that a per-date-constant
feature cannot re-rank a cross-section. LightGBM delta -0.0101 (more
overfitting room). No value.

### Per-stock news A/B (experiments/perstock_news)
Pre-declared hindsight gate PASSED, and the diagnostics are the finding:
sentiment vs same-day return **+0.091**; vs yesterday's return +0.060;
vs NEXT-5d return **-0.012**. News in mega-caps is contemporaneous and
reactive, not predictive — assimilated the same day, gone by the time
lag-1 execution can trade it (Ke-Kelly-Xiu reproduced in miniature).
Univariate news signal: IC +0.0024 (t 0.14). A/B deltas straddle zero
(ridge -0.0089, lightgbm +0.0039; se of the paired delta > |delta|).
Caveat documented: the 33-name 2020-chosen universe inflates absolute
ICs (BASE ridge +0.041 here vs ~0 on the honest 500-name universe) —
survivorship in miniature; only the within-universe DELTA is meaningful.

Ledger after round 4: **82 trials.**

### Field-level effects (experiments/field_effects) — user hypothesis
"overall sentiment of the specific field (e.g. SanDisk and memory chips)"

Two testable forms, both run on iteration folds, holdout sealed:
- **A. Sector momentum** (355 GICS-mapped names, 11 sectors, leave-one-out
  peer trailing returns): univariate sector-momentum IC **-0.0145**
  (t -1.21) — sector trends mean-reverted in this window (2016 rotations);
  A/B deltas -0.001..-0.006 (worse with the features, inside noise).
- **B. Peer news sentiment** (33 names, leave-one-out field news, semis =
  AMD/NVDA/INTC/QCOM/AVGO/AMAT): univariate peer-news IC **-0.0190**
  (t -1.21); SEMIS-only anecdote (n=6) **-0.0222**; A/B ridge +0.0004,
  lgbm -0.016. The field's news does not predict its members at lag-1.

Literature reconciliation: Moskowitz-Grinblatt industry momentum is a
MONTHLY effect measured on 1963-1995 data and weakened post-publication;
Cohen-Frazzini spillovers concentrate in less-followed small caps. Nulls
in the most-covered mega-caps at 5d horizon confirm, not contradict, the
arbitrage of published effects. SanDisk itself is absent from the panel
(acquired 2016 — deleted by the dataset's survivorship bias).

Ledger after field effects: **90 trials.**

---

## Round 5 — build-phase audits (BUILD_PLAN Phases 1-3, per-phase CR)

Two adversarial reviews of the live-operation build; 15 MAJORs total, all
reproduced by the reviewers before acceptance, all fixed with tests.

### Phase 1 (price feed) — 7 MAJORs fixed
- In-place store rewrite (crash destroys all history) -> atomic tmp+rename.
- No concurrency control (parallel runs clobber silently) -> flock lock.
- Intraday partial prints became immutable "final" closes -> settlement
  window: rows younger than 3 days are replaceable (logged restatements);
  immutability starts at settlement; explicit restate() for history rewrites.
- Adjustment-regime incoherence (yahoo adjclose mixed with raw OHLV; reverse
  splits NEVER healed -> permanent fake +700% days) -> canonical raw prints
  from all sources; split/dividend events captured into a corporate-actions
  table; exact factors applied at load (close AND volume); heuristic
  sanitizer demoted to fallback.
- V-spike validator blind on 1-2 row daily batches -> validates against the
  stored tail; genuine crash-then-bounce days preserved (compounded-move
  condition).
- Stooq full-history downloads per ticker per run + alphabetical starvation
  under hit limits -> bounded d1/d2 fetches, stalest-first ordering,
  abort-after-consecutive-failures, "partial" status.
- CSV-drop path crashed on partial OHLC columns and raw-raised on any error
  -> per-column fill, never raises (reports status=error, logged).
- Plus: future-dated row rejection (a single one permanently defeated the
  freshness guard), close-outside-high/low check, conflict DETAILS logged,
  survivorship marker (backfill_before) in store meta, exit codes that
  distinguish expected idle from real failure.

### Phases 2-3 (briefing + indicators) — 8 MAJORs fixed
- Gitignored sp500_sectors.csv would have silently collapsed every fresh-
  clone briefing from 38 fields to 1 and frozen the update universe -> file
  force-added; gitignore narrowed; missing-file path now prints a loud banner.
- Indicator PIT cache was outside the Routine's commit scope (destroyed
  weekly) -> committed; Routine prompt updated.
- Bundled->live transition produced NaN/degenerate percentiles for months
  -> live store gates at >= 252 trading days with an "accumulating N/252"
  banner until then.
- Cohesion percentile could rest on ONE comparison point (score 1.0 from a
  single number) -> >= 8 non-overlapping history windows required.
- Go-live delta section would have compared 2026 vs 2018 as "movers" ->
  deltas suppressed across source changes, >31d gaps, or membership changes.
- First-print-wins indicator cache made statuses permanently wrong on
  revised FRED series -> vintage log: revisions appended with retrieved_at;
  series() = latest vintage; series_asof() = point-in-time view. The old
  test ENSHRINED the harmful behavior and was rewritten.
- Malformed threshold rules silently evaluated False (a typo = permanently
  disabled alarm shown as OK) -> parse-at-load, loud failure; every
  registered rule test-verified.
- Empty/commented fields.yml crashed the weekly run -> never-raises config
  loading with warning banners.
- Plus: registered_on dates required + rendered (pre-registration
  enforcement), midrank percentiles (flat series no longer p100), UNKNOWN
  state for short-history percentile rules, per-frequency staleness flags,
  per-transform value formatting, semis-PPI trigger re-registered to a
  percentile rule (the absolute one would not have fired in the 2021-22
  shortage it exists to catch), Routine path/rebase fixes, pyyaml declared.

Post-fix: 54/54 tests green; briefing regenerates end-to-end on demo data.
