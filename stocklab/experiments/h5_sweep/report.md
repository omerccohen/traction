# horizon=5d sweep

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

- trials counted for deflation: **24** (this run's models + persisted prior-run ledger)
- folds: 6, total runtime 37s

## Signal tear sheet (all OOS folds, concatenated)

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| lightgbm | 0.0064 | 0.057 | 0.66 | 52% | 0.49 | 11 bps | 0.85 | 378 |
| ridge | 0.0005 | 0.005 | 0.05 | 47% | -0.47 | -11 bps | 0.94 | 378 |
| ensemble | -0.0026 | -0.025 | -0.18 | 48% | -0.26 | -10 bps | 0.89 | 126 |
| momentum_12_1 | -0.0091 | -0.057 | -0.58 | 49% | -0.62 | 2 bps | 0.99 | 378 |

## IC by horizon (days)

| model | 1 | 10 | 21 |
|---|---|---|---|
| lightgbm | 0.0075 | 0.0093 | 0.0090 |
| ridge | 0.0056 | -0.0083 | -0.0183 |
| ensemble | 0.0021 | 0.0029 | -0.0051 |
| momentum_12_1 | 0.0026 | -0.0188 | -0.0241 |

## Backtest — long-short decile, overlapping tranches, net of costs

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| lightgbm | -0.46 | -4.2% | 0.61 | -16.5% | 0.39 | 6 | 0.22 |
| ridge | -1.35 | -14.2% | -0.56 | -23.2% | 0.33 | -7 | 0.10 |
| ensemble | -1.61 | -14.6% | -0.49 | -7.5% | 0.40 | -4 | 0.20 |
| momentum_12_1 | -0.19 | -2.5% | 0.09 | -18.3% | 0.15 | 3 | 0.26 |

### Cost sensitivity (net Sharpe at bps per side)

| model | 0 bps | 5 bps | 10 bps | 25 bps |
|---|---|---|---|---|
| lightgbm | 0.61 | 0.08 | -0.46 | -2.05 |
| ridge | -0.56 | -0.96 | -1.35 | -2.55 |
| ensemble | -0.49 | -1.05 | -1.61 | -3.29 |
| momentum_12_1 | 0.09 | -0.05 | -0.19 | -0.61 |

### Long/short leg decomposition (gross ann. return)

| model | long leg | short leg |
|---|---|---|
| lightgbm | 15.9% | -10.2% |
| ridge | 9.1% | -15.0% |
| ensemble | 16.4% | -20.8% |
| momentum_12_1 | 10.6% | -9.3% |

### Ensemble membership by fold (walk-forward admission)

- fold 1: ridge
- fold 2: lightgbm
- fold 3: lightgbm
- fold 4: lightgbm, ridge
- fold 5: lightgbm, ridge

## Per-year net performance

| model | 2016 | 2017 |
|---|---|---|
| lightgbm | -7%/-0.8 | -14%/-2.5 |
| ridge | -20%/-1.7 | -9%/-1.2 |
| ensemble | — | -10%/-1.4 |
| momentum_12_1 | -11%/-0.8 | 8%/0.7 |
  (cells: ann return / Sharpe)

## Skeptic reports

```
skeptic(lightgbm):
  [WARN] significance: NW t-stat 0.66 < 3 required given 24 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity 0.49 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] decay: second-half OOS IC (-0.0092) is less than half of first-half (0.0219) — edge is decaying (Fischer-Krauss pattern).
  [WARN] cost fragility: break-even cost 6 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.22 < 0.95 given 24 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ridge):
  [WARN] significance: NW t-stat 0.05 < 3 required given 24 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity -0.47 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] cost fragility: break-even cost -7 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.10 < 0.95 given 24 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ensemble):
  [WARN] significance: NW t-stat -0.18 < 3 required given 24 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -4 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.20 < 0.95 given 24 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(momentum_12_1):
  [WARN] significance: NW t-stat -0.58 < 3 required given 24 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost 3 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.26 < 0.95 given 24 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
