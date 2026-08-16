# Handoff — everything a new agent needs to work on this project

Paste this whole file as the opening prompt. It is written to be read once and
acted on, not skimmed.

---

## 1. What this system is

A **research-attention allocator** over ~2,990 liquid US companies (NYSE +
Nasdaq + AMEX). It answers one question: **where is something unusual happening
that deserves a human's reading time this week?**

It is **not** a stock picker. This is not modesty — it is a measured result. The
attention score's correlation with forward returns is **+0.0009 (t 0.05)**,
i.e. zero, and that null has been re-verified after every change. Any output
phrased as "buy X" or "X will go up" is a defect.

**Non-negotiable:** never produce buy/sell calls. Direct attention and name the
real-world data a human should go check.

---

## 2. Standing rules from the owner — treat as hard constraints

1. **Real data only.** Every claim must come from a command you actually ran.
   Never assume, never estimate, never describe what code "probably" does. If
   you did not execute it, say so.
2. **Explain simply. This is a hard rule, stated verbatim by the owner.** Short
   sentences, plain words, no jargon. Not "the rank IC was +0.045 with a
   Newey-West t of 2.73" but "it was right slightly more often than chance, and
   that could easily be luck." The owner has repeatedly said they cannot follow
   dense output. Long, technical answers are a failure even when correct.
3. **Never give buy/sell advice.**
4. Work on branch `claude/stock-prediction-deep-learning-cokcbo`. PR #1 is open
   at https://github.com/omerccohen/traction/pull/1 — push to the branch and it
   updates. Do not open a new PR.

---

## 3. How to run it

```bash
cd stocklab
python3 scripts/run_pipeline.py            # the whole deterministic pipeline
python3 scripts/run_pipeline.py --dry-run  # just the dependency graph
python3 scripts/update_prices.py --status  # store health
```

The runner enforces stage order with hard gates. A stage whose prerequisite
failed is reported **SKIPPED**, never silently omitted:

```
prices     <- (nothing)              gated: >=95% of tickers on one date
briefing   <- prices
pack       <- prices                 gated: coverage block present and >=95%
targets    <- pack
positions  <- prices                 gated: price table parsed >0 companies
questions  <- pack, positions
```

Then the LLM stages, which read those artifacts: the **desk note** (brief in
`docs/ANALYST_PROMPT.md`) and occasional **deep per-company rankings**.

Timing: prices ~40 min (deliberate 0.4s pause per ticker — see §6), everything
else under 3 min.

---

## 4. What the evidence actually supports

### Holds (re-verified 2026-08-13 on repaired data)
| claim | number |
|---|---|
| Volatility regime persists 21d ahead | IC **+0.114, t 4.58** (44 dates, 129 fields) |
| Field trend predicts next 21d | +0.073, t 3.17 |
| **Attention does NOT predict returns** | **+0.0009, t 0.05** |

`docs/BACKTEST_FIELDWATCH.md` is the only unretracted backtest in the repo.

### Retracted 2026-08-13 — do not cite these
Every fundamental ranking result. They were measured on a universe built by
ranking dollar volume over the **last 252 days of the store** and applying that
list back to 2018 — companies were in the sample *because of what they later
became*. QBTS traded **$474K/day** in 2022 (rank 2531) and is rank 157 today.
40% of the universe was under $150M/day at the time.

| signal | as published | tradeable universe |
|---|---|---|
| improvement + value | +0.045, t 2.73 | **+0.038, t 1.45** |
| levels "sort backwards" | −0.053, t −3.15 | **−0.029, t −0.96** |
| momentum | +0.087, t 3.10 | **+0.043, t 1.38** |
| cheap-vs-expensive spread | −11.3 pts | **+3.3 pts** (sign flip) |

Nothing clears t=2. `BACKTEST_VALUATION.md` and `BACKTEST_IMPROVEMENT.md` keep
their original text under retraction banners — the record of how they failed is
worth more than a clean rewrite. **Never reintroduce cheapness or "improving
fundamentals" as evidence for anything.**

---

## 5. The bug pattern that runs through this entire codebase

**Missing or truncated data counted as a real measurement.** Found seven times
in one day, in seven different files:

- blank prices sorted last in pandas → not-yet-reported tickers became "top gainers"
- a stale cache served successfully → macro data 1,076 days old labelled "fresh"
- `NaN <= x` is False → unusable correlation windows counted as evidence, so
  109 of 130 groups were labelled "decoupling" when ~40 qualified
- `max(last_date)` → one current ticker made the whole store read "healthy"
  while 2,648 lagged a day
- `head(40)` of a descending sort reported as `n=112` → the analyst never saw a
  loser
- "None this week — that is a complete answer" printed when the input file was
  simply **missing** (17 real leads)
- a company researched in two groups counted twice → "18 disagreements" for 16 names

**When you touch anything here, ask first: what does this do when the input is
absent?** That single question would have caught all seven.

---

## 6. Data-layer facts you must know

- **Zero corporate actions are ever recorded.** No split feed exists. So a
  price halving overnight has to be *judged* as split-or-crash by heuristic.
  That heuristic was deleting **210 real crashes** (the SVB bank run read as a
  flat 0.00% day) until it was fixed to require evidence: a split leaves dollar
  volume unchanged, a crash multiplies it. Now 6 rewrites instead of 231.
- **Survivorship is near-total and unfixable from inside the pipeline.** Only
  **2 of 2,992** tickers ever stop trading in 8.5 years; reality is 4–8% *per
  year*. We only ever downloaded companies that exist today. Every historical
  result is flattered by this.
- **Sector labels come from SIC codes set at company registration and never
  updated.** The SEC's own `sicDescription` is *identical to ours and equally
  stale*, so no classification source can be used as a cross-check — the only
  valid test is **revenue**, read from the company's own filings. 24 labels were
  corrected this way (CLF was filed as a miner, SEI as oilfield when power is
  72% of its revenue, ARKO as a grocer when fuel is 84%). 11 pre-revenue names
  (OKLO: $1.2M revenue, $81.6M loss) were moved out of operating fields into
  `Development Stage/Pre-Revenue`.
- **The 0.4s fetch pause is a deliberate owner decision, not an oversight.**
  Owner chose safety over speed on 2026-08-13. A rate-limited run on 08-12
  aborted after 174 of 2,991 tickers. Do not "optimise" it.
- **Large one-day moves are kept and flagged, never dropped.** The >75% rule
  only removes a move that reverses the next day and nets under 15%.
- FRED is blocked in this environment; 7 of 12 macro indicators are missing and
  3 are ~1,078 days stale. Only VIX and a trend measure are live. **"Fresh"
  means the fetch succeeded — including from an ancient cache. Always check the
  age.**

---

## 7. The attention score, and its known weakness

`score = mean(|pctile − 0.5| × 2)` across five indicators: trend_21d,
volatility, dispersion, volume_influx, cohesion — each ranked against the
field's **own history**.

Averaging five numbers dilutes any single extreme. Mitigations exist but are
imperfect:
- `top_fields` shows the analyst **6** groups.
- `buried_moves` surfaces anything outside those 6 that is extreme on **any**
  indicator (trend ≥80th, or a secondary ≥90th/≤10th, needing two secondaries).
- It once used `rank > 15` while only 6 were shown, so **ranks 7–15 appeared
  nowhere** — that hole hid Electronic Components (the memory/storage names) at
  rank 10, +14.6%, with dispersion at the 100th percentile of its history.

**`buried_moves` currently self-reports `AT CHANCE`** — 35 flagged against 31
expected at random. The rows are true facts; the *selection* carries little
information. The pack states this on every run via `n_expected_by_chance` and
`selectivity`. Making it selective is an open design question, not a bug fix.

---

## 8. Verification discipline — the standard to hold

Three thresholds were shipped in one day: too strict, too loose, then
calibrated. **All three errors were caught by measuring the output, never by
reading the code.** Two of the biggest bugs of the day were caught by the owner
asking "where did X go?" — not by five independent auditors.

So, before claiming anything works:
1. **What would this say if the data were random?** A "90th percentile" filter
   sounds rigorous and fires on 59% of fields when applied to four indicators
   two-tailed. Compute the chance rate and report it beside the result.
2. **How would we know it's wrong?** State the falsifier.
3. **Run it and paste the real output.** A finding without a reproduction is not
   a finding.
4. Re-check the honest null (attention → returns ≈ 0) after any change to the
   signal path. If it starts "working", you have introduced leakage.

Audit reports with full reproductions: `docs/AUDIT_DATA_LAYER.md`,
`AUDIT_BACKTESTS.md`, `AUDIT_JOURNAL_SCRIPTS.md`, `AUDIT_ANALYSIS_LAYER.md`,
`AUDIT_SECTOR_LABELS.md`.

---

## 9. Open items

1. **Delisted-company collector** (biggest hole). Half-solved: the price vendor
   *does* serve dead tickers (SIVB, TWTR, ATVI all return full history), and SEC
   **Form 25** lists every delisting with CIK and date (582 in one quarter, via
   `https://www.sec.gov/Archives/edgar/full-index/<YYYY>/QTR<n>/form.idx`). The
   missing link is **CIK → historical ticker**: the SEC submissions API wipes
   the ticker on delisting, XBRL has no `TradingSymbol`, and the Form 25 HTML
   has no structured field. Best untested lead: SEC filenames embed the ticker
   (SVB's filings are all `sivb-…`). Owner has approved building this.
2. **13 low-confidence sector rollups** — pinned on a weak plurality (one splits
   12/7/6 across three sectors). Made consistent, *not* resolved. Needs the same
   revenue check.
3. **HDRN** appears in briefings but is absent from `broad_sectors.csv`.
4. **Memory is split across two fields** — MU sits in Semiconductors while WDC,
   STX and SNDK sit in Electronic Components, so "memory" can never surface as
   one theme.
5. **`buried_moves` selectivity** — see §7.
6. **Journal is empty by design** (`journal/decisions.csv`, header only). Do not
   add rows. It scores decisions vs SPY once real ones exist.

---

## 10. Where things live

```
stocklab/
  scripts/run_pipeline.py      the gated runner — start here
  scripts/update_prices.py     fetch; universe = roster ∪ everything in store
  scripts/analyze.py           builds the pack the analyst reads
  scripts/price_vs_position.py positioning vs cheapness (no LLM at run time)
  scripts/open_questions.py    computed shortlist — exists because a prose
                               summary once reported "nothing to do" with 9 leads
  scripts/fix_sector_labels.py revenue-based label corrections
  stocklab/fieldwatch.py       the five indicators and the score
  stocklab/data/live.py        PriceStore, fetching, validation
  stocklab/data/loaders.py     sanitize_corporate_actions (the crash/split judge)
  stocklab/fundamentals.py     point-in-time SEC XBRL (filed-date discipline is
                               clean — 456,379 points, 0 violations)
  docs/ANALYST_PROMPT.md       the desk-note brief
  docs/WEEKLY_PLAYBOOK.md      what a human does with the output
  briefings/                   dated outputs
```

---

## 11. If you change one habit, make it this

Do not report that something works because the code looks right. Run it, look at
what came out, and ask what it would have said on noise. Everything wrong in
this project passed code review and failed that test.
