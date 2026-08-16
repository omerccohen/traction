# Pre-committed sensitivity checks — primary configuration (lightgbm, neutralized, h=5)

Holdout window: 2017-06-01 .. 2018-01-30 (168 scored days)

- holdout rank IC: **+0.0230** (NW t = +1.39)

## Per-month IC

| month | IC | days |
|---|---|---|
| 2017-06 | +0.0737 | 22 |
| 2017-07 | +0.0060 | 20 |
| 2017-08 | +0.0040 | 23 |
| 2017-09 | +0.0571 | 20 |
| 2017-10 | +0.0791 | 22 |
| 2017-11 | -0.0378 | 21 |
| 2017-12 | -0.0176 | 20 |
| 2018-01 | +0.0144 | 20 |

## January-2018 boundary check

- IC without Jan/Feb-2018: **+0.0241** (NW t = +1.29, 148 days)
- IC of 2018 days alone: +0.0144 (20 days) — the data ends 2018-02-07, at a momentum melt-up peak; the Feb-2018 reversal is outside the sample.

## Concentration

- IC with the 5 largest-|IC| days removed: **+0.0258** (vs +0.0230 with them)

## IC by horizon (holdout, leakage-signature check)

-  1d: +0.0181
-  5d: +0.0230
- 10d: +0.0298
- 21d: +0.0292

## Trial accounting

- ledger total (incl. this run): **43** configurations
- primary holdout net Sharpe: -0.64; deflated-Sharpe prob is reported in results.json against this ledger.