# StockLab ranking as of 2018-02-07

> StockLab is a research and educational tool. Its outputs are statistical signals measured on historical data, not recommendations to buy or sell any security. Past performance does not predict future results.

**Read the evidence before the ranking.** The out-of-sample record of this
signal family on this dataset is the only justification these ranks have:

```json
{'model': 'lightgbm', 'oos_rank_ic': 0.022969519484563366, 'oos_nw_tstat': 1.391083732472026, 'oos_days': 168, 'source': 'experiments/final/results.json', 'dataset_biases': ['SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.', 'SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.', "PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.", 'DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374']}
```

**Skeptic flags on the underlying signal:**

```
[WARN] significance: NW t-stat 1.49 < 3 required given 43 trials — consistent with noise (Harvey-Liu-Zhu).
[WARN] cost fragility: break-even cost 6 bps/side — the edge dies within realistic retail cost ranges (10-25 bps).
[WARN] deflated Sharpe: DSR probability 0.18 < 0.95 given 43 trials — the Sharpe is not distinguishable from the best of that many noise strategies.
[NOTE] dataset: SURVIVORSHIP BIAS: universe = S&P 500 constituents as of 2018; delisted/failed companies are missing. Long-side results are inflated.
[NOTE] dataset: SINGLE REGIME: Feb-2013..Feb-2018 is one bull market; no bear-market evidence.
[NOTE] dataset: PRICE (NOT TOTAL) RETURNS: closes are split-adjusted but NOT dividend-adjusted, so every ex-div date injects ~-(div/price) into the payer's label. Labels carry a small systematic anti-yield tilt; the long leg's P&L understates by roughly the universe's ~2%/yr dividend yield.
[NOTE] dataset: DATA REPAIRS: 6 corporate-action rows mechanically repaired at load (see loaders.sanitize_corporate_actions): BAX 2015-07-01: -44.4% step treated as un-adjusted distribution; prior history scaled by 0.556; DISCA 2014-08-07: -50.6% step treated as un-adjusted distribution; prior history scaled by 0.494; DISCK 2014-08-07: -51.0% step treated as un-adjusted distribution; prior history scaled by 0.490; EBAY 2015-07-20: -56.9% step treated as un-adjusted distribution; prior history scaled by 0.431; LNT 2016-05-19: reversal pair (-49.4% then +101.0%) respliced to +0.79%/day; NI 2015-07-02: -62.6% step treated as un-adjusted distribution; prior history scaled by 0.374
```

## Top 15 (highest scores)

| ticker   |      score |   percentile | notable_features                                                |
|:---------|-----------:|-------------:|:----------------------------------------------------------------|
| KORS     | 0.00631763 |     0.998998 | sma50_sma200=+1.00, mom_vol_scaled=+1.00, mom_126=+0.98         |
| ALGN     | 0.00631763 |     0.998998 | mom_12_1=+1.00, sma50_sma200=+1.00, mom_vol_scaled=+0.99        |
| CBG      | 0.00134531 |     0.922846 | downside_ratio_63=+0.90, mom_vol_scaled=+0.84, log_adv_21=-0.82 |
| FBHS     | 0.00134531 |     0.922846 | ret_5d=-0.92, macd_hist=-0.88, vol_trend=+0.87                  |
| FRT      | 0.00134531 |     0.922846 | rsi_14=-0.98, px_sma50=-0.96, mom_21=-0.91                      |
| FTI      | 0.00134531 |     0.922846 | ret_1d=-0.99, boll_z=-0.96, amihud_21=+0.83                     |
| FLIR     | 0.00134531 |     0.922846 | log_adv_21=-0.97, amihud_21=+0.95, mom_126=+0.82                |
| GPS      | 0.00134531 |     0.922846 | sma50_sma200=+0.96, beta_63=+0.93, downside_ratio_63=-0.91      |
| JEC      | 0.00134531 |     0.922846 | ret_1d=+0.95, log_adv_21=-0.87, beta_63=+0.86                   |
| JNPR     | 0.00134531 |     0.922846 | vol_trend=-0.96, mom_21=-0.84, px_sma50=-0.83                   |
| JWN      | 0.00134531 |     0.922846 | amihud_21=+0.93, mom_63=+0.90, ret_5d=+0.90                     |
| KIM      | 0.00134531 |     0.922846 | rsi_14=-1.00, px_sma50=-1.00, mom_vol_scaled=-0.99              |
| HII      | 0.00134531 |     0.922846 | ret_1d=+0.97, amihud_21=+0.85, ret_5d=+0.84                     |
| GT       | 0.00134531 |     0.922846 | amihud_21=+0.72, log_adv_21=-0.71, mom_63=+0.71                 |
| IFF      | 0.00134531 |     0.922846 | log_adv_21=-0.94, amihud_21=+0.81, mom_consistency=+0.78        |

## Bottom 15 (lowest scores)

| ticker   |       score |   percentile | notable_features                                       |
|:---------|------------:|-------------:|:-------------------------------------------------------|
| CMS      | -0.00677967 |    0.0210421 | vol_21=-0.95, vol_63=-0.94, beta_63=-0.93              |
| ETR      | -0.00677967 |    0.0210421 | boll_z=-0.93, mom_63=-0.92, beta_63=-0.85              |
| ESS      | -0.00677967 |    0.0210421 | mom_126=-0.89, mom_63=-0.88, sma50_sma200=-0.87        |
| D        | -0.00677967 |    0.0210421 | beta_63=-0.98, vol_21=-0.98, vol_trend=+0.92           |
| SO       | -0.00677967 |    0.0210421 | beta_63=-0.99, vol_21=-0.97, vol_63=-0.95              |
| DTE      | -0.00677967 |    0.0210421 | vol_63=-0.97, vol_21=-0.97, beta_63=-0.97              |
| DUK      | -0.00677967 |    0.0210421 | beta_63=-0.99, vol_63=-0.98, vol_21=-0.92              |
| ED       | -0.00677967 |    0.0210421 | vol_21=-0.96, vol_63=-0.94, beta_63=-0.94              |
| XEL      | -0.00677967 |    0.0210421 | max_ret_21=-0.97, rsi_14=-0.96, boll_z=-0.96           |
| WEC      | -0.00677967 |    0.0210421 | vol_63=-0.96, boll_z=-0.94, beta_63=-0.92              |
| NI       | -0.00677967 |    0.0210421 | max_ret_21=-0.98, vol_21=-0.96, boll_z=-0.94           |
| PSA      | -0.00677967 |    0.0210421 | beta_63=-0.86, mom_vol_scaled=-0.79, mom_63=-0.78      |
| LNT      | -0.00677967 |    0.0210421 | beta_63=-0.92, boll_z=-0.89, px_sma50=-0.88            |
| PPL      | -0.00677967 |    0.0210421 | mom_63=-0.94, sma50_sma200=-0.94, mom_vol_scaled=-0.94 |
| PNW      | -0.00677967 |    0.0210421 | rsi_14=-0.97, vol_21=-0.96, max_ret_21=-0.95           |

*The model assigns only 8 distinct score levels across 499 names — tied scores mean the model genuinely cannot distinguish those stocks; the within-tie ordering is arbitrary.*

*Scores are cross-sectional relative rankings for the configured horizon — not price targets, not probabilities, not advice.*