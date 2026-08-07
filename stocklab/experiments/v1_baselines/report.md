# v1: baselines on real S&P500 2013-2018

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

- trials counted for deflation: **3**
- folds: 7, total runtime 29s

## Signal tear sheet (out-of-sample, concatenated across folds)

| model | rank IC | ICIR | NW t | IC>0 % | mono | Q10-Q1 (5d) | rank-AC | n days |
|---|---|---|---|---|---|---|---|---|
| ridge | 0.0021 | 0.016 | 0.19 | 50% | 0.07 | 0 bps | 0.95 | 393 |
| momentum_12_1 | -0.0014 | -0.008 | -0.08 | 49% | -0.75 | -4 bps | 0.99 | 393 |
| lightgbm | -0.0162 | -0.123 | -1.38 | 46% | -0.58 | -7 bps | 0.82 | 393 |

## IC by horizon (days)

| model | 1 | 10 | 21 |
|---|---|---|---|
| ridge | 0.0115 | -0.0090 | -0.0146 |
| momentum_12_1 | 0.0105 | -0.0101 | -0.0177 |
| lightgbm | -0.0014 | -0.0176 | -0.0279 |

## Backtest — long-short decile, overlapping tranches, net of costs

| model | net Sharpe | net ann ret | gross Sharpe | maxDD | turnover/d | break-even bps | DSR prob |
|---|---|---|---|---|---|---|---|
| ridge | -0.86 | -8.5% | -0.02 | -19.9% | 0.33 | -0 | 0.05 |
| momentum_12_1 | -0.32 | -4.8% | -0.11 | -19.3% | 0.13 | -5 | 0.17 |
| lightgbm | -1.58 | -15.1% | -0.48 | -24.0% | 0.42 | -4 | 0.00 |

### Cost sensitivity (net Sharpe at bps per side)

| model | 0 bps | 5 bps | 10 bps | 25 bps |
|---|---|---|---|---|
| ridge | -0.02 | -0.44 | -0.86 | -2.12 |
| momentum_12_1 | -0.11 | -0.22 | -0.32 | -0.64 |
| lightgbm | -0.48 | -1.03 | -1.58 | -3.22 |

### Long/short leg decomposition (gross ann. return)

| model | long leg | short leg |
|---|---|---|
| ridge | 14.9% | -15.1% |
| momentum_12_1 | 12.1% | -13.7% |
| lightgbm | 9.7% | -14.3% |

## Skeptic reports

```
skeptic(ridge):
  [WARN] significance: NW t-stat 0.19 < 2 required given 3 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] quantile monotonicity: decile monotonicity 0.07 — returns are not smooth across ranks; edge may be a tail artifact.
  [WARN] cost fragility: break-even cost -0 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.05 < 0.95 given 3 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
```
```
skeptic(momentum_12_1):
  [WARN] significance: NW t-stat -0.08 < 2 required given 3 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -5 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.17 < 0.95 given 3 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
```
```
skeptic(lightgbm):
  [WARN] significance: NW t-stat -1.38 < 2 required given 3 trials — consistent with noise (Harvey-Liu-Zhu).
  [WARN] cost fragility: break-even cost -4 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
  [WARN] deflated Sharpe: DSR probability 0.00 < 0.95 given 3 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
  [NOTE] baseline: does not beat momentum baseline IC (-0.0014); per design rules this model is not admitted to the ensemble.
  [NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
  [NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
```

## Leakage suite

```json
{
  "shuffled_label_ic": 0.001213178444095706,
  "shuffled_label_verdict": "PASS (no pipeline leak detected)",
  "canary_ic": 0.9821663975256743,
  "canary_verdict": "PASS (detector fires on planted leak)"
}
```