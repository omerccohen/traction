# Open-Source Stock-ML Landscape: Architecture Lessons for a Stock-Ranking System

*Survey of the major open-source stock prediction / quant-ML projects, with design ideas worth copying and known failure modes. Compiled 2026-08 from project repos, docs, papers, and third-party critiques (research agent output, reviewed and adopted into StockLab's design). Focus: what to steal (and what to avoid) when building a new cross-sectional stock-ranking ML system.*

---

## 1. Microsoft Qlib — github.com/microsoft/qlib

**(a) What it does.** The most complete open-source "AI quant platform" (~47k stars): data layer, factor library, model zoo, config-driven experiment workflow, portfolio backtest, and online serving. It frames the problem correctly — models score a cross-section of stocks each day and a portfolio strategy consumes the scores — rather than "predict the price of one ticker."

Key architecture pieces:

- **Data layer**: per-instrument, per-field flat binary columnar storage with an **expression engine**: factors are declarative strings like `Ref($close, -2)/Ref($close, -1) - 1`, with expression/dataset caches so factor research iterates in seconds.
- **Alpha158 / Alpha360**: two canonical feature sets. Alpha158 = 158 hand-engineered tabular features designed for tree models. Alpha360 = last 60 days × 6 raw normalized fields — designed for sequence models. The default **label is `Ref($close,-2)/Ref($close,-1)-1`**: the return from t+1's close to t+2's close, because a signal computed after t's close can only be traded at t+1 — look-ahead is designed out of the label itself.
- **Model zoo + benchmark table** (examples/benchmarks): 28+ models, each reported as mean±std over ~20 seeds on identical data. Representative Alpha158 ICs: **LightGBM 0.0448, TRA 0.0440, GATs 0.0349, LSTM 0.0318, Transformer 0.0264, DoubleEnsemble 0.0521 (best)**. On Alpha360, sequence models catch up (GRU 0.0493, HIST 0.0522, Transformer collapses to 0.0114). Two lessons: gradient boosting on good features beats most deep nets on engineered tabular data, and realistic edges are IC ≈ 0.03–0.05, not "95% accuracy."
- **Workflow**: `qrun config.yaml` runs data → train → predict → signal analysis (IC/ICIR/RankIC) → portfolio backtest (default **TopkDropoutStrategy**: hold top-k scores, swap out n each day) with market frictions.
- **Rolling / online serving**: first-class **walk-forward "rolling" workflow** (retrain every N days, stitch predictions), plus meta-learning for concept drift (**DDG-DA**, AAAI 2022). **Ensembles** across models (DoubleEnsemble tops the leaderboard) and across rolling windows/seeds.
- **Extras**: point-in-time database for quarterly fundamentals (keyed by announcement date, not period end); nested decision execution.

**(b) Design ideas worth copying**
1. **Label = next-tradable-bar forward return** — the tradability constraint lives in the label, not in post-hoc fixes.
2. **Declarative factor definitions + caching** — reproducible strings, not ad-hoc notebook pandas.
3. **Benchmark-table discipline**: every model run N seeds on frozen datasets, mean±std of IC/ICIR/RankIC.
4. **Rolling retrain as the default workflow** — test predictions always come from a model trained only on prior data.
5. **Config-driven runs with tracked artifacts** — every result reproducible from one config.

**(c) Weaknesses.** Bundled community data is low quality; US-market support second-class; heavy abstraction stack; some model-zoo results hard to reproduce; default backtest is daily close-to-close with simple proportional costs — no market impact.

---

## 2. FinRL — github.com/AI4Finance-Foundation/FinRL

**(a) What it does.** The flagship open-source **deep-RL-for-trading** framework. Three layers: Gym-style market environments, agents (PPO, A2C, SAC, DDPG, TD3), applications. FinRL-Meta (NeurIPS 2022) adds dynamic datasets; annual FinRL Contests now encrypt timestamps and collect out-of-sample data *after* the submission deadline — an explicit admission of how easily this setup leaks.

**(b) Design ideas worth copying**
1. **Environment/agent separation** — clean interface between market simulation and decision logic.
2. **The contest evaluation protocol** (holdout collected after model freeze) is the right adversarial mindset.
3. **Dynamic dataset regeneration** from live pipelines rather than frozen CSVs.

**(c) Weaknesses — the cautionary tale.** (i) extreme seed variance and non-reproducibility (maintainers' own papers concede this); (ii) backtest overfitting is the default outcome (they published a paper on it, arXiv 2209.05559); (iii) tutorials historically used current index constituents backtested into the past (survivorship bias), free yfinance data, naive fixed costs; (iv) daily-bar RL with portfolio-value reward has ~1 sample/day of extremely low signal-to-noise — agents mostly rediscover leveraged buy-and-hold; independent replications of the flagship ensemble strategy generally fail to beat buy-and-hold after honest cost/seed handling. **Architecture lesson: do not make RL the core of a stock-ranking system.** RL belongs (if anywhere) at the execution layer, after a supervised ranking signal exists.

---

## 3. huseinzol05/Stock-Prediction-Models and the LSTM-price-demo genre

**(a) What it does.** Archived (~9.5k stars) catalog of 18 deep forecasting architectures plus 23 "trading agents", pointed at single-ticker next-day close prediction, reporting "accuracy" of 68–96%.

**(b) Worth copying:** model-catalog-as-notebooks pedagogy. Its real value is as a **negative example**.

**(c) Why naive next-day-price LSTM demos are misleading** (applies to thousands of similar repos):
- **The persistence trap**: on a near-random-walk price series, the loss-minimizing one-step forecast is ŷ(t+1) ≈ y(t). The LSTM converges to a lagged copy of the input; plots look "amazingly accurate" while containing zero tradable information. These models **underperform the naive "predict yesterday's price" baseline**; one study measured predicted-vs-lagged-price autocorrelation of 0.89.
- **Metrics that reward the trap**: R²/MAPE on price *levels* are dominated by persistence; a naive forecast also scores ~95%+. Directional accuracy near 50–55% on returns is the honest number.
- **Standard leaks**: MinMaxScaler fit on the full series; recursive forecasts re-anchored on true prices; tuning on the test window; single ticker, no costs, no cross-section, no naive baseline.
- **Lesson**: never model price levels; model (excess/relative) returns; treat any suspiciously smooth "prediction tracks price" plot as a bug.

---

## 4. Backtesting engines — vectorbt, backtrader, zipline-reloaded, LEAN

- **vectorbt** — Numba-JIT vectorized simulation; broadcasts hyperparameter grids into the column axis (thousands of variants in one pass). Best for research-scale sweeps, not microstructure fidelity.
- **backtrader** — classic event-driven engine; beloved API, effectively unmaintained, slow on large universes.
- **zipline-reloaded** — maintained Quantopian fork. Crown jewel: **Pipeline API** — cross-sectional factor computation over a *screened point-in-time universe*, trading calendars, VolumeShareSlippage (fills capped as % of bar volume).
- **LEAN** (QuantConnect) — production-grade: security master with splits/dividends/**delistings**, point-in-time universe selection, per-brokerage reality models, identical code paths backtest → live.

**What a good backtest must model (checklist distilled from all four)**
- **Costs**: commissions + spread + market impact as a function of participation; borrow fees on shorts.
- **Fill realism**: trade at *next* bar, never the same bar's close that generated the signal; untradable bars (halts, limit moves).
- **Point-in-time data**: historical index membership, fundamentals keyed by announcement date, delistings resolved at real terminal value.
- **Vectorized engines "lie about microstructure"** — fine for ranking research, but validate on an event-driven engine before believing/funding a strategy.

---

## 5. Alphalens (quantopian/alphalens, alphalens-reloaded)

**(a) What it does.** The standard **factor evaluation** library. Aligns factor values per (date, asset) with 1/5/10-day forward returns; tear sheet reports: **Information Coefficient** (daily Spearman of factor vs forward return — mean IC, ICIR = mean/std, t-stats, IC decay across horizons), **mean returns by factor quantile** (monotonicity), **long-short top-minus-bottom spread**, **turnover per quantile and factor rank autocorrelation** (implied trading cost), **sector-neutral breakdowns**.

**(b) Worth copying**
1. **Signal tear sheet as a mandatory gate before any portfolio backtest** — isolates predictive power from implementation.
2. **Quantile monotonicity as a sanity test**: a real factor moves returns smoothly across bins; only-the-top-decile-works is a red flag.
3. **IC decay across horizons** to choose rebalance frequency; **rank autocorrelation/turnover** to forecast cost drag.
4. **Sector/group neutralization** so you know if a "factor" is just a sector bet.

**(c) Weaknesses.** Original unmaintained; daily-frequency equal-weight assumptions; garbage-in sensitivity; no transaction costs (by design — pair with a backtester).

---

## 6. mlfinlab / López de Prado tooling

**(a) What it does.** Implementation of *Advances in Financial Machine Learning*: **triple-barrier labeling**, meta-labeling, **purged K-fold CV with embargo**, combinatorial purged CV, fractional differentiation, sample-uniqueness weighting, MDI/MDA feature importance, **Probabilistic and Deflated Sharpe Ratio** (Bailey & López de Prado 2014) which discounts an observed Sharpe for the number of trials, track length, skew, kurtosis.

**(b) Worth copying**
1. **Purged K-fold + embargo for all model selection** — overlapping forward-return labels make ordinary K-fold leak; the single most common silent inflator of financial ML results.
2. **Deflated Sharpe / trial accounting**: log every configuration ever evaluated; deflate final statistics by effective number of trials.
3. **Meta-labeling** as an optional second stage ("should I act on this signal") for bet sizing.
4. **Sample-weighting by label uniqueness** when labels overlap.

**(c) Weaknesses.** Went closed-source (community forks exist; the core is ~200 lines to reimplement). For daily cross-sectional *ranking*, triple-barrier labels and fractional differentiation often add complexity for little IC gain. The unambiguously transferable parts: purging/embargo, DSR, and "backtesting is a validation tool, not a research tool."

---

## 7. Notable recent projects (2023–2026)

### RD-Agent / RD-Agent(Q) — microsoft/RD-Agent
LLM multi-agent loop automating quant R&D on Qlib: propose hypothesis → generate factor/model code → backtest → read feedback → iterate. Reports IC 0.0532 on CSI300 with ~70% fewer factors than Alpha158. **Copy**: the *closed experiment loop* — any factor idea enters a standardized propose→implement→evaluate→log pipeline. **Criticism**: an automated loop optimizing against a backtest is a multiple-testing machine — without trial accounting and a locked holdout it overfits at industrial scale.

### TradeMaster — TradeMaster-NTU/TradeMaster
NTU's RL platform. Standout: **evaluation toolkit (PRUDEX-Compass)** — multi-metric, multi-seed comparison (profitability, risk, reliability) because single-backtest RL claims don't replicate. **Copy**: evaluation-first mindset; regime labeling for stress tests.

### Stockformer — arXiv 2401.06139
Academic SOTA ranking net: wavelet decomposition + dual-frequency spatiotemporal encoder + stock-relation graphs + **multi-task heads** (return regression + trend classification). **Copy**: multi-task labels regularize; relation graphs are a proven IC add. **Criticism**: frequency-domain transforms are a leak hazard (must be strictly causal); complexity per IC point is high vs LightGBM.

### FinGPT — AI4Finance-Foundation/FinGPT
Open financial-LLM stack: strong at **sentiment classification** (F1 ~0.87) but **stock-movement prediction accuracy 45–53%** — near coin-flip. **Copy**: LLMs as *feature factories* (per-stock daily sentiment with strict article-timestamp discipline) piped into the same IC evaluation as any factor. **Criticism**: an LLM is not a trading system.

### AlphaGen — RL-MLDM/alphagen (KDD 2023)
RL generator of formulaic alphas whose reward is the **marginal improvement of the whole alpha pool's combined IC**, not standalone IC. **Copy**: evaluate candidate features by marginal contribution to the ensemble — kills the "100 correlated momentum clones" problem. **Criticism**: symbolic search is a multiple-testing furnace; needs frozen out-of-sample periods and trial deflation.

---

## SYNTHESIS: what a credible system must have

1. **Predict cross-sectional relative returns, not raw prices.** Prices are near-random-walk; level-forecasting converges to persistence and fake accuracy.
2. **Bake tradability into the label** (Qlib's `Ref($close,-2)/Ref($close,-1)-1`). Most tutorial leakage is a label bug, not a model bug.
3. **Point-in-time everything: universe, prices, fundamentals.** Without it, numbers are not merely optimistic but meaningless.
4. **Walk-forward rolling retrain as the only evaluation and deployment mode.**
5. **Purged K-fold + embargo for all hyperparameter selection.** ~200 lines; non-negotiable.
6. **IC / RankIC (with ICIR) as the primary research metric.** Realistic good values: 0.03–0.06.
7. **Two-gate evaluation: signal tear sheet first, portfolio backtest second.**
8. **LightGBM on engineered features is the baseline to beat** (Qlib: LGB 0.0448 vs LSTM 0.0318, Transformer 0.0264). Admit deep models only when they beat it out-of-sample on the same frozen data.
9. **Ensemble across seeds, rolling windows, and models.** Deep-model seed variance is large; averaging is the cheapest reliable gain.
10. **Model costs and turnover from day one.** A 0.04-IC signal with 100% daily turnover is dead at 20bps round-trip.
11. **Two backtest tiers: vectorized for research, event-driven for pre-production.**
12. **Trial accounting + Deflated Sharpe on every reported result.**
13. **Declarative factor definitions + registry; score new factors by marginal contribution to the pool.**
14. **Config-driven, tracked experiments; frozen benchmark datasets.**
15. **Keep RL and LLMs at the edges, not the core.** RL for execution/bet-sizing at most; LLMs as timestamp-disciplined feature factories and hypothesis generators, never autonomous decision-makers judged on backtests they helped tune.

*(Full source-link list retained in the research agent transcript; primary sources: project GitHub repos, Qlib benchmarks README, arXiv 2111.09395, 2209.05559, 2401.06139, SSRN 2460551, NeurIPS 2022 FinRL-Meta, KDD 2023 AlphaGen.)*
