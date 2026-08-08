# v2: baselines after skeptic round 1 fixes (iteration folds only)

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

- trials counted for deflation: **7** (this run's models + persisted prior-run ledger)
- folds: 6, total runtime 26s

## Signal tear sheet (all OOS folds, concatenated)

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| lightgbm | -0.0061 | -0.036 | -0.37 | 48% | -0.38 | 6 bps | 0.87 | 378 |
| ridge | -0.0143 | -0.078 | -0.82 | 44% | -0.83 | -28 bps | 0.95 | 378 |
| ensemble | -0.0187 | -0.170 | -1.19 | 48% | -0.54 | -22 bps | 0.88 | 126 |
| momentum_12_1 | -0.0221 | -0.096 | -0.99 | 44% | -0.93 | -24 bps | 0.99 | 378 |

## IC by horizon (days)

| model | 1 | 10 | 21 |
|---|---|---|---|
| lightgbm | 0.0044 | -0.0105 | -0.0129 |
| ridge | 0.0007 | -0.0348 | -0.0574 |
| ensemble | -0.0018 | -0.0247 | -0.0378 |
| momentum_12_1 | -0.0036 | -0.0362 | -0.0502 |

## Backtest — long-short decile, overlapping tranches, net of costs

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| lightgbm | -0.60 | -8.4% | 0.09 | -22.9% | 0.38 | 1 | 0.27 |
| ridge | -1.51 | -21.7% | -0.96 | -33.8% | 0.32 | -17 | 0.13 |
| ensemble | -2.19 | -20.2% | -1.11 | -11.1% | 0.40 | -10 | 0.18 |
| momentum_12_1 | -0.79 | -15.3% | -0.63 | -35.9% | 0.13 | -38 | 0.23 |

### Cost sensitivity (net Sharpe at bps per side)

| model | 0 bps | 5 bps | 10 bps | 25 bps |
|---|---|---|---|---|
| lightgbm | 0.09 | -0.25 | -0.60 | -1.62 |
| ridge | -0.96 | -1.23 | -1.51 | -2.35 |
| ensemble | -1.11 | -1.65 | -2.19 | -3.80 |
| momentum_12_1 | -0.63 | -0.71 | -0.79 | -1.03 |

### Long/short leg decomposition (gross ann. return)

| model | long leg | short leg |
|---|---|---|
| lightgbm | 14.8% | -13.5% |
| ridge | 4.9% | -18.6% |
| ensemble | 13.8% | -24.0% |
| momentum_12_1 | 5.5% | -17.7% |

### Ensemble membership by fold (walk-forward admission)

- fold 1: (none admitted)
- fold 2: lightgbm
- fold 3: lightgbm
- fold 4: lightgbm, ridge
- fold 5: lightgbm, ridge

## Per-year net performance

| model | 2016 | 2017 |
|---|---|---|
| lightgbm | -12%/-0.8 | -26%/-4.1 |
| ridge | -33%/-2.0 | -14%/-1.5 |
| ensemble | — | -20%/-3.1 |
| momentum_12_1 | -35%/-1.6 | 6%/0.5 |
  (cells: ann return / Sharpe)

## Skeptic reports

```
skeptic(lightgbm):
  [WARN] significance: NW t-stat -0.37 < 2 required given 7 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] decay: second-half OOS IC (-0.0318) is less than half of first-half (0.0196) — edge is decaying (Fischer-Krauss pattern).
  [WARN] cost fragility: break-even cost 1 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.27 < 0.95 given 7 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ridge):
  [WARN] significance: NW t-stat -0.82 < 2 required given 7 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -17 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.13 < 0.95 given 7 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ensemble):
  [WARN] significance: NW t-stat -1.19 < 2 required given 7 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -10 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.18 < 0.95 given 7 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(momentum_12_1):
  [WARN] significance: NW t-stat -0.99 < 2 required given 7 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -38 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.23 < 0.95 given 7 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```

## Leakage suite

```json
{
  "tabular_shuffled_ic": -0.0019927303953861893,
  "tabular_shuffled_verdict": "PASS (no train/test row contamination detected)",
  "tabular_canary_ic": 0.9809771401245135,
  "tabular_canary_verdict": "PASS (detector fires on planted leak)",
  "sequence_shuffled_ic": -0.0047032219326492795,
  "sequence_shuffled_verdict": "PASS (no train/test row contamination detected)",
  "sequence_canary_ic": 0.9999999200710789,
  "sequence_canary_verdict": "PASS (window indexing exposes the current row, as designed; detector fires)"
}
```