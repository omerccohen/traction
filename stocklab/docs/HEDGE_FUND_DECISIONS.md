# The Top-Down Funnel: Synthesis

*How hedge funds actually decide (docs/RESEARCH_FUND_PROCESS.md) × what the
evidence says works (docs/RESEARCH_FUND_EVIDENCE.md) — and what it means for
this project. The user hypothesis under investigation: "global sentiment
(inflation, rates) → field sentiment (supply/demand, e.g. spotting the chip
shortage early) → picking the stocks best positioned to solve big problems."*

## 1. The funnel is real — and the user described it accurately

The macro→field→stock funnel is not a retail fantasy; it is a documented
practitioner workflow (Druckenmiller's liquidity-first cascade, the Tiger-cub
thesis process, the 7-step loop in RESEARCH_FUND_PROCESS.md). The chip-shortage
example happened essentially as hypothesized: foundry quote hikes and the NXP
price-increase letter (Oct–Nov 2020) fired 4–8 weeks before the OEM
production-cut headlines, and auto-levered chip names re-rated for another 2–3
quarters. Anticipating field-level supply/demand imbalance from physical
indicators is a real, repeatedly-executed trade.

## 2. But the profitable steps are not the ones intuition credits

Overlaying the evidence review on the process map:

| Funnel step | Practitioner reality | Evidence verdict |
|---|---|---|
| Macro FORECASTING (inflation/rates calls) | Even macro funds mostly express views in asset classes, not stocks | **Worst-graded layer in the literature**: predictors fail OOS, TAA funds 0-for-12 vs a 60/40, graded forecasters ≈ 47% accuracy. Only mechanical trend/regime *reaction* survives (Sharpe ≈ 0.4) |
| Field imbalance DETECTION | The step where chips/shipping/GLP-1 money was actually made | **Real** — but it runs on *physical indicators* (lead times, price sheets, freight rates, weekly scripts), not "sentiment"; it is short-to-medium horizon; and the data is paid or requires domain immersion |
| "Problem-solver" STOCK PICKING | Funds gate it with variant perception, unit models, base rates, expectations checks | **Negative premium as commonly practiced** (glamour loses ~10pp/yr to value; thematic ETFs −30% risk-adjusted in 5 years post-launch; ARK's dollar-weighted destruction). What works: *quality at reasonable prices*, or the bottleneck owner with pricing power — often the boring node, not the hero |
| The funnel as "why funds win" | The documented persistent winners (Medallion, pods, TCI) mostly *don't run it* — they run breadth+neutrality+capacity control, or quality+activism | Funnel-shaped vehicles (TAA, thematic funds, crossover growth) own the worst records in the modern literature |

## 3. The three reconciling insights

**(a) The edge is in the lag, and the lag is where capital can't stay.**
Documented indicator-to-payoff lags: chips 1–2 months to headlines, 2–4
quarters to full re-rating; shipping 6–15 months; uranium 3–6 YEARS. Pod
capital dies at a 5% drawdown and penalizes >30-day holds; Tiger-style capital
faces quarterly redemptions. The imbalances institutions can SEE but cannot
HOLD are the individual's structural opening — time arbitrage, not information
speed. Conversely, the individual is weakest at the pod's own game:
next-quarter prediction against card panels and twenty expert calls.

**(b) "Sentiment" is the wrong instrument; physical series are the right one.**
Every documented anticipation case ran on countable things — wafer quotes,
non-cancellable order terms, charter durations, utility contract coverage,
weekly prescriptions — with confirmation thresholds defined in advance. Our own
experiments agree from the other side: news *sentiment* on mega-caps is
contemporaneous (+0.09 same-day, −0.01 forward). Text tells you what already
happened; order books tell you what must happen next.

**(c) The stock-picking layer must invert the hero narrative.**
"Who solves the big problem" selects glamour, which underperforms. The
documented winners pick the *bottleneck with pricing power* (the foundry, the
physical pound, the charter owner, fill-finish capacity) and gate it with
falsifiable unit models, expectations-vs-price checks, base rates, and
pre-committed invalidation rules.

## 4. Why our system's nulls were the correct answer to a different question

StockLab tested the pod game (short-horizon cross-sectional prediction) with
public prices only — the single most arbitraged corner of the market, without
the paid data that makes pods viable. The honest nulls are consistent with the
funnel investigation, not in tension with it. The funnel game lives at
horizons (quarters-to-years) where our 5-year dataset contains ~20 independent
bets — statistically unjudgeable by backtest (a true 55% caller needs ~96 years
of quarterly bets to prove skill at 95% confidence). The industry "solves" this
with mechanism-first reasoning, cross-market replication, and daily-granularity
pod evaluation — not with backtests.

## 5. What a disciplined individual implementation looks like

The evidence-approved skeleton of the funnel, with the forecasting removed:

1. **Regime layer — mechanical, not predictive**: trend/vol regime conditioning
   on public prices (the one macro layer with a century of evidence, Sharpe
   ≈ 0.3–0.4 as an overlay). Already prototyped in StockLab's market features.
2. **Field layer — instrument one or two value chains you genuinely know**:
   build dashboards of *physical* series (public ones exist: SEMI billings,
   WSTS, freight indices, FDA shortage lists, EIA data) with pre-registered
   thresholds. This is research infrastructure, not a backtest — validation is
   mechanism + out-of-time behavior, and it needs data feeds this sandbox
   cannot reach.
3. **Stock layer — quality-at-reasonable-price on the bottleneck**, never the
   story stock: profitability, balance-sheet survivability ("right but late"
   must be survivable), what growth the price already implies, pre-committed
   invalidation. Point-in-time fundamentals required.
4. **Honest expectations**: combined net IR ≈ 0.2–0.5 — meaningful compounding
   help, not a money machine; sized for 25–60% published-edge decay; judged
   over years by mechanism-adherence, not by short-window P&L.

## 6. Bottom line

The user's intuition contains a true core: the funnel exists, is run daily by
professionals, and the chip shortage was detectable in advance from named,
dated indicators. The evidence adds the two corrections that decide
profitability: (1) delete the forecasting top of the funnel and replace
narrative stock-picking at the bottom with quality/bottleneck discipline;
(2) accept that the remaining edge is structural (time horizon + small size +
physical data), budget-dependent at short horizons, and unverifiable by
backtest at long ones — which is why process discipline, not prediction
accuracy, is what actually separates the documented winners from everyone else.
