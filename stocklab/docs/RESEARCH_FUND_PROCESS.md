# How Hedge Funds and Institutions Actually Make Decisions

*(Research agent output, reviewed and adopted. Full inline source links preserved
in the agent transcript; key sources listed at the end.)*

## 1. The top-down funnel: global macro

**Bridgewater (systematized):** economic-machine template -> regime
classification (growth x inflation "four boxes") -> indicator ingestion (credit
creation, CB balance sheets, flows, breakevens) -> relative-value across ~150
liquid markets -> risk-based sizing toward many uncorrelated bets. Every rule
written down and backtested across countries and decades before it trades.
**Crucially: the funnel STOPS at asset-class/country level** — macro views
become bond/FX/index futures positions, not single stocks.

**Soros/Druckenmiller (discretionary):** liquidity, not earnings, is the top
node ("focus on the central banks"); "never invest in the present" — visualize
18-24 months out; the market itself is a data source (bank stocks, cyclicals,
credit spreads as leading indicators); instrument selection is opportunistic
(express the view in whatever has best asymmetry); concentration at maximum
conviction ("go for the jugular", GBP 1992).

## 2. Long/short equity: the Tiger-cub process

Idea generation (screens, industry mapping, network) -> full fundamental thesis
(TAM, unit economics, moat direction, management quality, 2-3yr earnings power
vs consensus) -> **variant perception as the gate** (Steinhardt: "a well-founded
view meaningfully different from consensus") -> catalysts (hard vs soft) ->
sizing = conviction x liquidity x downside. Concentrated books: 20-40 longs.

A real analyst workweek: models for 15-50 names updated per datapoint; earnings
previews/reviews 4x/yr per name; 5-15 expert calls/week in deep-dive; 1-2 pitch
memos/month.

**Expert networks** (GLG, AlphaSights, Guidepoint, Tegus; ~$1000+/hr) map value
chains and pressure-test theses. **Channel checks**: distributors, suppliers,
resellers (Point72 institutionalized as "Market Intelligence"). **Post-Galleon
guardrails** (Rajaratnam 2011, 11 years; SAC/"Black Edge"): mosaic theory legal,
but no current-employer discussion, no unreleased numbers, chaperoned/recorded
calls, do-not-contact lists.

## 3. Multi-strategy pod shops (Citadel, Millennium, Point72)

Structure: hundreds of pods (1 PM + 2-4 analysts, $100-200M levered several
turns), each forced ~market-neutral (net within ±20%) AND within caps on factor
exposures (beta, sector, size, momentum, value, crowding) monitored centrally
against Barra/Axioma models.

**Why force neutralization:** (1) anything a factor model replicates is cheap
beta — pods are paid for the residual "idio" P&L only (Paleologo, *Advanced
Portfolio Management*); (2) idio bets diversify across pods, factor bets STACK
— neutrality is what makes 5-8x leverage survivable; (3) protects against
correlated degrossing events.

**Risk rules:** ~5% drawdown -> capital halved; ~7.5% -> pod terminated;
15-20% annual PM turnover; daily capital reallocation. "The alpha factory has
kill switches."

**What edge means in a pod:** short-horizon single-name forecasting superiority
around catalysts (next print vs consensus via alt data + channel checks +
positioning read); many pods penalize holds >30 days. Fed transaction study:
funds order in a given stock every ~12 trading days on average.

## 4. Thematic / supply-chain anticipation — the indicator toolkit

| Indicator class | Named sources | Front-runs |
|---|---|---|
| Component lead times | Susquehanna tracker, Digitimes | shortages, pricing power |
| Industry price sheets | TrendForce/DRAMeXchange | semi cycle turns |
| Equipment/capex | SEMI billings, WSTS | capex cycles |
| Freight rates | SCFI, FBX, Harpex, Baltic Dry | shipping earnings, goods inflation |
| Card panels | YipitData, Second Measure, Consumer Edge | company revenue pre-print |
| Satellite/geo | Orbital Insight, RS Metrics, Placer.ai | retail traffic, storage, congestion |
| App data | Sensor Tower, data.ai | consumer-tech inflections |
| Job postings | LinkUp, Revelio | expansion/roadmaps |
| Import manifests | Panjiva, ImportGenius | supplier links, volumes |
| Prescriptions | IQVIA weekly, Symphony | drug launches |

### Case 1 — the 2020-21 chip shortage (the user's example, documented)
- Q3-Q4 2020: 8-inch foundry capacity fully loaded; UMC/GloFo/Vanguard raise
  quotes 10-15% with 20-40% teed for 2021 (TrendForce/Digitimes documenting).
- Nov 26, 2020: NXP letter — raising prices on ALL products, "severe shortage",
  one-year non-cancellable orders. Microchip 10-Q concurrent.
- Dec 2020: VW warns of production cuts. Dec 29: Third Point's Intel letter
  (activist conversion of the supply observation). Jan 8, 2021: Ford idles
  Louisville — now front-page.
- 2021-22: Susquehanna lead-time tracker (17wk Apr-21 -> 20.2wk Aug -> 21.9wk
  Oct) becomes the market's thermometer; its mid-2022 rollover marked the top.
- **Measured lag: physical indicators fired 4-8 weeks before headlines;
  full stock re-rating ran another 2-3 quarters** (auto-levered names ~doubled
  in the following 12 months).

### Case 2 — uranium 2016-24: thesis 2017 (mine-by-mine supply model, utility
contract-coverage rolloff), Kazatomprom cuts 2017, McArthur River suspension
2018, Sprott physical trust July 2021 as engineered catalyst; spot $20 -> $106
Jan-2024; Cameco ~5x. **Indicator-to-payoff lag: 3-6 YEARS — why no pod could
hold it and specialist/personal capital owned it.**

### Case 3 — container shipping 2020-22: SCFI/FBX inflect Jun-Oct 2020; charter
DURATIONS extending converted spot froth into contracted EBITDA; ZIM 5x+ from
its flopped Jan-2021 IPO. **Lag: 6-15 months.**

### Case 4 — GLP-1s: STEP-1 efficacy discontinuity (mid-2020) -> Wegovy launch
outruns supply (2021-22) -> IQVIA weekly scripts become the most-watched series
in equities -> second-order "Ozempic basket" shorts (restaurants, sleep apnea,
CGM) only mid/late-2023. **Each stage gave 6-18 months.**

## 5. Horizons and capacity — where competition is weakest

| Fund type | Holding period | Constraint |
|---|---|---|
| Stat arb | hours-2wk | signal decay |
| Pods | days-1 quarter (>30d penalized) | drawdown kill switches |
| Discretionary macro | weeks-18mo | policy cycles |
| Tiger-style L/S | 6mo-3yr | LP redemption terms |
| Quality long-only (Baillie Gifford) | 5-10yr | none — by design |
| Activist/PE | 3-10yr | control positions |

**Retail/individual competition is weakest: (1) beyond ~2 years (institutions
can SEE imbalances they cannot HOLD — uranium archetype); (2) below capacity
thresholds (micro/small caps, odd securities); (3) through drawdowns (nobody
halves your capital at -5%). Weakest AT the pod's own game: next-quarter
prediction against card panels and 15 expert calls.**

## 6. "Who solves big problems" — process vs narrative

- ARK: Wright's Law cost curves -> TAM -> 1-10 scoring with forced review
  triggers; open research. Cautionary half: -75% ARKK drawdown = theme
  identification without valuation/entry discipline.
- Baillie Gifford LTGG: fixed ten-question framework ("Can sales double in 5
  years?"), research aimed at years 3-10, positions re-scored by rule.
- Tiger Global 2021-22 = the failure mode: ~350 private deals in a year,
  speed-over-price, -56%/-67% in 2022.
- The discipline stack separating investing from narrative: (1) falsifiable
  unit-level model; (2) expectations check (what growth is priced in —
  Mauboussin/Rappaport); (3) base rates; (4) pre-committed review triggers;
  (5) sizing that admits fallibility.

## THE FUNNEL AS PRACTITIONERS RUN IT (7 steps, a loop)

1. **Macro regime read** (quarterly): growth x inflation box + liquidity vector.
   Output: one-page regime statement, favored asset classes.
2. **Theme selection**: where does the regime create a supply/demand gap
   consensus hasn't priced? Output: 3-5 themes with explicit imbalance
   hypothesis and size-of-gap estimate.
3. **Field verification**: instrument the theme with the highest-frequency
   PHYSICAL series available; define confirmation thresholds in advance
   (lead times, price sheets, freight rates, scripts, card data). This step —
   not the macro forecast — is where the chip/shipping/GLP-1 money was made.
4. **Value-chain mapping + human verification**: 5-20 expert calls inside the
   guardrails; find the BOTTLENECK node (foundry 2020, physical pound 2021,
   charter owner 2021, fill-finish capacity 2022).
5. **Single-name selection**: rank every listed lever on the bottleneck by
   torque, survivability, valuation vs re-rated scenario, liquidity. Output:
   pitch memo with variant perception + catalyst calendar.
6. **Structure, sizing, risk**: choose expression; hedge what you have no view
   on; written invalidation criteria (the step-3 dashboard run in reverse).
7. **Monitor, recycle, mind the lag**: the documented lags ARE the profit
   margin — 1-2 months indicator->headline in chips; 2-4 quarters to re-rating;
   6-15 months shipping; 3-6 years uranium. Match trade horizon to capital
   horizon — the most common institutional failure and the individual's
   structural opening.

*Caveats: pod risk parameters are reported conventions, not filings; Bridgewater
rules reconstructed from public writings; "who was early" limited to documented
actors (letters, interviews, published research).*

*Key sources: Bridgewater publications; Macro Ops/Druckenmiller compilations;
Steinhardt "No Bull"; Wall Street Prep/Marcellus on Tiger cubs; GLG/Integrity
Research on expert networks; OJP/NPR on Rajaratnam; Kolhatkar "Black Edge";
Paleologo "Advanced Portfolio Management"; WSO pod AMAs; Fed working paper
2021-022 (fund transaction horizons); Point72 Market Intelligence; Coatue
Mosaic coverage; EE Times/EPS News (NXP letter); DCD/Al Jazeera (Susquehanna
lead times); Crux Investor/MacroVoices (Alkin uranium); Seatrade/FreightWaves
(ZIM); IQVIA/Fierce Pharma (GLP-1 scripts); Fortune/CNBC (Ozempic basket);
ARK process docs; Baillie Gifford LTGG philosophy; CNBC/Workweek (Tiger 2022);
Investment Masters Class (time arbitrage).*
