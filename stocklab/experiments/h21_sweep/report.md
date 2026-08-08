# horizon=21d sweep

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

- trials counted for deflation: **32** (this run's models + persisted prior-run ledger)
- folds: 6, total runtime 28s

## Signal tear sheet (all OOS folds, concatenated)

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| lightgbm | -0.0136 | -0.133 | -0.77 | 44% | -0.55 | -11 bps | 0.87 | 378 |
| ensemble | -0.0246 | -0.229 | -0.85 | 43% | -0.53 | -53 bps | 0.92 | 189 |
| ridge | -0.0251 | -0.245 | -1.33 | 40% | -0.42 | -78 bps | 0.94 | 378 |
| momentum_12_1 | -0.0326 | -0.238 | -1.32 | 36% | -0.75 | -10 bps | 0.99 | 378 |

## IC by horizon (days)

| model | 1 | 10 | 21 |
|---|---|---|---|
| lightgbm | 0.0085 | -0.0053 | -0.0136 |
| ensemble | 0.0061 | -0.0056 | -0.0246 |
| ridge | 0.0020 | -0.0144 | -0.0251 |
| momentum_12_1 | 0.0044 | -0.0213 | -0.0326 |

## Backtest — long-short decile, overlapping tranches, net of costs

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| lightgbm | -0.58 | -4.3% | -0.13 | -14.4% | 0.13 | -3 | nan |
| ensemble | -1.25 | -8.4% | -0.80 | -9.7% | 0.12 | -18 | nan |
| ridge | -1.45 | -12.0% | -1.06 | -18.6% | 0.13 | -27 | nan |
| momentum_12_1 | -0.23 | -3.0% | -0.09 | -16.5% | 0.07 | -6 | nan |

### Cost sensitivity (net Sharpe at bps per side)

| model | 0 bps | 5 bps | 10 bps | 25 bps |
|---|---|---|---|---|
| lightgbm | -0.13 | -0.35 | -0.58 | -1.25 |
| ensemble | -0.80 | -1.03 | -1.25 | -1.94 |
| ridge | -1.06 | -1.26 | -1.45 | -2.04 |
| momentum_12_1 | -0.09 | -0.16 | -0.23 | -0.45 |

### Long/short leg decomposition (gross ann. return)

| model | long leg | short leg |
|---|---|---|
| lightgbm | 14.3% | -15.3% |
| ensemble | 15.5% | -20.9% |
| ridge | 12.6% | -21.4% |
| momentum_12_1 | 11.6% | -12.7% |

### Ensemble membership by fold (walk-forward admission)

- fold 1: ridge
- fold 2: ridge
- fold 3: lightgbm, ridge
- fold 4: lightgbm, ridge
- fold 5: lightgbm, ridge

## Per-year net performance

| model | 2016 | 2017 |
|---|---|---|
| lightgbm | -10%/-1.2 | 9%/2.2 |
| ensemble | -24%/-2.6 | 2%/0.5 |
| ridge | -17%/-1.7 | -3%/-0.7 |
| momentum_12_1 | -10%/-0.7 | 13%/1.1 |
  (cells: ann return / Sharpe)

## Skeptic reports

```
skeptic(lightgbm):
  [WARN] significance: NW t-stat -0.77 < 3 required given 32 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -3 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ensemble):
  [WARN] significance: NW t-stat -0.85 < 3 required given 32 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -18 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(ridge):
  [WARN] significance: NW t-stat -1.33 < 3 required given 32 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -27 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
```
skeptic(momentum_12_1):
  [WARN] significance: NW t-stat -1.32 < 3 required given 32 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -6 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
  [NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
  [NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```
