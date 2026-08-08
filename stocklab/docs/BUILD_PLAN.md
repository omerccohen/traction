# Build Plan: from demo to a living research operation

Goal: turn what exists (StockLab = the lie detector, FieldWatch = the
attention allocator, the research library) into a continuously running
personal research operation modeled on the evidence-approved parts of the
hedge-fund funnel. Explicitly NOT an autotrader and never a buy-list.

## What already exists (done, tested, committed)

- **StockLab** — leakage-proof evaluation harness: purged walk-forward,
  cost-aware backtests, skeptic tripwires, leakage suite, trial ledger,
  pre-registration pattern. 26 tests green. Any future quantitative claim
  gets judged here.
- **FieldWatch** — 38 watched fields (11 sectors, 26 sub-industries, custom
  value chains) with unusualness scoring (trend/vol/dispersion/volume/
  cohesion/news) and briefing generation. Validated on historical event
  dates (Feb-2016, Feb-2018).
- **Research library** — open-source survey, literature survey, fund-process
  map with the indicator toolkit, evidence review, funnel synthesis.
- **Data layer** — CSV ingestion with alias handling, corporate-action
  sanitizer, PIT eligibility. Ready to receive any `date,ticker,...` feed.

## Phase 1 — Live price feed (THE gate; one decision is the user's)

Everything downstream needs one thing: a daily OHLCV update for the chosen
universe. Three viable paths — pick one:

| Path | How | Trade-off |
|---|---|---|
| A. Open-network environment | Re-create the Claude environment with a network policy that allows a data source (e.g. Stooq/Yahoo endpoints, or a broker API the user holds keys for); a scheduled session runs the updater | Fully automated; needs the policy change |
| B. User-side fetcher | A tiny script (provided) runs on the user's machine/cron, commits `data_cache/latest.csv.gz` to the repo; cloud sessions analyze | No policy change; user machine must run daily/weekly |
| C. Manual drop | User exports CSV from any broker/site weekly and drops it in | Zero setup; weekly cadence only |

Deliverables: `scripts/update_prices.py` (schema-validated, sanitizer-run,
append-only with revision log), universe config (S&P 500 + optional
small-cap extension — where the remaining literature-supported edges live).
Effort: one session once the path is chosen.

## Phase 2 — Live FieldWatch (weekly briefing)

- `fields.yml`: user-editable field definitions (sectors auto + custom
  chains like the memory/compute chain).
- Scheduled run (Claude Routine or cron): generate the weekly briefing,
  publish as artifact/markdown in `briefings/`, with a delta section
  ("what changed since last week") and threshold crossings.
- Effort: one session. Depends only on Phase 1.

## Phase 3 — Physical-indicator instrumentation (the verification layer)

The layer where the documented money was made (chips/shipping/GLP-1 cases).
Start with ONE chain the user knows (semiconductors), 2-3 public series:

- Registry design: `indicators/` adapters, each storing series WITH
  retrieval timestamps (point-in-time discipline), a pre-registered
  threshold file (committed before use, PREREGISTRATION.md-style), and
  provenance notes.
- Candidate public sources (network permitting): FRED (rates/credit/
  industrial production), EIA (energy), SEMI/WSTS press releases
  (semi billings/sales), Freightos FBX public prints, FDA shortage list.
  Paid sources (TrendForce, IQVIA, card panels) documented as upgrade
  paths, not dependencies.
- Briefing integration: each flagged field shows its physical indicators
  vs thresholds — "attention + evidence" in one page.
- Effort: 2-3 sessions for the semis MVP; expand chain-by-chain.

## Phase 4 — Quality/bottleneck stock layer (needs fundamentals)

- Source: SEC EDGAR XBRL company facts (free, public; keyed by FILING date
  for point-in-time honesty) — requires network access to sec.gov (path A)
  or user-side fetch (path B).
- Build: PIT fundamentals store; quality metrics (gross profitability,
  ROIC trend, accruals, leverage, survivability); expectations check
  (what growth the price implies vs base rates).
- Output: per-candidate CHECKLIST (the Tiger-cub memo skeleton with the
  numbers pre-filled), never a recommendation. Any systematic version of
  the screen goes through StockLab before it is trusted.
- Effort: several sessions; largest single build.

## Phase 5 — The discipline loop (process, mostly not code)

- `theses/` folder with a pre-registration template per idea: variant
  perception, physical confirmations expected, invalidation triggers,
  review dates. (The repo already practices this pattern on itself.)
- Weekly cadence: briefing -> indicator dashboards -> forced thesis
  reviews. Decisions logged; the log IS the track record, judged over
  years with the power caveats documented in RESEARCH_FUND_EVIDENCE.md §7.

## Phase 6 — Standing validation

- Every quantitative rule that emerges (e.g. "tilt when threshold X
  crosses") is walk-forward tested in StockLab, ledger-counted, deflated.
- The skeptic module reviews every result; SKEPTIC_LOG continues.

## Sequencing and reality

- Critical path: Phase 1 -> 2 (days once the feed decision is made).
- Phase 3 starts immediately after (semis chain first).
- Phase 4 is parallel-izable but biggest; Phase 5 costs discipline, not code.
- Standing constraints, restated: no buy lists; attention + evidence +
  checklists only; expectations calibrated to IR 0.2-0.5 for any
  systematic tilt; long-horizon judgments validated by process adherence,
  not short-window P&L.
