# horizon=1d sweep

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

- trials counted for deflation: **20** (this run's models + persisted prior-run ledger)
- folds: 6, total runtime 29s

## Signal tear sheet (all OOS folds, concatenated)

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| ridge | 0.0071 | 0.053 | 1.07 | 53% | -0.05 | -1 bps | 0.92 | 378 |
| momentum_12_1 | 0.0022 | 0.013 | 0.26 | 52% | -0.36 | 2 bps | 0.99 | 378 |
| lightgbm | 0.0005 | 0.004 | 0.07 | 49% | -0.18 | -6 bps | 0.66 | 378 |
| ensemble | -0.0016 | -0.014 | -0.18 | 49% | -0.25 | -7 bps | 0.81 | 126 |

## IC by horizon (days)

| model | 1 | 10 | 21 |
|---|---|---|---|
| ridge | 0.0071 | 0.0006 | -0.0034 |
| momentum_12_1 | 0.0022 | -0.0184 | -0.0241 |
| lightgbm | 0.0005 | -0.0008 | -0.0023 |
| ensemble | -0.0016 | -0.0005 | 0.0025 |

## Backtest — long-short decile, overlapping tranches, net of costs

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| ridge | -2.35 | -26.2% | -0.10 | -34.5% | 1.00 | -0 | 0.00 |
| momentum_12_1 | -0.31 | -4.4% | 0.28 | -20.7% | 0.33 | 5 | 0.00 |
| lightgbm | -4.25 | -51.4% | -1.28 | -55.5% | 1.43 | -4 | 0.00 |
| ensemble | -4.17 | -27.2% | -1.54 | -24.1% | 0.69 | -6 | 0.00 |

### Cost sensitivity (net Sharpe at bps per side)

| model | 0 bps | 5 bps | 10 bps | 25 bps |
|---|---|---|---|---|
| ridge | -0.10 | -1.22 | -2.35 | -5.72 |
| momentum_12_1 | 0.28 | -0.01 | -0.31 | -1.19 |
| lightgbm | -1.28 | -2.78 | -4.25 | -8.25 |
| ensemble | -1.54 | -2.90 | -4.17 | -7.27 |

### Long/short leg decomposition (gross ann. return)

| model | long leg | short leg |
|---|---|---|
| ridge | 9.1% | -10.2% |
| momentum_12_1 | 10.7% | -6.6% |
| lightgbm | 2.8% | -18.1% |
| ensemble | 1.2% | -11.0% |

### Ensemble membership by fold (walk-forward admission)

- fold 1: (none admitted)
- fold 2: lightgbm, ridge
- fold 3: (none admitted)
- fold 4: ridge
- fold 5: lightgbm, ridge

## Per-year net performance

| model | 2015 | 2016 | 2017 |
|---|---|---|---|
| ridge | -13%/-1.3 | -28%/-2.4 | -27%/-2.9 |
| momentum_12_1 | 32%/1.7 | -14%/-1.0 | 6%/0.6 |
| lightgbm | 1%/0.1 | -58%/-4.5 | -59%/-6.3 |
| ensemble | — | -23%/-4.0 | -37%/-4.6 |
  (cells: ann return / Sharpe)

## Skeptic reports

```
skeptic(ridge):
  [WARN] significance: NW t-stat 1.07 < 3 required given 20 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity -0.05 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] cost fragility: break-even cost -0 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.00 < 0.95 given 20 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(momentum_12_1):
  [WARN] significance: NW t-stat 0.26 < 3 required given 20 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity -0.36 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] decay: second-half OOS IC (0.0010) is less than half of first-half (0.0035) — edge is decaying (Fischer-Krauss pattern).
  [WARN] cost fragility: break-even cost 5 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.00 < 0.95 given 20 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(lightgbm):
  [WARN] significance: NW t-stat 0.07 < 3 required given 20 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity -0.18 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] decay: second-half OOS IC (-0.0037) is less than half of first-half (0.0046) — edge is decaying (Fischer-Krauss pattern).
  [WARN] cost fragility: break-even cost -4 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.00 < 0.95 given 20 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] baseline: does not beat momentum baseline IC (0.0022); per design rules this model is not admitted to the ensemble.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ensemble):
  [WARN] significance: NW t-stat -0.18 < 3 required given 20 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -6 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.00 < 0.95 given 20 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] baseline: does not beat momentum baseline IC (0.0022); per design rules this model is not admitted to the ensemble.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
