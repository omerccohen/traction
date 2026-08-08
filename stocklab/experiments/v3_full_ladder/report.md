# v3: full model ladder after skeptic round 1 (iteration folds)

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

- trials counted for deflation: **11** (this run's models + persisted prior-run ledger)
- folds: 6, total runtime 2491s

## Signal tear sheet (all OOS folds, concatenated)

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| lightgbm | -0.0061 | -0.036 | -0.37 | 48% | -0.38 | 6 bps | 0.87 | 378 |
| ridge | -0.0143 | -0.078 | -0.82 | 44% | -0.83 | -28 bps | 0.95 | 378 |
| ensemble | -0.0190 | -0.163 | -1.17 | 42% | -0.67 | -22 bps | 0.93 | 126 |
| momentum_12_1 | -0.0221 | -0.096 | -0.99 | 44% | -0.93 | -24 bps | 0.99 | 378 |
| transformer | -0.0224 | -0.120 | -1.24 | 43% | -0.87 | -35 bps | 0.99 | 378 |
| lstm | -0.0254 | -0.152 | -1.62 | 45% | -0.93 | -38 bps | 0.94 | 378 |
| mlp | -0.0288 | -0.165 | -1.72 | 43% | -0.99 | -35 bps | 0.84 | 378 |

## IC by horizon (days)

| model | 1 | 10 | 21 |
|---|---|---|---|
| lightgbm | 0.0044 | -0.0105 | -0.0129 |
| ridge | 0.0007 | -0.0348 | -0.0574 |
| ensemble | -0.0006 | -0.0260 | -0.0368 |
| momentum_12_1 | -0.0036 | -0.0362 | -0.0502 |
| transformer | -0.0047 | -0.0358 | -0.0465 |
| lstm | -0.0072 | -0.0389 | -0.0390 |
| mlp | -0.0064 | -0.0359 | -0.0307 |

## Backtest — long-short decile, overlapping tranches, net of costs

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| lightgbm | -0.60 | -8.4% | 0.09 | -22.9% | 0.38 | 1 | 0.21 |
| ridge | -1.51 | -21.7% | -0.96 | -33.8% | 0.32 | -17 | 0.10 |
| ensemble | -2.02 | -19.5% | -1.08 | -10.8% | 0.36 | -12 | 0.17 |
| momentum_12_1 | -0.79 | -15.3% | -0.63 | -35.9% | 0.13 | -38 | 0.18 |
| transformer | -1.59 | -22.4% | -1.25 | -34.2% | 0.19 | -37 | 0.09 |
| lstm | -1.87 | -28.3% | -1.27 | -42.7% | 0.36 | -21 | 0.07 |
| mlp | -2.10 | -28.8% | -1.27 | -40.0% | 0.45 | -15 | 0.06 |

### Cost sensitivity (net Sharpe at bps per side)

| model | 0 bps | 5 bps | 10 bps | 25 bps |
|---|---|---|---|---|
| lightgbm | 0.09 | -0.25 | -0.60 | -1.62 |
| ridge | -0.96 | -1.23 | -1.51 | -2.35 |
| ensemble | -1.08 | -1.55 | -2.02 | -3.42 |
| momentum_12_1 | -0.63 | -0.71 | -0.79 | -1.03 |
| transformer | -1.25 | -1.42 | -1.59 | -2.10 |
| lstm | -1.27 | -1.57 | -1.87 | -2.78 |
| mlp | -1.27 | -1.68 | -2.10 | -3.35 |

### Long/short leg decomposition (gross ann. return)

| model | long leg | short leg |
|---|---|---|
| lightgbm | 14.8% | -13.5% |
| ridge | 4.9% | -18.6% |
| ensemble | 15.5% | -26.0% |
| momentum_12_1 | 5.5% | -17.7% |
| transformer | 2.0% | -19.6% |
| lstm | 2.2% | -21.4% |
| mlp | 5.6% | -23.0% |

### Ensemble membership by fold (walk-forward admission)

- fold 1: (none admitted)
- fold 2: lightgbm
- fold 3: lightgbm
- fold 4: lightgbm, ridge
- fold 5: lightgbm, lstm, ridge, transformer

## Per-year net performance

| model | 2016 | 2017 |
|---|---|---|
| lightgbm | -12%/-0.8 | -26%/-4.1 |
| ridge | -33%/-2.0 | -14%/-1.5 |
| ensemble | — | -19%/-2.7 |
| momentum_12_1 | -35%/-1.6 | 6%/0.5 |
| transformer | -33%/-2.1 | -10%/-1.3 |
| lstm | -44%/-2.6 | -18%/-2.3 |
| mlp | -40%/-2.5 | -14%/-2.0 |
  (cells: ann return / Sharpe)

## Skeptic reports

```
skeptic(lightgbm):
  [WARN] significance: NW t-stat -0.37 < 3 required given 11 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] decay: second-half OOS IC (-0.0318) is less than half of first-half (0.0196) — edge is decaying (Fischer-Krauss pattern).
  [WARN] cost fragility: break-even cost 1 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.21 < 0.95 given 11 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ridge):
  [WARN] significance: NW t-stat -0.82 < 3 required given 11 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -17 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.10 < 0.95 given 11 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ensemble):
  [WARN] significance: NW t-stat -1.17 < 3 required given 11 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -12 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.17 < 0.95 given 11 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(momentum_12_1):
  [WARN] significance: NW t-stat -0.99 < 3 required given 11 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -38 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.18 < 0.95 given 11 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(transformer):
  [WARN] significance: NW t-stat -1.24 < 3 required given 11 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -37 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.09 < 0.95 given 11 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] baseline: does not beat momentum baseline IC (-0.0221); per design rules this model is not admitted to the ensemble.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(lstm):
  [WARN] significance: NW t-stat -1.62 < 3 required given 11 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -21 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.07 < 0.95 given 11 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] baseline: does not beat momentum baseline IC (-0.0221); per design rules this model is not admitted to the ensemble.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(mlp):
  [WARN] significance: NW t-stat -1.72 < 3 required given 11 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -15 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.06 < 0.95 given 11 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] baseline: does not beat momentum baseline IC (-0.0221); per design rules this model is not admitted to the ensemble.
  [NOTE] forced exits: 2 held-name days had missing prices (forced liquidation at last close; delisting returns not modeled).
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