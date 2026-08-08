# StockLab — an honest machine-learning stock ranking laboratory

> **This is a research and educational tool, not financial advice.** Its outputs
> are statistical signals measured on historical data — not recommendations to
> buy or sell anything. Past performance does not predict future results, and
> this system's own headline finding is that most apparent edges are artifacts.

StockLab predicts **which stocks are likely to do better than their peers**
over the next few days (cross-sectional ranking) — never prices, never the
market — and it is engineered so that every number it reports survives the
known ways "AI stock picking" projects fool their authors.

Built from a deep-dive into the open-source landscape (Microsoft Qlib, FinRL,
alphalens, López de Prado's tooling — see `docs/RESEARCH_OPEN_SOURCE.md`) and
the academic literature (Gu-Kelly-Xiu 2020, the factor-zoo replication
crisis, backtest-overfitting statistics — see `docs/RESEARCH_LITERATURE.md`),
then hardened by three rounds of adversarial review with every finding and fix
logged in `docs/SKEPTIC_LOG.md`.

## What makes it honest

| Failure mode | Defense (all enforced in code + tests) |
|---|---|
| Trading the close you just observed | Label = `close(t+1+k)/close(t+1)−1`; backtest first earns P&L at t+2 (test-pinned from both sides) |
| Overlapping-label leakage | Purged walk-forward with embargo; grid-audited every run |
| Lookahead features | Every feature trailing-only; dataset-level point-in-time test on staggered listings |
| Lookahead universe | Trailing 63d price/liquidity eligibility, point-in-time (no full-sample medians) |
| Scaler leakage | Per-date cross-sectional ranks only; no fitted scalers anywhere |
| Costs ignored | 10 bps/side default; 0/5/10/25 grid always reported; break-even bps; turnover-damping tranches |
| Overfitting via many tries | Deflated Sharpe with a **persistent trial ledger** across all runs |
| Winner-picked ensembles | Walk-forward admission: fold k's membership decided only on folds < k |
| Holdout reuse | Post-2017-06 folds locked; final run reports HOLDOUT-ONLY separately; opening is recorded and warned about |
| Data corruption | Corporate-action sanitizer (6 repaired events, logged); survivorship/dividend biases attached to every report |
| Seed luck | Multi-seed neural nets, averaged |
| Overlapping-label t-stats | Newey-West (lags = 2×horizon) everywhere |
| Too-good-to-be-true | Skeptic module: literature-calibrated tripwires (IC, Sharpe, monotonicity, leg dependence, decay) run on every result |

## Layout

```
stocklab/
├── stocklab/
│   ├── config.py            # every timing constant, with rationale
│   ├── data/                # panel model, loaders (+sanitizer), synthetic market
│   ├── features/            # trailing technical features, PIT pipeline
│   ├── labels.py            # lagged forward returns, symmetric rank target
│   ├── validation/          # purged walk-forward + leakage guards
│   ├── models/              # momentum, ridge, LightGBM, MLP, LSTM, Transformer
│   ├── backtest/            # cost-aware engine + tear-sheet metrics
│   ├── ensemble.py          # per-date z-scored averaging
│   ├── skeptic.py           # automated red-flag review of every result
│   ├── runner.py            # walk-forward orchestration + reports
│   └── report.py            # live ranking report (ships with its evidence)
├── data_cache/              # bundled real S&P500 daily OHLCV 2013-2018 (.gz)
├── docs/                    # research surveys, design doc, skeptic log
├── experiments/             # run artifacts + trial ledger + holdout marker
├── scripts/                 # run_experiment.py, fetch_data.py
└── tests/                   # 26 tests incl. planted-signal recovery & PIT
```

## Quickstart

```bash
pip install -e .            # core (numpy/pandas/sklearn/lightgbm/scipy)
pip install -e ".[deep]"    # + tensorflow-cpu for MLP/LSTM/Transformer

python -m pytest            # 26 tests: timing, purge, recovery, null, canary

# baselines on the bundled real data (iteration folds only — holdout stays locked)
python scripts/run_experiment.py --models momentum,ridge,lightgbm --out experiments/my_run

# full ladder
python scripts/run_experiment.py --models all --out experiments/full

# FINAL evaluation (opens the lockbox; recorded and warned on reuse)
python scripts/run_experiment.py --models all --include-holdout --out experiments/final
```

Bring your own data: `stocklab.data.load_csv("panel.csv")` with columns
`date,ticker,close,volume[,open,high,low]` (yfinance-style `Adj Close`
handled; adjusted close preferred and stated).

## The model ladder

Every rung must beat the rung below **out-of-sample, net of costs**, or it is
not used: 12-1 momentum (zero parameters) → Ridge → LightGBM → shallow MLP →
LSTM → small Transformer → walk-forward-admitted ensemble. This ordering is
what the evidence supports: GKX 2020 and the Qlib benchmarks both find
gradient boosting ≈ shallow nets > deep/sequence models on daily equity data,
and our results on the bundled dataset reproduce exactly that.

## What results look like (and should look like)

On the bundled data (S&P 500, 2013-2018, survivor-biased, one bull regime),
honest baselines report **rank IC ≈ 0** on the 2015-2017 iteration window —
that window contains the 2016 momentum crash, and the pipeline says so rather
than hiding it. The literature's ceiling for the best models ever published is
IC ≈ 0.03-0.06. Any run of this system that reports dramatically more than
that triggers the skeptic module, and the leakage suite (shuffled labels ≈ 0,
canaries ≈ 1.0 on both tabular and sequence paths) is printed with every
report so readers can see the measurement instrument works.

## Known limitations (disclosed, not hidden)

- Bundled dataset is survivor-biased (2018 constituents), price-return only
  (no dividends), single bull regime. Every report carries these caveats.
- No fundamentals, no news/sentiment features (the data isn't bundled);
  the architecture accepts them as additional feature columns with the same
  point-in-time discipline.
- Vectorized backtest: no market impact model beyond linear bps costs, no
  borrow fees on shorts (flagged by the skeptic when the short leg dominates).
- Daily bars only.
