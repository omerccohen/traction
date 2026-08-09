# News & Sentiment Data Sources — what actually works (live-probed)

*Every reachability claim here was tested with a real HTTP request from this
environment on **2026-08-09**, not assumed. Where a source needs content (not
just a 200), the payload was validated too. Re-run `scripts/probe_sources.py`
to refresh — the shared-egress IP means "reachable" can flip week to week.*

---

## Plain-language bottom line

We wanted to know: **can news, social sentiment, or search-attention make the
system smarter?** Two honest answers, kept separate:

1. **For *pointing research* (what the whole system does): yes, a few of these
   help.** They tell you *where the crowd and the filings are pointing* — which
   is exactly the "attention" job FieldWatch already does, just with new inputs
   beyond price. The best additions are **SEC filings** (hard facts: who filed
   an 8-K, who's buying insider stock) and **Wikipedia page-views** (the
   cleanest free "how much is the public suddenly looking at this?" meter).

2. **For *predicting direction* (which way a stock goes next): no.** This is the
   same wall we already proved with price. Public sentiment is already in the
   price by the time we can read it. Measured forward information coefficient
   (IC) of published sentiment is ~0.01–0.03 and decays within days — real but
   too small and too fast to trade in liquid names, and it does **not** survive
   costs. So we use these as **attention/evidence inputs, never as buy signals.**

**The single highest-leverage idea needs no new plumbing:** fetch a handful of
**thematic / commodity ETFs** (uranium, semis, copper, oil, defense, lithium…)
through the price adapter we already have. They are the market's own real-time
vote on physical supply/demand — the exact thing the desk note keeps asking
about ("is the power/chip/copper shortage real?"). Verified working below.

---

## Reachability table (live, 2026-08-09)

| Source | Status | Keyless? | History? | What it gives | Verdict |
|---|---|---|---|---|---|
| **SEC EDGAR** (submissions + full-text search) | ✅ 200 | yes | full | Every 8-K/13D/Form 4, keyword-searchable | **USE — tier 1** |
| **Wikipedia pageviews** (Wikimedia REST) | ✅ 200 | yes | since 2015 | Daily public-attention counts per topic | **USE — tier 1** |
| **FINRA RegSHO** (daily short volume) | ✅ 200 | yes | daily files | Per-symbol short vol (12,175 rows/day) | **USE — tier 2** |
| **Thematic/commodity ETFs** (via our adapter) | ✅ 200 | yes | 5y+ | Physical supply/demand proxy prices | **USE — tier 1 (free)** |
| **StockTwits** (symbol stream) | ✅ 200 | yes | forward-only | Crowd Bull/Bear tags (11B/3B on NVDA now) | USE — accumulate |
| **Google News RSS** + FinBERT | ✅ 200 | yes | forward-only | Headlines to score for tone (102 items) | USE — explanatory |
| **GDELT** (global news volume) | ⚠️ 200 but flaky | yes | 2015+ | Field-level news-volume timelines | Best-effort only |
| **Reddit** (r/stocks json) | ❌ 403 | — | — | Retail chatter | **Blocked** |
| **Google Trends** | ❌ 400/429 | — | — | Search interest | **Blocked** (token wall) |
| **Yahoo Finance RSS** | ⚠️ intermittent | yes | — | Headlines | Flaky (shared IP 429s) |
| **Twitter / X** | ❌ paid | no | — | Firehose | Not available |

> Note vs. earlier notes: GDELT and Yahoo returned **429** on an earlier probe
> and **200** today. That's the shared-egress IP getting rate-limited, not a
> permanent block — treat both as *unreliable*, cache what you get, never
> block the pipeline on them.

---

## Tier-1: use these first (robust, keyless, backfillable)

### 1. SEC EDGAR — the hard-facts layer
The desk note keeps asking questions like *"is UTZ a real deal or a rumor?"* or
*"who's actually buying the power names?"* EDGAR answers them with **primary
documents**, not chatter.

- **Filing stream per company:** `https://data.sec.gov/submissions/CIK{10-digit}.json`
  → every filing with date + type. An **8-K burst** (sudden cluster of 8-Ks in a
  field) is a real "something happened here" flag. **Form 4** clusters = insiders
  buying/selling.
- **Full-text search:** `https://efts.sec.gov/LATEST/search-index?q="data center"&forms=8-K`
  → directly turns an analyst question into a list of filings. This is how you
  *confirm* a thesis instead of guessing (it's exactly what the target-finder did
  to verify the Utz/Intersnack take-private and CEG's PPAs).
- **Why tier 1:** keyless, rock-solid, fully historical (backfill years), and it
  is *evidence*, not sentiment — no IC-decay problem because we don't trade it,
  we cite it.
- **Etiquette:** send a real `User-Agent` with contact email; stay ≤10 req/s.

### 2. Wikipedia pageviews — the cleanest attention meter
`https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{Article}/daily/{start}/{end}`

- Verified: 39 daily points for "Nvidia" in one call, real counts (6,540→4,651).
- **Full history since 2015** → unlike social feeds, you can **backtest** it.
- Best free stand-in for Google Trends (which is walled). A sudden pageview
  spike on a company/technology/commodity page = the public just turned to look.
- Map each field to a few anchor articles (e.g. power field → "Data center",
  "Nuclear power", "Electrical grid") and track the field's attention that way.

### 3. Thematic / commodity ETFs — physical supply/demand, **free, already wired**
This is the highest-leverage, lowest-effort addition. The desk note's core
questions are physical: *is there really a power shortage? a chip glut? a copper
squeeze?* An ETF that holds the physical thing (or its miners/producers) is the
market pricing that shortage in real time. **All fetch through the price adapter
we already have** — verified 2026-08-09, 130 rows each, current:

| ETF | Reads out | ETF | Reads out |
|---|---|---|---|
| **URA** | uranium / nuclear fuel | **XLE** | energy sector |
| **SOXX** | semiconductors | **ITA** | defense / aerospace |
| **COPX** | copper miners | **JETS** | airlines |
| **USO** | crude oil | **LIT** | lithium / battery |
| **GLD** | gold / risk-off | **TAN** | solar |

Add these as regular tickers in the universe and FieldWatch treats them as
"fields" for free — a physical-world cross-check on every equity thesis, with
**zero new code**.

---

## Tier-2: useful, with caveats

- **FINRA RegSHO daily short volume** — keyless daily text files, one row per
  symbol (verified 12,175 rows for 2026-08-06). Rising short-volume share into a
  falling field = crowded-short / squeeze setup. T+1, backfillable. Good *context*,
  weak *predictor*.
- **Google News RSS + FinBERT** — 102 headlines per query, keyless. Score tone
  with a finance-tuned model (FinBERT) to get a field-level "tone" number. This
  is **explanatory only** — it tells you *why* a field is hot, not where it goes.
  Feeds the existing `news_tone` / `news_intensity` hooks in `fieldwatch.py`.
- **StockTwits** — keyless crowd Bull/Bear tags (live NVDA: 11 bullish / 3
  bearish / 16 untagged). **Forward-only** — no history, so you must start
  logging now and let it accumulate before it's backtestable.

## Blocked / not worth it right now
- **Reddit** (403), **Google Trends** (token wall / 429), **Twitter/X** (paid).
  Wikipedia pageviews replaces Trends; the rest aren't worth fighting the IP block.
- **GDELT / Yahoo RSS** — intermittent (see note above). Best-effort, cache-first,
  never a hard dependency.

---

## The honest predictive caveat (why none of this is a buy signal)

Published sentiment/attention has, in every credible study and in our own price
work, a **tiny and fast-decaying** edge: rank-IC ~0.01–0.03 that is mostly gone
within a few days and **arbitraged away in liquid names** — the ones we cover.
By the time a headline or a bullish-tag is public, the price already moved.

So the rule is unchanged from the rest of the system:
> **These are attention and evidence inputs. They point research. They never
> say "buy."** We use them to answer *"where should a human look, and is the
> story real?"* — not *"what goes up next?"*

---

## Recommended integration order (cheapest real value first)

1. **Thematic/commodity ETFs into the universe** — 1 line each, free, immediate
   physical cross-check. *(Do first.)*
2. **Wikipedia pageviews → a field-attention indicator** — backfillable, so it's
   testable against the 2-year backtest.
3. **SEC 8-K/Form-4 burst detector → an evidence flag on the desk note** — turns
   "something's happening" into "here's the filing."
4. **Google News + FinBERT tone** into the existing `news_tone` hook — explanatory
   color on flagged fields.
5. **Start logging StockTwits + FINRA short-volume now** so they're backtestable
   in a few months.

*Footer: reachability is live-probed and dated; predictive claims are deliberately
conservative and match what the price work already proved. Nothing here upgrades
the system from "where to look" to "what to buy." — StockLab, 2026-08-09.*
