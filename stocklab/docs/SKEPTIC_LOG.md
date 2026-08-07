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

(Findings from three independent review passes — data/features/labels/splits,
backtest/statistics, models/runner/experiment design — are recorded here as
they are adjudicated. Each accepted finding links to its fix commit; rejected
findings are kept with the reason, because a rejected critique is evidence the
check happened.)

*Pending: agents running.*
