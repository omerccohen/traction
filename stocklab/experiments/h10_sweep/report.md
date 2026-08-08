# horizon=10d sweep

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

- trials counted for deflation: **28** (this run's models + persisted prior-run ledger)
- folds: 6, total runtime 29s

## Signal tear sheet (all OOS folds, concatenated)

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| lightgbm | 0.0067 | 0.063 | 0.50 | 52% | 0.59 | 11 bps | 0.86 | 378 |
| ensemble | 0.0005 | 0.006 | 0.03 | 52% | -0.02 | 26 bps | 0.91 | 126 |
| ridge | -0.0091 | -0.087 | -0.68 | 43% | -0.62 | -29 bps | 0.94 | 378 |
| momentum_12_1 | -0.0180 | -0.113 | -0.89 | 44% | -0.54 | 9 bps | 0.99 | 378 |

## IC by horizon (days)

| model | 1 | 10 | 21 |
|---|---|---|---|
| lightgbm | 0.0031 | 0.0067 | 0.0156 |
| ensemble | 0.0077 | 0.0005 | 0.0111 |
| ridge | 0.0036 | -0.0091 | -0.0197 |
| momentum_12_1 | 0.0031 | -0.0180 | -0.0262 |

## Backtest — long-short decile, overlapping tranches, net of costs

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| lightgbm | -0.36 | -3.3% | 0.33 | -13.6% | 0.25 | 5 | 0.28 |
| ensemble | 0.01 | 0.1% | 0.89 | -4.9% | 0.24 | 10 | nan |
| ridge | -1.35 | -12.7% | -0.74 | -20.6% | 0.23 | -12 | 0.17 |
| momentum_12_1 | -0.02 | -0.3% | 0.18 | -18.0% | 0.11 | 9 | 0.33 |

### Cost sensitivity (net Sharpe at bps per side)

| model | 0 bps | 5 bps | 10 bps | 25 bps |
|---|---|---|---|---|
| lightgbm | 0.33 | -0.01 | -0.36 | -1.39 |
| ensemble | 0.89 | 0.45 | 0.01 | -1.32 |
| ridge | -0.74 | -1.04 | -1.35 | -2.27 |
| momentum_12_1 | 0.18 | 0.08 | -0.02 | -0.32 |

### Long/short leg decomposition (gross ann. return)

| model | long leg | short leg |
|---|---|---|
| lightgbm | 12.0% | -9.0% |
| ensemble | 18.2% | -12.1% |
| ridge | 10.7% | -17.7% |
| momentum_12_1 | 12.4% | -9.9% |

### Ensemble membership by fold (walk-forward admission)

- fold 1: (none admitted)
- fold 2: lightgbm
- fold 3: lightgbm
- fold 4: lightgbm, ridge
- fold 5: lightgbm, ridge

## Per-year net performance

| model | 2016 | 2017 |
|---|---|---|
| lightgbm | -10%/-1.0 | -2%/-0.5 |
| ensemble | — | 3%/0.7 |
| ridge | -18%/-1.6 | -6%/-0.9 |
| momentum_12_1 | -10%/-0.7 | 16%/1.5 |
  (cells: ann return / Sharpe)

## Skeptic reports

```
skeptic(lightgbm):
  [WARN] significance: NW t-stat 0.50 < 3 required given 28 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity 0.59 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] decay: second-half OOS IC (0.0035) is less than half of first-half (0.0098) — edge is decaying (Fischer-Krauss pattern).
  [WARN] cost fragility: break-even cost 5 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.28 < 0.95 given 28 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ensemble):
  [WARN] significance: NW t-stat 0.03 < 3 required given 28 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity -0.02 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] decay: second-half OOS IC (-0.0140) is less than half of first-half (0.0149) — edge is decaying (Fischer-Krauss pattern).
  [WARN] cost fragility: break-even cost 10 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ridge):
  [WARN] significance: NW t-stat -0.68 < 3 required given 28 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -12 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.17 < 0.95 given 28 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(momentum_12_1):
  [WARN] significance: NW t-stat -0.89 < 3 required given 28 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost 9 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.33 < 0.95 given 28 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
