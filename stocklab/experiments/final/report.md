# FINAL: pre-registered holdout evaluation (neutralized, full ladder)

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

- trials counted for deflation: **43** (this run's models + persisted prior-run ledger)
- folds: 9, total runtime 4555s

## HOLDOUT-ONLY (test >= 2017-06-01) — the only numbers never iterated on

Every development decision was made on the pre-holdout folds; this
section is the sole out-of-sample-of-the-process evidence.

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| ridge | 0.0408 | 0.381 | 2.45 | 64% | 0.96 | 43 bps | 0.93 | 168 |
| mlp | 0.0349 | 0.275 | 1.89 | 65% | 0.93 | 39 bps | 0.85 | 168 |
| momentum_12_1 | 0.0344 | 0.171 | 1.25 | 58% | 0.73 | 8 bps | 0.99 | 168 |
| lightgbm | 0.0230 | 0.197 | 1.39 | 62% | 0.77 | 8 bps | 0.81 | 168 |
| lstm | 0.0184 | 0.162 | 0.99 | 57% | 0.87 | 23 bps | 0.91 | 168 |
| transformer | 0.0053 | 0.061 | 0.39 | 50% | 0.04 | 13 bps | 0.99 | 168 |
| ensemble | 0.0004 | 0.004 | 0.02 | 61% | -0.27 | -9 bps | 0.92 | 59 |

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| ridge | 1.44 | 11.6% | 2.66 | -5.6% | 0.39 | 22 | nan |
| mlp | 0.87 | 8.2% | 2.03 | -6.7% | 0.43 | 18 | nan |
| momentum_12_1 | -0.03 | -0.5% | 0.20 | -11.5% | 0.16 | 9 | nan |
| lightgbm | -0.64 | -6.4% | 0.39 | -10.8% | 0.41 | 4 | nan |
| lstm | -0.04 | -0.3% | 1.29 | -8.4% | 0.44 | 10 | nan |
| transformer | 0.02 | 0.1% | 1.05 | -6.6% | 0.23 | 10 | nan |
| ensemble | -1.10 | -12.5% | -0.32 | -6.1% | 0.35 | -4 | nan |

## Signal tear sheet (all OOS folds, concatenated)

*Includes the pre-holdout folds that development iterated on — read the
holdout-only section above for the untouched estimate.*

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| lightgbm | 0.0125 | 0.110 | 1.49 | 56% | 0.89 | 11 bps | 0.83 | 563 |
| ridge | 0.0122 | 0.109 | 1.31 | 52% | 0.79 | 5 bps | 0.93 | 563 |
| mlp | 0.0118 | 0.102 | 1.22 | 54% | 0.92 | 9 bps | 0.82 | 563 |
| momentum_12_1 | 0.0087 | 0.050 | 0.61 | 53% | -0.05 | 10 bps | 0.99 | 563 |
| ensemble | 0.0004 | 0.004 | 0.02 | 61% | -0.27 | -9 bps | 0.92 | 59 |
| lstm | -0.0011 | -0.010 | -0.12 | 50% | -0.58 | -7 bps | 0.93 | 563 |
| transformer | -0.0038 | -0.032 | -0.40 | 48% | -0.79 | -2 bps | 0.99 | 563 |

*Rows are NOT all on the same window: the ensemble starts at fold 1 (walk-forward admission needs prior-fold evidence) and sequence models lose a lookback warm-up — compare via the `n days` column, and only compare models pairwise on their overlapping days.*

## IC by horizon (days)

| model | 1 | 10 | 21 |
|---|---|---|---|
| lightgbm | 0.0107 | 0.0166 | 0.0172 |
| ridge | 0.0119 | 0.0063 | 0.0004 |
| mlp | 0.0119 | 0.0121 | 0.0154 |
| momentum_12_1 | 0.0122 | 0.0042 | 0.0024 |
| ensemble | 0.0101 | -0.0164 | -0.0472 |
| lstm | 0.0051 | -0.0020 | 0.0033 |
| transformer | 0.0025 | -0.0099 | -0.0149 |

## Backtest — long-short decile, overlapping tranches, net of costs

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| lightgbm | -0.47 | -4.5% | 0.59 | -20.3% | 0.40 | 6 | 0.18 |
| ridge | -0.62 | -6.1% | 0.28 | -23.9% | 0.35 | 3 | 0.15 |
| mlp | -0.72 | -6.7% | 0.48 | -25.6% | 0.45 | 4 | 0.14 |
| momentum_12_1 | 0.09 | 1.4% | 0.34 | -18.3% | 0.15 | 14 | 0.30 |
| ensemble | -1.10 | -12.5% | -0.32 | -6.1% | 0.35 | -4 | nan |
| lstm | -1.28 | -13.8% | -0.35 | -37.1% | 0.40 | -4 | 0.07 |
| transformer | -0.70 | -6.6% | -0.15 | -21.2% | 0.21 | -3 | 0.14 |

### Cost sensitivity (net Sharpe at bps per side)

| model | 0 bps | 5 bps | 10 bps | 25 bps |
|---|---|---|---|---|
| lightgbm | 0.59 | 0.06 | -0.47 | -2.06 |
| ridge | 0.28 | -0.17 | -0.62 | -1.98 |
| mlp | 0.48 | -0.12 | -0.72 | -2.51 |
| momentum_12_1 | 0.34 | 0.22 | 0.09 | -0.28 |
| ensemble | -0.32 | -0.71 | -1.10 | -2.27 |
| lstm | -0.35 | -0.82 | -1.28 | -2.69 |
| transformer | -0.15 | -0.43 | -0.70 | -1.51 |

### Long/short leg decomposition (gross ann. return)

| model | long leg | short leg |
|---|---|---|
| lightgbm | 15.9% | -10.3% |
| ridge | 14.4% | -11.7% |
| mlp | 16.0% | -11.5% |
| momentum_12_1 | 13.9% | -8.8% |
| ensemble | 21.7% | -25.3% |
| lstm | 12.2% | -15.9% |
| transformer | 10.9% | -12.4% |

### Ensemble membership by fold (walk-forward admission)

- fold 1: ridge
- fold 2: lightgbm
- fold 3: lightgbm
- fold 4: (none admitted)
- fold 5: (none admitted)
- fold 6: (none admitted)
- fold 7: (none admitted)
- fold 8: lightgbm, mlp, ridge

## Per-year net performance

| model | 2016 | 2017 |
|---|---|---|
| lightgbm | -7%/-0.8 | -7%/-0.8 |
| ridge | -20%/-1.7 | 3%/0.3 |
| mlp | -22%/-2.2 | 3%/0.3 |
| momentum_12_1 | -11%/-0.8 | 5%/0.3 |
| ensemble | — | — |
| lstm | -29%/-2.3 | -7%/-0.9 |
| transformer | -14%/-1.2 | 0%/0.1 |
  (cells: ann return / Sharpe; edge years are CALENDAR-YEAR FRAGMENTS clipped to the OOS window, and stubs under 40 days are omitted)

## Skeptic reports

```
skeptic(lightgbm):
  [WARN] significance: NW t-stat 1.49 < 3 required given 43 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost 6 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.18 < 0.95 given 43 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ridge):
  [WARN] significance: NW t-stat 1.31 < 3 required given 43 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost 3 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.15 < 0.95 given 43 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(mlp):
  [WARN] significance: NW t-stat 1.22 < 3 required given 43 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost 4 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.14 < 0.95 given 43 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(momentum_12_1):
  [WARN] significance: NW t-stat 0.61 < 3 required given 43 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity -0.05 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] cost fragility: break-even cost 14 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.30 < 0.95 given 43 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ensemble):
  [WARN] significance: NW t-stat 0.02 < 3 required given 43 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity -0.27 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] cost fragility: break-even cost -4 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [NOTE] baseline: does not beat momentum baseline IC (0.0087); per design rules this model is not admitted to the ensemble.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(lstm):
  [WARN] significance: NW t-stat -0.12 < 3 required given 43 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -4 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.07 < 0.95 given 43 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] baseline: does not beat momentum baseline IC (0.0087); per design rules this model is not admitted to the ensemble.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(transformer):
  [WARN] significance: NW t-stat -0.40 < 3 required given 43 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -3 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.14 < 0.95 given 43 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] baseline: does not beat momentum baseline IC (0.0087); per design rules this model is not admitted to the ensemble.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```

## Leakage suite

```json
{
  "tabular_shuffled_ic": -0.003564588632355059,
  "tabular_shuffled_verdict": "PASS (no train/test row contamination detected)",
  "tabular_canary_ic": 0.980994452484759,
  "tabular_canary_verdict": "PASS (detector fires on planted leak)",
  "sequence_shuffled_ic": -0.0047032219326492795,
  "sequence_shuffled_verdict": "PASS (no train/test row contamination detected)",
  "sequence_canary_ic": 0.9999999200710789,
  "sequence_canary_verdict": "PASS (window indexing exposes the current row, as designed; detector fires)"
}
```