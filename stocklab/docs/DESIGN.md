# StockLab — Design Document

A machine-learning stock **ranking** system built to be honest before it is impressive.
Every design decision below exists to kill a specific, well-documented failure mode of
"AI stock picking" projects.

> **This is a research tool, not financial advice.** Nothing it outputs is a
> recommendation to buy or sell any security.

## 1. What we predict (and what we refuse to predict)

- **Target:** cross-sectional *relative* performance — which stocks will do better than
  their peers over the next `k` trading days (default `k=5`). The label is the forward
  k-day return, **cross-sectionally demeaned per date**, so the model is never asked to
  forecast the market itself, only the ordering of stocks within it.
- **Not the target:** absolute prices or index levels. Next-day price forecasting demos
  (the classic LSTM-on-closing-prices tutorial) look accurate because prices are a
  near-random-walk: predicting "tomorrow ≈ today" scores a great RMSE and contains zero
  tradeable information. We refuse that framing entirely.

## 2. Timing discipline (the anti-lookahead contract)

All timestamps follow one contract, enforced in code and covered by tests:

```
signal date t:   features may use information up to and including close(t)
execution:       positions established at close(t+1)   (one full day of lag)
label:           ret = close(t+1+k) / close(t+1) - 1
```

- Features are built exclusively from **trailing** windows ending at `t`.
- The label starts at `t+1`, never at `t` — you cannot trade the close you just observed.
- A point-in-time test recomputes features on truncated data and asserts equality with
  the full-sample computation (no function may peek forward).

## 3. Data layer

- **Bundled real data:** S&P 500 daily OHLCV, Feb-2013 → Feb-2018, ~505 tickers
  (public dataset, checked into the repo compressed). Two known biases are documented and
  surfaced by the skeptic module rather than hidden:
  - *Survivorship bias*: constituents as of 2018 — failed/delisted names are missing, which
    inflates long-side results and mutes short-side ones.
  - *Single regime*: a 5-year bull market with two corrections; results do not speak to
    bear-market behavior.
- **CSV ingestion** for any user-supplied panel (`date,open,high,low,close,volume,ticker`).
- **Synthetic market generator:** a regime-switching factor model with *planted* momentum
  and reversal effects of realistic (small) size. Used by tests to verify the pipeline can
  recover a known signal and reports ~zero when the planted signal is removed.
- Basic hygiene: minimum history per ticker, minimum price and dollar-volume filters
  (penny/illiquid names are where fake backtest alpha lives), forward-fill limits, and an
  explicit tradability mask instead of silently dropped rows.

## 4. Features (all trailing, all boring on purpose)

Per stock, per date — the factors with decades of literature behind them, not exotica:

| Group | Features |
|---|---|
| Momentum | 21d / 63d / 126d returns; 12-1 momentum (252d skipping most recent 21d) |
| Reversal | 5d return (short-term reversal), 1d return |
| Volatility | 21d / 63d realized vol; downside semivol ratio |
| Trend | close/SMA50, SMA50/SMA200, MACD histogram (price-normalized), Bollinger z(20d) |
| Range/anomaly | distance from 252d high (52-week-high effect), RSI(14) |
| Liquidity/size | log 21d avg dollar volume, Amihud illiquidity, volume trend 21d/63d |
| Market context | market 21d return & vol, cross-sectional dispersion (same value for all stocks that date) |

All features are **cross-sectionally rank-transformed to [-1, 1] per date** before
modeling. Per-date transforms cannot leak time-series information by construction, make
distributions stationary across regimes, and remove the need for any fitted scaler that
could smuggle test-set statistics into training.

## 5. Models — a ladder, not a hero

Every rung must beat the rung below it out-of-sample, or it is not used:

1. **MomentumBaseline** — score = 12-1 momentum. Zero parameters. The floor.
2. **Ridge** — linear, heavily regularized. What GKX (2020) found hard to beat.
3. **LightGBM** — gradient boosting, the strongest tabular-data prior.
4. **MLP** (Keras) — 2 hidden layers, dropout, early stopping.
5. **LSTM** — 40-day sequences of a compact feature subset.
6. **Transformer** — small encoder (2 blocks) on the same sequences.
7. **Ensemble** — average of per-date z-scored member predictions (only members that
   individually beat the momentum floor are admitted).

Deep nets are deliberately small: the empirical finance literature (GKX 2020) finds
*shallow* networks beat deep ones on this data regime — signal-to-noise, not capacity,
is the binding constraint.

## 6. Validation — purged walk-forward

- Expanding-window walk-forward: train on everything up to fold start, minus a
  **purge+embargo gap of `k+1+5` trading days** (so no training label window overlaps a
  test date), then predict a 63-day out-of-sample block; retrain and roll.
- All reported numbers are **concatenated out-of-sample predictions only**.
- Primary metric: daily cross-sectional **rank IC** (Spearman), with a **Newey–West
  t-statistic** (lag = k) because overlapping k-day labels autocorrelate IC series.
- Secondary: decile portfolio monotonicity, long-short top-vs-bottom-decile returns.

## 7. Backtest — costs are not optional

- Long-short (and long-only variant) decile portfolios, rebalanced at `close(t+1)`,
  positions held k days via k overlapping tranches (or single-tranche at lower frequency).
- **Transaction costs charged on turnover** (default 10 bps per side; sensitivity grid
  0 / 5 / 10 / 25 bps is always reported). Sharpe without costs is not reported anywhere.
- Outputs: annualized return/vol/Sharpe, max drawdown, turnover, cost drag, and a
  **deflated Sharpe ratio** that penalizes the number of model variants tried.

## 8. Leakage guards (automated, in `tests/` and `stocklab/validation/leakage.py`)

1. **Shuffled-label test** — retrain on date-block-shuffled labels → IC must collapse to ~0.
2. **Future-feature canary** — inject the label as a feature → the guard must scream
   (verifies our detector can detect).
3. **Point-in-time recomputation** — features(data up to t) == features(full data) at t.
4. **Split audit** — assert every train label window ends before the first test date.

## 9. Skeptic module

`stocklab/skeptic.py` runs after every experiment and emits a red-flag report:

- OOS daily rank IC > 0.10 → *suspect leakage* (published good signals live at 0.02–0.06).
- Net Sharpe > 3 on daily equity signals → *suspect leakage or costs missing*.
- Decile returns non-monotonic → signal is noise concentrated in tails.
- Train IC ≫ test IC → overfitting index.
- Performance survives only at 0 bps costs → not a real edge.
- Result driven by a handful of days (top-5-day excision test).
- Dataset-level warnings (survivorship, single-regime) attached to every report.

The same skepticism is applied by human/agent review each iteration and logged in
`docs/SKEPTIC_LOG.md` (critique → fix → re-run).

## 10. Honesty budget — what success looks like

On survivor-biased daily data over one bull regime, an *honest* result is modest: rank IC
in the low single digits (0.01–0.04), long-short net Sharpe well under 1.5, and instability
across folds. The system's job is to measure that honestly and to prove to a skeptic that
what remains is not an artifact. Anything that looks better than this budget triggers the
skeptic module, not a celebration.
