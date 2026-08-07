# Machine Learning for Stock Return Prediction: A Skeptic's Literature Survey

*Survey of academic and practitioner evidence on what actually works, what fails, and how to avoid fooling yourself. Compiled 2026-08 (research agent output, reviewed and adopted into StockLab's design).*

---

## 1. Gu, Kelly & Xiu (2020): the benchmark study

**Gu, Kelly & Xiu, "Empirical Asset Pricing via Machine Learning," *RFS* 33(5)** is the canonical horse race: ~30,000 US stocks, 1957-2016, 94 characteristics + 8 macro series (~920 features), monthly returns, expanding-window refits.

- **Predictability is real but tiny.** Monthly OOS R2 for individual stocks: OLS with all features *negative*; 3-feature OLS (size, B/M, momentum) ~0.16%; elastic net ~0.11%; PCR/PLS ~0.26-0.27%; random forest ~0.33%; boosted trees ~0.34%; neural nets 0.33-0.40%, best ~**0.40%/month** -> implied IC ~ sqrt(0.004) ~ **0.06. That is the ceiling** achieved by the best model on 60 years of data.
- **Shallow beats deep.** Performance peaks at ~3 hidden layers and *declines* for deeper nets. Trees get ~85-90% of the NN gain.
- **Economic magnitude:** value-weighted L/S decile Sharpe ~1.35 OOS (equal-weighted 2.45, leaning on microcaps). All **pre-cost**.
- **Which features matter:** price-trend variables dominate (1-mo reversal, 12-1 momentum, industry momentum), then liquidity (size, dollar volume, turnover), then volatility. Gains come from **nonlinear interactions of the same small set**, not exotic data.
- **Caveat (Avramov, Cheng & Metzker, *Mgmt Sci* 2023):** ML profits concentrate in microcaps, distressed names, high-vol episodes, and the short leg; excluding microcaps + realistic costs "considerably attenuates" profitability.

## 2. Lopez de Prado: why most backtests are false

- **Purged K-fold CV with embargo.** Multi-day labels overlap; standard K-fold leaks. Purge training rows whose label window overlaps test, embargo an extra buffer after each test block.
- **Triple-barrier labeling / meta-labeling:** path-aware labels; ML predicts *whether the primary signal is right* (bet sizing) - one of the most practical ideas in the book.
- **Backtest overfitting:** expected max in-sample Sharpe of N zero-skill configs grows like sqrt(2 ln N). **Deflated Sharpe Ratio** tests the observed Sharpe against that expected max (correcting for track length, skew, kurtosis). **PBO** via combinatorial CV. Harvey & Liu: apply a ~50% haircut to any reported backtest Sharpe.

## 3. The factor literature: what survives

| Signal | Reference | Verdict |
|---|---|---|
| Momentum (12-1) | Jegadeesh & Titman 1993 | Very robust across countries/assets; rare crashes (-73% Mar-May 2009, Daniel & Moskowitz 2016); vol-scaling helps; survives realistic costs |
| Short-term reversal | Jegadeesh 1990 | Strongest gross, weakest net (extreme turnover); mostly unprofitable after costs standalone; still the single most useful ML *feature* (GKX) |
| Low-volatility | Ang et al. 2006; BAB 2014 | Robust internationally; low turnover; capacity-constrained |
| Value | Fama & French 1992 | Real but weakened post-publication; brutal 2017-2020; slow turnover survives costs |
| Quality/profitability | Novy-Marx 2013 | Among better post-publication survivors; low turnover |

**Factor zoo / replication crisis:** Harvey, Liu & Zhu (2016): new factors should clear **t >= 3.0**. Hou, Xue & Zhang (2020): of 452 anomalies, **65% fail |t|>=1.96** with microcap mitigation. McLean & Pontiff (2016): predictor returns **-26% out-of-sample, -58% post-publication**. Jensen, Kelly & Pedersen (2023): broad *themes* replicate (~82%); size real factors at 1/3-1/2 of published strength.

## 4. Deep learning for finance: the honest state

- **Fischer & Krauss (2018)**: LSTM on S&P 500 daily, Sharpe 5.8 *pre-cost* - but profits concentrate pre-2000 and **post-2010 returns fluctuate around zero after costs**. The most-cited LSTM result self-reports its own death by arbitrage.
- **Zeng et al. (AAAI 2023) "Are Transformers Effective for Time Series Forecasting?"**: one-layer linear (DLinear) beats Informer/Autoformer/FEDformer by 20-50% on standard benchmarks. If Transformers struggle on high-SNR electricity load, priors for near-zero-SNR daily equities are very pessimistic.
- **Grinsztajn et al. (NeurIPS 2022)**: tuned XGBoost/RF beat tuned deep models on typical tabular tasks. Cross-sectional equity prediction IS a tabular problem. Consistent with GKX and with Numerai/Jane Street leaderboards (GBDT ensembles dominate).
- **Honest ranking on cross-sectional tabular features: GBDT ~ shallow-NN ensemble > penalized linear >> deep/sequence models**, first two often within noise.
- Deep learning earns its keep in finance for: representation learning over unstructured data (text, filings), very-high-frequency microstructure, not end-to-end daily OHLCV prediction.

## 5. News and sentiment

- Ke, Kelly & Xiu (NBER w26186): news assimilated in ~1-2 days; *fresh* news survives reasonable costs at daily horizon, *stale* does not. Text alpha half-life: hours to days.
- FinBERT: better sentiment *classification* than dictionaries; incremental *return* predictability modest, fast-decaying.
- Lopez-Lira & Tang (2023): GPT-4 headline scores predict next-day drift, concentrated in small caps and negative news; Sharpe 3.8 **pre-cost**, but ~350% cumulative at 10bps vs ~50% at 25bps - extreme cost sensitivity; edge declining as adoption rises. **LLM memorization look-ahead** is a real bias when backtesting inside the model's training window.

## 6. Efficient-markets reality check

- **Realistic IC: 0.02-0.05 good; 0.05-0.10 excellent; sustained > 0.10 on a liquid universe = leakage until proven otherwise.**
- **Realistic daily direction accuracy: 50.5-53% is skillful.** Claims of 60-90% are always leakage/cherry-picking.
- **Realistic net Sharpe: 0.8-1.5 excellent for a single daily cross-sectional equity strategy; > 2-2.5 sustained = presumed broken.**
- **Costs:** mid-turnover anomalies pay 20-57 bps/month (Novy-Marx & Velikov); >50% monthly turnover rarely survives without cost mitigation (buy/hold bands). US mega-cap half-spread 1-3bps, mid 5-15bps, small 20-100+bps, plus impact, plus borrow on shorts.
- **Grinold-Kahn:** IR ~ IC x sqrt(breadth) x transfer coefficient - breadth and turnover management, not model heroics, drive real performance.
- **Market-level timing fails OOS (Welch & Goyal 2008). Cross-sectional relative prediction is the tractable problem.**

## 7. Regime change and non-stationarity

- Momentum -73% in 3 months (2009); value lost half a Sharpe-decade 2017-2020; Fischer-Krauss alpha vanished post-2010. Assume any genuine edge loses 30-60% of backtest strength live.
- Sample size in *regimes* is ~5-10, not the nominal row count - the deepest reason shallow models win.
- Mitigations: rolling retraining on a fixed schedule; ensembling across seeds/windows/families; volatility targeting for risk (not sign-flipping); live IC monitoring with a predefined kill rule.

---

## DESIGN RULES (adopted by StockLab)

1. Predict the cross-section, not the level.
2. Mandatory baselines: zero/naive, ridge on {momentum, reversal, size, vol}, LightGBM. New models must beat them net of costs or are rejected.
3. Purged, embargoed walk-forward only. Never shuffled K-fold on returns.
4. All preprocessing statistics from training window only (per-date cross-sectional ranks are safe by construction).
5. Count every trial; report Deflated Sharpe against the full trial count; demand t >= 3 after many trials.
6. Haircut everything: expect <= 50% of backtest Sharpe live; assume 30-60% decay.
7. Model costs pessimistically: report at 0/5/10/25+ bps per side. A strategy that dies between 10 and 25 bps is not a strategy.
8. Control turnover by design (buy/hold bands, tranche overlap, horizon-matched rebalancing).
9. Headline results on a liquid universe (min price, min ADV); flag equal-weighted results as such.
10. Report long and short legs separately; short-microcap-driven alpha = unimplementable.
11. Prefer shallow models sized to the data (<= 3 hidden layers; heavy regularization).
12. Ensemble by default: multiple seeds for NNs, blend across families; never ship single-seed.
13. Retrain on a fixed schedule chosen ex ante.
14. Sanity-bound metrics: tripwires at IC > 0.10, accuracy > 58%, net Sharpe > 2.5 -> leakage audit, not celebration.
15. Vol-target the book; cap single names.
16. Restrict features to defensible families (momentum, reversal, vol, liquidity, value, quality, optionally fresh news).
17. Text/LLM features: timestamp discipline; evaluate only post-training-cutoff; assume half-life <= 1-3 days.
18. Point-in-time data only; delistings included where available; document biases when not.
19. Predefine live monitoring and a kill rule (rolling IC < 50% of backtest -> decommission).
20. Write the spec before running experiments; freeze a final untouched holdout evaluated once.

## SKEPTIC CHECKLIST (implemented in stocklab.skeptic + SKEPTIC_LOG)

1. Classic look-ahead in features -> lag everything one bar and re-run; collapse proves look-ahead.
2. Label/train overlap leakage -> purge+embargo >= label horizon; material drop proves original leaked.
3. Normalization/scaler leakage -> no fit on data later than prediction date; per-date ranks safe.
4. Survivorship bias -> count tickers/year vs known universe; check presence of later-delisted names.
5. Backtest overfitting -> Deflated Sharpe with true trial count; performance across ALL configs.
6. Iterated peeking at test set -> experiment log review; fresh out-of-time data for final claims.
7. Microcap/equal-weighting mirage -> re-run on liquid universe, min price $5.
8. Short-leg dependence -> decompose L/S into legs; check short-leg implementability.
9. Costs and turnover -> annualized turnover; re-run at 10/25/50 bps; break-even bps vs realistic spreads.
10. Non-tradable timing -> 1-bar execution delay minimum; performance on implementable lag only.
11. Volume/liquidity fantasy -> position size vs ADV; cap participation.
12. Non-point-in-time fundamentals -> announcement-date keying (n/a for pure-price features).
13. Regime luck -> per-year returns; rolling Sharpe; inspect crisis windows.
14. Decay masked by averages -> first-half vs second-half OOS IC; decay > 50% = decaying edge.
15. Cherry-picked benchmark -> equal-tuning-budget baselines on identical data/CV.
16. Seed instability -> multi-seed mean +/- sd; claimed result > 2sd from seed-mean = seed-picking.
17. LLM memorization -> evaluation window after model training cutoff only.
18. Overlapping-label t-stat inflation -> Newey-West/HAC with lags >= label horizon.
19. Unneutralized risk exposure -> regress strategy returns on factor proxies; check crash behavior.
20. Too-good tripwire -> daily accuracy > 58%, IC > 0.10, net Sharpe > 2.5, near-zero drawdown -> full leakage audit first.

## Key references

Gu/Kelly/Xiu RFS 2020; Lopez de Prado 2018 (AFML); Bailey & Lopez de Prado 2014 (DSR, SSRN 2460551); Harvey/Liu/Zhu RFS 2016; Hou/Xue/Zhang RFS 2020; McLean & Pontiff JF 2016; Jensen/Kelly/Pedersen JF 2023; Daniel & Moskowitz JFE 2016; Frazzini/Israel/Moskowitz 2015; Novy-Marx & Velikov RFS 2016; Avramov/Cheng/Metzker Mgmt Sci 2023; Fischer & Krauss EJOR 2018; Zeng et al. AAAI 2023 (DLinear); Grinsztajn et al. NeurIPS 2022; Kelly/Malamud/Zhou JF 2024 + Buncic 2025 critique; Ke/Kelly/Xiu NBER w26186; Huang/Wang/Yang 2023 (FinBERT); Lopez-Lira & Tang 2023; Welch & Goyal RFS 2008.

**Bottom line:** ML genuinely improves cross-sectional prediction, but the honest gain is small (IC ~0.03-0.06 ceiling), comes from nonlinear combinations of six defensible signal families, is best captured by regularized shallow models, and the dominant risk is self-deception - leakage, survivorship, uncounted trials, ignored costs, decay. A correct process rejects most ideas; that is what correct looks like in a market this efficient.
