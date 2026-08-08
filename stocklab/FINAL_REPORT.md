# StockLab — Final Report

> StockLab is a research and educational tool. Nothing here is a
> recommendation to buy or sell any security.

## Verdict (per the pre-registered decision rule)

**Null.** The pre-registered primary configuration — beta-neutralized
LightGBM, 5-day horizon, 25 trailing features, decile long-short at
10 bps/side — scored on the untouched holdout (2017-06-01 → 2018-01-30,
168 days):

| metric | value | pre-registered bar | met? |
|---|---|---|---|
| holdout rank IC | **+0.0230** | — | — |
| Newey-West t | **+1.39** | ≥ 2 | **no** |
| net Sharpe @10bps | **−0.64** | > 0 | **no** |
| break-even cost | **3.8 bps/side** | > 10 bps | **no** |

Quoting the wording committed in `docs/PREREGISTRATION.md` before the lockbox
was opened: the test's minimum detectable IC was ~0.06 — several times larger
than honest published daily-equity signals — so this run **excludes
leakage-scale artifacts but can neither demonstrate nor exclude an edge of
realistic size.** Across **43 logged trials** on 2013-2018 S&P-500 survivors,
no model family produced evidence distinguishable from a zero-signal system
with ~1.5 effective independent bets. No trading conclusion follows in either
direction — in particular, *not* "short the signal".

## The one row that crossed t=2 — and why it is not a discovery

Ridge (a secondary) scored holdout IC +0.041, NW t = 2.45, net Sharpe +1.44,
break-even 21.8 bps. Under the pre-registered forbidden-moves list this
cannot be promoted: it is the best of seven highly-correlated rows
(winner's curse: with se ≈ 0.03 and ~2-3 effective independent models, the
expected best-of-k under a modest common regime tailwind reaches exactly this
size), on an 8-month, single-regime, survivorship-biased window that ends at
a momentum melt-up peak. The strongest permissible statement: **suggestive,
not a discovery; pre-registered replication on fresh post-2018 data is the
required next test.** The pairwise ridge-vs-primary difference is itself
inside noise (se of any pairwise holdout difference ≥ ~0.02).

## Pre-committed sensitivity checks (all clean — see experiments/final/sensitivity.md)

- **No Jan-2018 boundary dependence**: IC without Jan-2018 = +0.0241 (vs +0.0230).
- **No day-concentration**: dropping the 5 largest-|IC| days *raises* IC to +0.0258.
- **No leakage signature**: IC by horizon rises smoothly 1d +0.018 → 10d +0.030
  (a 1d spike is the classic leak fingerprint; there is none).
- **Leakage suite green** on both tabular and sequence paths (shuffled ≈ 0,
  canaries fire at 0.98 / 1.00).
- Per-month IC swings −0.04 → +0.08 — the instability the power analysis
  predicted for a window this short.

## What the program established (with receipts)

1. **The pipeline measures honestly.** It recovers planted signals on
   synthetic markets, reports ~zero on null markets, collapses on shuffled
   labels, detects planted canaries at IC ≈ 1.0, and its features/labels
   pass point-in-time recomputation on staggered listings (26 tests).
2. **The 2016 iteration window's uniform negativity was real regime, not a
   bug** — refuted sign-error four independent ways; raw-data momentum IC by
   year: 2014 +0.015, 2015 +0.065, **2016 −0.049**, 2017 +0.023; matches the
   documented 2016 US momentum crash.
3. **~60% of the momentum book's 2016 loss was un-hedged beta**, removed by
   per-date beta-neutralization (v4) — a risk-control improvement that
   moved every model +0.012..+0.027 IC without creating an edge.
4. **The model ladder ordered as the literature predicts**: LightGBM ≈
   ridge ≈ shallow MLP ≥ LSTM > Transformer on full OOS; deep/sequence
   models never beat the tabular ones (GKX 2020, Qlib benchmarks, DLinear
   critique — reproduced).
5. **Costs are decisive at this signal size.** Even the primary's positive
   holdout IC dies at 3.8 bps/side break-even. IC 0.02-0.04 with ~0.4/day
   turnover is not a strategy; it is a statistic.

## What would actually move the needle (ranked, from the research docs)

1. **Fresh out-of-time data** (post-2018): the only legitimate test of the
   ridge observation, and of anything else.
2. **Survivorship-free universe with delisting returns** — the current
   dataset's biases flatter every long-side number.
3. **Point-in-time fundamentals and news/sentiment features** — the
   literature's evidence for genuine (small) incremental alpha lives in
   fresh-news reaction and quality/value interactions, not in more price
   transforms.
4. **Longer history** (multiple regimes) — 5 years ≈ 1.5 regimes; sample
   size in *regimes*, not rows, binds model capacity.
5. More compute/architectures would NOT help: the binding constraint is
   signal-to-noise, demonstrated by the ladder ordering.

## Deliverables

- `stocklab/` — the full system (installable, tested, documented)
- `docs/RESEARCH_OPEN_SOURCE.md`, `docs/RESEARCH_LITERATURE.md` — the research base
- `docs/DESIGN.md` — architecture and the anti-self-deception contract
- `docs/SKEPTIC_LOG.md` — every finding from 3 review rounds, adjudicated
- `docs/PREREGISTRATION.md` — the binding pre-registration (committed before opening)
- `experiments/final/` — the one-shot holdout evaluation + sensitivity.md
- `experiments/trial_ledger.json` — all 43 trials, counted against every Sharpe
- `experiments/final/ranking.md` — the live ranking, shipped with its null evidence
