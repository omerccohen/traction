# Data-layer audit — 2026-08-13

Scope: `stocklab/data/live.py`, `stocklab/data/loaders.py`, `stocklab/data/panel.py`,
`stocklab/fundamentals.py`, `scripts/update_prices.py`, `scripts/fetch_fundamentals.py`.

Everything below was executed against the real artifacts in this repo — the live
store at `data_cache/live` (3,498,085 rows, 2,992 tickers, 2018-01-02 → 2026-08-12)
and the SEC XBRL cache at `data_cache/xbrl` (646 tickers, 391,399 facts). No file
was modified. All output blocks are pasted verbatim from the commands shown.

Store snapshot the numbers were measured against: `prices.csv.gz` mtime 2026-08-12
22:36, 3,498,085 rows, 2,992 tickers, newest date 2026-08-12, 4.51% of tickers on that
newest date. Re-run after a successful refresh and the alignment figures in finding 6
will change; nothing else will.

The headline: **the price panel that every live-store backtest consumes is not
point-in-time.** Past prices are rewritten by future events, and the mechanism doing
the rewriting fires on genuine market crashes 87% of the time.

---

## 1. `sanitize_corporate_actions` rewrites past prices using future events, and deletes real crash returns

**What breaks** — Rule 2 ("NEGATIVE STEP") multiplies a ticker's *entire prior price
history* by `(1 + ret)` whenever it sees a one-day drop worse than -40%, and sets that
day's return to zero; 87% of the drops it fires on are genuine market moves, not data
errors, so real crashes are erased and five years of price levels are retroactively
rescaled by information from the future.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import pandas as pd
from stocklab.data.live import PriceStore
from stocklab.data.panel import long_to_panel
from stocklab.data.loaders import sanitize_corporate_actions
p = long_to_panel(PriceStore("data_cache/live").load())
raw = p.close["WAL"].loc["2023-03-08":"2023-03-14"]
psan, notes = sanitize_corporate_actions(p)
san = psan.close["WAL"].loc["2023-03-08":"2023-03-14"]
print(pd.DataFrame({"stored": raw, "stored_ret": raw.pct_change(),
                    "after_sanitize": san, "sanitized_ret": san.pct_change()}).to_string())
pit, _ = sanitize_corporate_actions(p.truncate_before("2023-03-10"))
d = pd.Timestamp("2023-03-09")
print(f"\nWAL close 2023-03-09 seen from 2023-03-10 : {pit.close.loc[d,'WAL']:.2f}")
print(f"WAL close 2023-03-09 seen from 2026-08-12 : {psan.close.loc[d,'WAL']:.2f}")
print(f"n prior-history rescales: {len([n for n in notes if 'distribution' in n])}")
PY
```

```
            stored  stored_ret  after_sanitize  sanitized_ret
date
2023-03-08   71.56         NaN       37.883000            NaN
2023-03-09   62.36   -0.128563       33.012631      -0.128563
2023-03-10   49.34   -0.208788       26.120000      -0.208788
2023-03-13   26.12   -0.470612       26.120000       0.000000
2023-03-14   29.87    0.143568       29.870000       0.143568

WAL close 2023-03-09 seen from 2023-03-10 : 62.36
WAL close 2023-03-09 seen from 2026-08-12 : 33.01
n prior-history rescales: 231
```

`WAL` is Western Alliance Bancorp and 2023-03-13 is the SVB/Signature bank run. The
raw store has the correct print. `sanitize_corporate_actions` classifies it as an
"un-adjusted distribution", sets the day's return to **exactly 0.0%**, and divides
every WAL close from 2018 through 2023-03-10 by 0.5294. The same date's close is
`62.36` if you look at it from 2023-03-10 and `33.01` if you look at it from today —
that is the definition of look-ahead.

The event is unmistakably a real market move in the store's own data:

```
             open    high     low  close       ret       $vol_M
2023-03-09  70.18  70.225  61.370  62.36 -0.128563   286.222048
2023-03-10  54.70  55.960  30.050  49.34 -0.208788  1217.043136
2023-03-13  12.89  30.780   7.460  26.12 -0.470612  1581.569918
2023-03-14  38.66  39.960  22.500  29.87  0.143568  1537.051954
  trailing 60d median dollar volume before the week: $57M
```

A $7.46 low against a $30.78 high on **28x** the normal dollar volume is a panic, not
a bad split row.

Classifying all 231 rescales by dollar-volume blow-out (a true split leaves dollar
volume unchanged; a crash multiplies it):

```
GENUINE MARKET MOVE (dollar volume blowout)    201
ambiguous                                       13
looks like a split/distribution                 10
```

Worst offenders by blow-out: `ALOY 2021-11-10 -47.2% (9367x)`, `BMNR 2025-07-09
-40.2% (2948x)`, `SBET 2025-06-13 -71.7% (1274x)`, `LUNR 2023-02-23 -75.2% (376x)`,
`QXO 2024-07-30 -80.1% (146x)`, `CAR 2026-04-23 -48.4% (48x)`.

**Impact** — measured on the real panel:

```
cells changed: 110627 of 3498085 observations = 3.16%
tickers affected: 208 of 2992
single-day crash returns erased: 232
mean erased return: -51.2%
(date,ticker) universe-membership decisions changed by the rescale: 11,613
tickers whose membership changes on at least one date: 70
observations on backtest_valuation's as_of grid: 157,087; with a look-ahead-rewritten price: 5,293 (3.37%)
```

Every consumer of the live store runs this: `backtest_fieldwatch.py:52`,
`backtest_valuation.py:70`, `backtest_positioning.py:112`, `backtest_improvement.py:138`,
`price_vs_position.py:112`, `journal.py:39`, `weekly_briefing.py:53`.

Three separate downstream numbers are wrong:

* **The left tail of every return distribution is gone.** 232 single-day returns
  averaging -51.2% are set to ~0. Drawdown, downside vol, short-leg P&L and any
  tail statistic computed on this panel are optimistic by construction.
* **Universe membership is decided with future information.** `eligibility_mask`'s
  `min_price >= 5.0` sees the rescaled level, so 11,613 (date, ticker) admit/evict
  decisions across 70 tickers were made using a crash that had not happened yet.
* **Valuation features are contaminated.** `backtest_valuation.py:90` feeds the
  sanitized price straight into `valuation_features` as the market-cap price while
  share counts come unrescaled from SEC filings:

  ```
  ticker      as_of  price_true  price_used  mcap_true_B  mcap_used_B   ey_true   ey_used   bp_true   bp_used
    MNST 2026-08-06       94.16       47.64        92.09        46.59  0.022065  0.043613  0.094767  0.187316
  ```

  Monster Beverage looks exactly **2x cheaper** than it was, on 3.37% of the
  backtest's observations.

**Severity: CRITICAL**

---

## 2. The live store has never recorded a single corporate action, and the settlement policy discards the vendor's own split correction

**What breaks** — The module docstring says splits are "captured into their own table
and applied EXACTLY at load time", but the only reachable source emits no actions, the
actions table does not exist, `apply_split_adjustments` is a proven no-op, and when the
vendor *does* send corrected split-adjusted history the store rejects it because the
settlement window measures calendar days and closes on a Friday print after one
trading day.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import json
from stocklab.data.live import PriceStore, apply_split_adjustments
from stocklab.data.panel import long_to_panel
s = PriceStore("data_cache/live")
print("corporate_actions.csv exists:", s.actions_path.exists(), "| action rows:", len(s.load_actions()))
runs = [json.loads(l) for l in open("data_cache/live/updates.log.jsonl")]
print("actions_recorded over all", len(runs), "runs:", sum(r.get("actions_recorded", 0) for r in runs))
p = long_to_panel(s.load())
p2, notes = apply_split_adjustments(p, s.load_actions())
print("apply_split_adjustments changed the panel:", not p2.close.equals(p.close), "| notes:", len(notes))
m = s.load(); m = m[(m.ticker == "MNST") & (m.date >= "2026-08-06")]
print(m.assign(ret=m.close.pct_change())[["date","close","volume","ret"]].to_string(index=False))
PY
```

```
corporate_actions.csv exists: False | action rows: 0
actions_recorded over all 9 runs: 0
apply_split_adjustments changed the panel: False | notes: 0
      date  close     volume       ret
2026-08-06 94.160  6468437.0       NaN
2026-08-07 90.360  8503246.0 -0.040357
2026-08-10 45.715 11944348.0 -0.494079
2026-08-11 45.530  9330761.0 -0.004047
```

`fetch_stockanalysis` (the only source that probes true — `stooq: false, yahoo: false`
in all 8 network runs) returns `actions = pd.DataFrame(columns=ACTION_COLUMNS)` at
`live.py:187`; `fetch_stooq` does the same at `live.py:91`. Only `fetch_yahoo` populates
the table and yahoo has never been the source used. So the "exact factor" path has
never carried a single row, and the "heuristic fallback" in finding 1 is in fact the
*only* mechanism — running on 100% of events instead of the residual it was designed for.

The store's own log recorded the correction arriving and being thrown away:

```
run 2026-08-11: conflicts=2 but status='updated' (exit 0, no alert)
   details: [{'date': '2026-08-07', 'ticker': 'MNST', 'stored': 90.36, 'incoming': 45.18, 'rel': 0.5},
             {'date': '2026-08-07', 'ticker': 'SCCO', 'stored': 199.06, 'incoming': 196.7, 'rel': 0.0119}]
```

`rel: 0.5` is the vendor restating Friday's close for a 2:1 split. `append()` refused
it. Why — `SETTLEMENT_DAYS = 3` is subtracted as *calendar* days:

```
SETTLEMENT_DAYS = 3 (documented as "rows younger than this are replaceable")

  newest=2026-08-03 (Mon)  settle_cut=2026-07-31  mutable trading days = 1  ['2026-08-03']
  newest=2026-08-04 (Tue)  settle_cut=2026-08-01  mutable trading days = 2
  newest=2026-08-05 (Wed)  settle_cut=2026-08-02  mutable trading days = 3
  newest=2026-08-06 (Thu)  settle_cut=2026-08-03  mutable trading days = 4
  newest=2026-08-10 (Mon)  settle_cut=2026-08-07  mutable trading days = 2  ['2026-08-07', '2026-08-10']
  newest=2026-08-11 (Tue)  settle_cut=2026-08-08  mutable trading days = 2  ['2026-08-10', '2026-08-11']

  settle_cut = 2026-08-11 - 3d = 2026-08-08  ->  08-07 < 2026-08-08 = True
  => SETTLED, stored value wins, correction discarded
```

The advertised 3-day settlement window is worth between **1 and 4 trading days**
depending on the weekday, and Monday's newest print freezes Friday after a single
trading day. `restate()` is the only escape and nothing calls it automatically.

**Impact** — 197 ratio-shaped one-day moves across 159 tickers sit in the panel with
no exact factor available. Every one of them is left to the 87%-false-positive
heuristic in finding 1, or (for positive moves — reverse splits — which rule 3
explicitly refuses to touch) left in the panel as a fake +100% return. `CRNX 2026-07-07
+98.7%`, `SHAZ 2025-12-04 +48.6%`, `SLAB 2026-02-04 +48.9%` are all still in the
returns series that feeds momentum, labels and field statistics.

**Severity: CRITICAL**

---

## 3. Market cap is `as-filed shares × today's price` with no staleness or split-consistency guard

**What breaks** — `valuation_features` multiplies whatever share count `latest_any`
last saw by the current price. Nothing checks how old that share count is, and nothing
reconciles it against splits that happened after the filing, so `earnings_yield`,
`book_to_price` and `sales_to_price` are wrong by whatever the share count has missed.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import pandas as pd, numpy as np
from pathlib import Path
from stocklab.data.live import PriceStore
from stocklab.fundamentals import load_facts, valuation_features, latest_any
close = PriceStore("data_cache/live").load().pivot_table(index="date", columns="ticker", values="close").ffill()
facts, asof = load_facts(Path("data_cache/xbrl")), "2026-08-11"
px = close.loc[pd.Timestamp(asof)]
rows = []
for t, fam in facts.items():
    if t not in px.index or not np.isfinite(px[t]): continue
    v = valuation_features(fam, asof, float(px[t]))
    if v is None: continue
    sh = latest_any(fam.get("shares", []), asof)
    rows.append(dict(ticker=t, price=round(float(px[t]),2), shares=sh["val"],
                     shares_filed=sh["filed"], mcap_B=round(v["market_cap"]/1e9,1),
                     earnings_yield=v["earnings_yield"]))
R = pd.DataFrame(rows); R["ey_rank"] = R.earnings_yield.rank(ascending=False)
print(R[R.ticker=="V"].to_string(index=False))
print(R.nlargest(8, "earnings_yield")[["ticker","shares_filed","mcap_B","earnings_yield"]].to_string(index=False))
R["age"] = (pd.Timestamp(asof) - pd.to_datetime(R.shares_filed)).dt.days
for thr in (120, 365, 1825): print(f"share count >{thr}d old: {(R.age>thr).sum()} of {len(R)}")
PY
```

```
ticker  price    shares shares_filed  mcap_B  earnings_yield  ey_rank
     V 362.82 469280842   2010-02-03   170.3        0.130597     15.0
ticker shares_filed  mcap_B  earnings_yield
  LYFT   2026-08-07     6.6        0.431603
   USO   2026-08-07     1.9        0.309950
  CHTR   2026-07-24    19.1        0.257521
   ALL   2026-08-05    66.3        0.200673
   AES   2026-08-04    10.5        0.178497
  AGNC   2026-07-31    12.9        0.175524
   GLD   2026-08-04   141.3        0.163986
   FIS   2026-08-04    22.1        0.152914
share count >120d old: 19 of 601
share count >365d old: 6 of 601
share count >1825d old: 4 of 601
```

Across all 646 cached tickers (not just the 601 that survive the feature gates) the
staleness is worse: 47 with a share count older than 120 days, 10 older than a year,
6 older than five years — `V` (2010), `BIDU` (2011), `VALE` (2013), `SEI` (2020),
`RACE` (2021), `WHD` (2021).

**Impact** — Visa's market cap is computed from its **2010** Class-A-only share count
(469.3M). Visa's real 2026 share count is ~1.94B after the 2015 4:1 split, so the
market cap is understated ~4.1x and the earnings yield is overstated ~4.1x: **13.06%**
instead of ~3.2%. That places Visa at **rank 15 of 601** on the "cheapest in the
universe" axis that `price_vs_position.py` prints as `cheap_pct`. `VALE` (2013 share
count) ranks 20/601 at 11.8%.

The split leg of the same bug is live today:

```
as_of 2026-08-07  price 90.36  shares=979,525,882 (filed 2026-08-07, end 2026-07-31)
   -> market_cap = $88.51B   earnings_yield=0.0240
as_of 2026-08-12  price 45.53  shares=979,525,882 (filed 2026-08-07, end 2026-07-31)
   -> market_cap = $44.60B   earnings_yield=0.0477
```

Monster's market cap halves and its earnings yield doubles overnight because it split
2:1 and the pre-split share count is still the newest one filed. No sanity gate catches
it: `earnings_yield` is gated at `(-2, 2)`, `book_to_price` at `(-5, 20)`.

The only guard in the code is `sh["val"] < 1e5`, which happens to fire on `SEI` (29,923
shares cached) and drops it — nothing else checks age or split consistency.

Two ETFs (`GLD`, `USO`) also appear with "earnings yields" of 16.4% and 31.0%; the
fundamentals universe is built by `liquid_universe()` purely on dollar volume with no
operating-company filter, despite the comment in `fetch_fundamentals.py:28` claiming
"liquid operating companies".

**Severity: HIGH**

---

## 4. Survivorship: 2 of 2,992 tickers stop trading in five and a half years

**What breaks** — Every row in the store was backfilled from a ticker list captured in
August 2026, so companies that were delisted, acquired or went bankrupt during the
sample simply do not exist. `meta.json` admits this in one line; the magnitude is that
the store has a measured attrition rate of **0.07%/yr against a real-world 4-8%/yr**.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import pandas as pd
from stocklab.data.live import PriceStore
df = PriceStore("data_cache/live").load()
fd, ld, mx = df.groupby("ticker")["date"].min(), df.groupby("ticker")["date"].max(), df.date.max()
print("tickers:", df.ticker.nunique(), "rows:", len(df), "range:", df.date.min().date(), "->", mx.date())
print("first-date year counts:\n", fd.dt.year.value_counts().sort_index().to_string())
dead = ld[ld < mx - pd.Timedelta(days=30)]
print("\ntickers that stop trading before the end of the sample:", len(dead)); print(dead.to_string())
print("\nrows dated before the first live update (2026-08-09):",
      f"{(df.date < pd.Timestamp('2026-08-09')).sum():,} / {len(df):,}")
b = pd.read_csv("data_cache/all_stocks_5yr.csv.gz")
old = set(b["Name"].dropna().unique()); live = set(df.ticker.unique())
print("2018 S&P constituents absent from the store:", len(old - live), "of", len(old))
PY
```

```
tickers: 2992 rows: 3498085 range: 2018-01-02 -> 2026-08-12
first-date year counts:
 date
2018      23
2021    2619
2022      45
2023      54
2024      78
2025      96
2026      77

tickers that stop trading before the end of the sample: 2
ticker
NVA    2026-06-02
NVRI   2026-05-29

rows dated before the first live update (2026-08-09): 3,492,179 / 3,498,085
2018 S&P constituents absent from the store: 101 of 505
```

Per-year attrition measured inside the store:

```
  2021:    23 tickers entering the year,  0 stop trading  -> 0.00%/yr
  2022:  2642 tickers entering the year,  0 stop trading  -> 0.00%/yr
  2023:  2687 tickers entering the year,  0 stop trading  -> 0.00%/yr
  2024:  2741 tickers entering the year,  0 stop trading  -> 0.00%/yr
  2025:  2819 tickers entering the year,  0 stop trading  -> 0.00%/yr
  2026:  2915 tickers entering the year,  2 stop trading  -> 0.07%/yr
```

**Impact** — 99.83% of the store's rows are backfilled survivor history. The usable
history for 2,619 of 2,992 names begins in 2021 (the vendor's `5Y` range), so the real
sample is 5.5 years in which nobody failed. At a conservative 5%/yr the store is missing
roughly **700-900 names** that should have stopped trading in it. 101 of the 505
February-2018 S&P 500 constituents (20%) are gone with no trace — `ALXN`, `ANTM`,
`ATVI`, `CELG`, `CERN`, `CHK`, `CTXS`, `CXO`, `DISH`, `ESRX`, `DFS`, `EA` and 89 more.
Their post-2018 returns, including the ones that went to zero, exist nowhere.

Long-side backtest returns are overstated and short-side returns understated by the
usual survivorship magnitude (literature: 1-4%/yr for a US equity universe). This is
unfixable from the current store; it needs a delisted-securities feed. The point of
quantifying it is that "audit note in meta.json" understates it — this is not a small
tilt, it is a universe with **zero** business failures.

**Severity: HIGH**

---

## 5. `improvement_features` never got the `quarterly_complete` fix — the Q4 hole is still there

**What breaks** — `quarterly_complete` was written to fill the missing Q4, but
`improvement_features` (the source of `rev_growth`, `rev_accel`, `margin`, `margin_chg`,
`margin_accel` — the entire IMPROVEMENT composite) still calls the naive `quarterly()`.
Only `valuation_features` was switched over. So on one observation in eleven, "this
quarter vs last quarter" silently spans two quarters.

**Repro**

```
$ cd /home/user/traction/stocklab && grep -n "quarterly(\|quarterly_complete(" stocklab/fundamentals.py \
    | grep -v "^33:\|^54:\|^63:"
```

```
126:    rev_q = quarterly(fam.get("revenue", []), as_of_iso)
141:    oi = {p["end"]: p["val"] for p in quarterly(fam.get("op_income", []), as_of_iso)}
175:    rev_ttm = ttm(quarterly_complete(fam.get("revenue", []), as_of_iso))
176:    ni_ttm = ttm(quarterly_complete(fam.get("net_income", []), as_of_iso))
```

Lines 126 and 141 are `improvement_features`; 175-176 are `valuation_features`. Only
the valuation half was migrated.

```
$ cd /home/user/traction/stocklab && python - <<'PY'
from pathlib import Path
from stocklab.fundamentals import load_facts, quarterly, quarterly_complete, improvement_features, year_ago, _d
facts = load_facts(Path("data_cache/xbrl"))
tot = gap = 0
for asof in ["2023-03-15","2023-08-15","2024-03-15","2024-08-15","2025-03-15","2025-08-15","2026-03-15","2026-08-11"]:
    for t, fam in facts.items():
        q = quarterly(fam.get("revenue", []), asof)
        if len(q) < 6: continue
        tot += 1
        if (_d(q[-1]["end"]) - _d(q[-2]["end"])).days > 140: gap += 1
print(f"observations feeding improvement_features: {tot:,}; where 'prev quarter' is >140d back: {gap:,} ({100*gap/tot:.1f}%)")
def complete(fam, asof):
    rq = quarterly_complete(fam.get("revenue", []), asof)
    if len(rq) < 6: return None
    cur, prev = rq[-1], rq[-2]; cy, py = year_ago(rq, cur), year_ago(rq, prev)
    if not cy or not cy["val"] or cur["val"] <= 0: return None
    g = cur["val"]/cy["val"] - 1
    gp = (prev["val"]/py["val"] - 1) if (py and py["val"]) else None
    return g, (g - gp) if gp is not None else None
d = [(t, a["rev_accel"], b[1]) for t, fam in facts.items()
     for a, b in [(improvement_features(fam, "2026-08-11"), complete(fam, "2026-08-11"))]
     if a and b and a["rev_accel"] is not None and b[1] is not None and abs(a["rev_accel"]-b[1]) > 1e-9]
print(f"tickers whose rev_accel changes if the Q4 hole is filled, as_of 2026-08-11: {len(d)}")
for t, a, b in d[:8]: print(f"  {t:6s} rev_accel {a:+.3f} -> {b:+.3f}")
PY
```

```
observations feeding improvement_features: 4,455; where 'prev quarter' is >140d back: 400 (9.0%)
tickers whose rev_accel changes if the Q4 hole is filled, as_of 2026-08-11: 123
  COF    rev_accel +0.041 -> +0.099
  DECK   rev_accel -0.014 -> -0.038
  CNP    rev_accel -0.070 -> -0.100
  MOD    rev_accel -0.025 -> -0.194
  CARR   rev_accel +0.091 -> +0.084
  SPGI   rev_accel +0.017 -> +0.014
  PPG    rev_accel +0.175 -> -0.741
  TTWO   rev_accel -0.229 -> -0.041
```

Concrete instances of the hole:

```
   AAPL   as_of 2023-03-15: prev=2022-06-25 cur=2022-12-31  gap=189d
   AVGO   as_of 2023-03-15: prev=2022-07-31 cur=2023-01-29  gap=182d
   BDX    as_of 2023-03-15: prev=2022-06-30 cur=2022-12-31  gap=184d
   FTS    as_of 2023-03-15: prev=2021-06-30 cur=2022-06-30  gap=365d
```

**Impact** — 9.0% of all `improvement_features` observations compute `rev_accel` and
`margin_accel` as the difference between two YoY growth rates measured **two quarters
apart** instead of one. At the current as-of date, **123 of 566** tickers (22%) get a
different `rev_accel` once the hole is filled, and some flip sign outright: PPG goes
from `+0.175` (accelerating) to `-0.741` (sharply decelerating). `rev_accel` is one of
the four IMPROV features z-scored into `z_IMPROVEMENT` in `backtest_valuation.py` and
into `IMPROVEMENT` / `improve_pct` in `price_vs_position.py`, so the composite the
ranking prints is wrong for roughly a fifth of the universe.

**Severity: HIGH**

---

## 6. The misalignment guard exists in exactly one of eight consumers

**What breaks** — `weekly_briefing.py` got a `MIN_ALIGNED_SHARE` guard after the
2026-08-12 partial refresh. The other seven live-store consumers call
`long_to_panel(store.load())` directly and silently price a "cross-section" from three
different trading days.

**Repro**

```
$ cd /home/user/traction/stocklab && grep -rn "MIN_ALIGNED_SHARE\|live-misaligned" --include=*.py .
scripts/weekly_briefing.py:39:MIN_ALIGNED_SHARE = 0.80      # share of tickers that must share the newest date
scripts/weekly_briefing.py:66:            if share < MIN_ALIGNED_SHARE:
scripts/weekly_briefing.py:73:                return panel, "live-misaligned", banner

$ grep -rn "long_to_panel(store.load())\|long_to_panel(df)\|long_to_panel(PriceStore" --include=*.py scripts/
scripts/price_vs_position.py:110:    panel = long_to_panel(store.load())
scripts/fetch_fundamentals.py:90:    p = long_to_panel(PriceStore(ROOT / "data_cache" / "live").load())
scripts/backtest_fieldwatch.py:50:    panel = long_to_panel(df)
scripts/backtest_valuation.py:68:    panel = long_to_panel(store.load())
scripts/weekly_briefing.py:51:        panel = long_to_panel(df)
scripts/backtest_positioning.py:110:    panel = long_to_panel(store.load())
scripts/backtest_improvement.py:136:    panel = long_to_panel(store.load())
scripts/journal.py:37:    p = long_to_panel(store.load())
```

Measured on the store as it stands (the pattern `s = close[t].loc[:as_of].dropna();
px = s.iloc[-1]` used by `price_vs_position.py:124`, `backtest_valuation.py:90`,
`backtest_positioning.py:134`, `backtest_improvement.py:167`):

```
as_of reported by every live script (panel.dates[-1]): 2026-08-12

### the price each script calls "as of 2026-08-12" ###
2026-08-12     125
2026-08-11    2583
2026-08-10     203
2026-08-07       2
2026-06-02       1
2026-05-29       1
  -> 95.7% of the cross-section is priced on an EARLIER day than the header claims
```

**Impact** — `price_vs_position.py` prints "# Positioning vs price — as of 2026-08-11"
(or -12) over a table where 95.7% of the prices are from a different day, with no
banner. `.dropna()` hides the misalignment rather than exposing it: instead of NaNs
that would be obvious, every name silently gets its own last good price. Any
cross-sectional z-score, percentile or ranking computed on that row mixes Monday,
Tuesday and Wednesday closes. Two names (`NVRI`, `NVA`) contribute prices that are
**75 and 72 days stale**.

The `--status` output confirms nothing surfaces this:

```
$ python scripts/update_prices.py --status
{
  "has_data": true,
  "newest_date": "2026-08-12",
  "n_tickers": 2992,
  "days_stale_calendar": 1,
  ...
}
```

**Severity: HIGH**

---

## 7. Silent failure paths: a broken refresh, a rejected split and a dropped row all exit 0

**What breaks** — Four distinct conditions that corrupt the store or the fundamentals
cache produce `status: "updated"` (or `"partial"`), exit code 0, and no alert.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import json
from pathlib import Path
from stocklab.fundamentals import load_facts, improvement_features
runs = [json.loads(l) for l in open("data_cache/live/updates.log.jsonl")]
last = runs[-1]
print(f"last run: status={last['status']} aborted={last['aborted_after_failures']} "
      f"updated={last['tickers_updated']}/{last['tickers_requested']} "
      f"appended={last['rows_appended']} restated={last['rows_restated']}")
for r in runs:
    if r.get("conflicts"): print(f"  conflicts={r['conflicts']} -> status='{r['status']}'")
    if r.get("problems"):  print(f"  problems={r['problems']} -> status='{r['status']}'")
files = sorted(Path("data_cache/xbrl").glob("*.json"))
empty = [f.stem for f in files if all(len(v)==0 for v in json.loads(f.read_text()).values())]
print(f"XBRL files where every family is empty (counted as fetched): {len(empty)} {empty}")
facts = load_facts(Path("data_cache/xbrl"))
n = sum(1 for f in facts.values() if improvement_features(f, "2026-08-11") is not None)
print(f"cached tickers {len(facts)}, producing features {n} -> {len(facts)-n} silently dropped")
PY
```

```
last run: status=partial aborted=True updated=174/2991 appended=307 restated=172
  problems=['dropped 1 implausible spike rows'] -> status='updated'
  problems=['dropped 1 implausible spike rows'] -> status='updated'
  conflicts=2 -> status='updated'
XBRL files where every family is empty (counted as fetched): 9 ['AZN', 'BN', 'BP', 'NU', 'NVO', 'RNW', 'SKHY', 'TBBB', 'TECK']
cached tickers 646, producing features 566 -> 80 silently dropped
```

1. **Aborted refresh still commits.** `update_from_network` breaks out of the fetch
   loop after 10 consecutive failures but falls straight through to `store.append(new)`
   with the partial `frames` (`live.py:565-576`). The 2026-08-12 run committed 307 rows
   for 174 of 2,991 tickers and left the store on four different dates.
   `update_prices.py:83-87` only calls `sys.exit(2)` for `status == "error"` — a
   `"partial"` run prints a warning and **exits 0**, so a cron job stays green.
2. **Settled-history conflicts never change status.** `rep.conflicts` is logged and
   ignored. The MNST 2:1 split rejection (finding 2) shipped as `status: "updated"`.
3. **`validate_rows` drops never change status.** `rep.problems` is logged and ignored.
4. **`fetch_fundamentals.py` writes empty caches as successes.** Nine tickers have
   every concept family empty because they file under IFRS tags outside `FAMILIES`
   (`AZN`, `BP`, `NVO`, `TECK`, ...). `dest.exists()` then makes them permanently
   `skipped` on every re-run. Another 39 have no revenue series at all. Net: **80 of
   646** cached tickers produce no features and vanish from every ranking with no
   message. `dest.write_text(...)` at `fetch_fundamentals.py:116` is also non-atomic,
   unlike `PriceStore._atomic_write`, so an interrupted fetch leaves a truncated JSON
   that will make `load_facts` raise for the whole cache.

**Severity: MEDIUM** (each is individually recoverable, but together they mean no
automated run can detect that the store is broken)

---

## 8. `update_from_csv` silently swaps the store's RAW-price regime for adjusted closes

**What breaks** — `live.py`'s docstring declares "CANONICAL REGIME = RAW PRINTS", but
the CSV ingestion path calls `_normalize_columns`, which *prefers* `Adj Close` over
`Close` and drops the raw column. A dropped yfinance-style export therefore writes
dividend-and-split-adjusted closes into a store that the rest of the system treats as
unadjusted.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import pandas as pd, tempfile, os, json
from stocklab.data.live import PriceStore, update_from_csv
tmp = tempfile.mkdtemp(); p = os.path.join(tmp, "drop.csv")
pd.DataFrame({"Date":["2024-01-02","2024-01-03"], "Symbol":["XYZ","XYZ"],
              "Close":[10.5,10.7], "Adj Close":[5.25,5.35], "Volume":[100,110]}).to_csv(p, index=False)
st = PriceStore(os.path.join(tmp, "store"))
rep = update_from_csv(st, p)
print(json.dumps({k: v for k, v in rep.to_dict().items()
                  if k in ("status","rows_appended","problems")}, default=str))
print(st.load().to_string(index=False))
PY
```

```
{"rows_appended": 2, "problems": [], "status": "updated"}
      date ticker  open  high  low  close  volume
2024-01-02    XYZ   NaN   NaN  NaN   5.25     100
2024-01-03    XYZ   NaN   NaN  NaN   5.35     110
```

Raw closes were 10.5 / 10.7; the raw-prints store now holds 5.25 / 5.35, with
`status: "updated"`, no entry in `problems`, and exit code 0.

**Impact** — Any CSV drop mixes regimes. When OHL columns are present the
`close < low * 0.98` check in `validate_rows` happens to catch it as a side effect;
when the CSV carries only `Close` + `Adj Close` + `Volume` (the most common yfinance
export) nothing catches it. Subsequent network refreshes of the same ticker will then
register the raw/adjusted gap as settled-history conflicts and the wrong value wins
(finding 2).

**Severity: MEDIUM**

---

## 9. The future-date guard admits tomorrow

**What breaks** — `validate_rows` computes `tomorrow = today + 1 day` and drops rows
where `date > tomorrow`, so a row dated tomorrow passes. The comment above it
(`live.py:248`) says a single future-dated row "permanently defeats the briefing's
freshness guard" — which is exactly what one day of slack still allows.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import pandas as pd
from datetime import datetime, timezone
from stocklab.data.live import validate_rows
t = pd.Timestamp(datetime.now(timezone.utc).date()) + pd.Timedelta(days=1)
rows = pd.DataFrame({"date":[t, t+pd.Timedelta(days=1)], "ticker":["ZZZ","ZZZ"],
                     "open":[10,10], "high":[10,10], "low":[10,10],
                     "close":[10.0,10.0], "volume":[1,1]})
out, probs = validate_rows(rows)
print("today:", datetime.now(timezone.utc).date())
print("submitted:", [str(x.date()) for x in rows.date])
print("kept     :", [str(x.date()) for x in out.date], probs)
PY
```

```
today: 2026-08-13
submitted: ['2026-08-14', '2026-08-15']
kept     : ['2026-08-14'] ['dropped 1 future-dated rows']
```

**Impact** — one bad vendor row dated tomorrow becomes the store's permanent
`newest_date`, making `freshness()` report `days_stale_calendar: -1` and every
`panel.dates[-1]` as-of date a day into the future. The store is append-only, so the
only repair is `restate()`. Low probability, permanent consequence.

**Severity: LOW**

---

## 10. `quarterly_complete` can emit the same quarter twice, one day apart

**What breaks** — `annual()` accepts any 350-380 day duration, which for a few filers
includes rolling TTM windows published inside 10-Qs. `quarterly_complete` derives a
"missing quarter" from each of them and keys the result on the exact `end` date, so the
same fiscal quarter can land in the series twice with ends a day apart.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
from pathlib import Path
from stocklab.fundamentals import load_facts, annual, quarterly_complete, _d
facts = load_facts(Path("data_cache/xbrl")); A = "2026-08-12"
for t in ["AMZN","GOOG","MSFT","JPM"]:
    a = annual(facts[t]["net_income"], A); y = len({p["end"][:4] for p in a})
    print(f'{t:5s}: {len(a)} "annual" periods over {y} years ({len(a)/y:.1f}/yr; a fiscal-year series is 1.0)')
for p in quarterly_complete(facts["AMZN"]["net_income"], A)[-8:-4]:
    print("  ", p)
tot = hit = 0; ov = 0
for t, fam in facts.items():
    for fn in ("revenue","net_income"):
        qc = quarterly_complete(fam.get(fn, []), A); tot += 1
        if any(0 < (_d(qc[i+1]["end"])-_d(qc[i]["end"])).days <= 5 for i in range(len(qc)-1)): hit += 1
        if len(qc) >= 4 and any((_d(qc[-4:][i+1]["start"])-_d(qc[-4:][i]["end"])).days < -2 for i in range(3)): ov += 1
print(f"series checked {tot}; containing duplicate quarters {hit} ({100*hit/tot:.1f}%); TTM windows with an overlapping pair {ov}")
PY
```

```
AMZN : 74 "annual" periods over 20 years (3.7/yr; a fiscal-year series is 1.0)
GOOG : 13 "annual" periods over 13 years (1.0/yr; a fiscal-year series is 1.0)
MSFT : 19 "annual" periods over 19 years (1.0/yr; a fiscal-year series is 1.0)
JPM  : 19 "annual" periods over 19 years (1.0/yr; a fiscal-year series is 1.0)
   {'start': '2024-09-30', 'end': '2024-12-31', 'filed': '2025-02-07', 'val': 20004000000, 'derived': True}
   {'start': '2024-10-01', 'end': '2025-01-01', 'filed': '2025-10-31', 'val': 20004000000, 'derived': True}
   {'start': '2025-01-01', 'end': '2025-03-31', 'filed': '2025-05-02', 'val': 17127000000}
   {'start': '2025-04-01', 'end': '2025-06-30', 'filed': '2025-08-01', 'val': 18164000000}
series checked 1292; containing duplicate quarters 47 (3.6%); TTM windows with an overlapping pair 1
```

AMZN Q4-2024 appears twice — `end 2024-12-31` and `end 2025-01-01`, both `$20.004B`.
Also note `gap_start` for a derived Q4 is set to the previous quarter's `end` rather
than `end + 1 day`, so 3,540 of 3,545 derived quarters overlap their predecessor by one
calendar day.

**Impact** — small in practice: only **1 of 1,167** TTM windows currently contains an
overlapping pair (`WAT revenue 2025-06-29..2025-09-27` vs `2025-07-01..2025-09-30`,
from the fiscal-calendar change). The `300 <= span <= 430` check in `ttm()` catches
most of it. But if the duplicate lands inside the trailing four, `ttm` double-counts one
quarter and omits another, and nothing reports it.

**Severity: LOW**

---

## 11. Silent drops in `long_to_panel` and `Panel.select`

**What breaks** — `long_to_panel` computes `dupes` at `panel.py:97`, drops the rows,
and never returns or logs the count. `Panel.select` filters unknown tickers out with no
report.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import pandas as pd
from stocklab.data.panel import long_to_panel
d = pd.DataFrame({"date":["2024-01-02"]*2, "ticker":["A","A"], "close":[10.0,99.0], "volume":[1,1]})
p = long_to_panel(d)
print("input rows", len(d), "-> panel cells", int(p.close.notna().sum().sum()), "kept", float(p.close.iloc[0,0]))
d2 = pd.DataFrame({"date":["2024-01-02"]*2, "ticker":["A","B"], "close":[10.0,20.0], "volume":[1,1]})
print("select(['A','B','GHOST']) ->", list(long_to_panel(d2).select(["A","B","GHOST"]).tickers))
PY
```

```
input rows 2 -> panel cells 1 kept 99.0
select(['A','B','GHOST']) -> ['A', 'B']
```

**Impact** — a source that emits two conflicting rows for the same (date, ticker) has
one silently chosen by row order, with no counter anywhere. `PriceStore.append`'s
assertion protects the store, but the panel builder is used directly on the bundled
CSV and any user CSV. Low frequency in the current data (0 duplicates in the live
store), but it is a data-integrity blind spot.

**Severity: LOW**

---

## 12. The universe source file is missing live large caps and contains ETFs

**What breaks** — `data_cache/universe/all_us_stocks.csv` (5,854 symbols, the source for
`universe_tickers.txt`) omits NYSE names that are current S&P 500 members, and no
dotted-class tickers exist anywhere in the store.

**Repro**

```
$ cd /home/user/traction/stocklab && python - <<'PY'
import pandas as pd
from stocklab.data.live import PriceStore
a = set(pd.read_csv("data_cache/universe/all_us_stocks.csv")["symbol"].astype(str))
u = set(s.strip() for s in open("data_cache/universe/universe_tickers.txt") if s.strip())
live = set(PriceStore("data_cache/live").load().ticker.unique())
for t in ["BK","CMA","BRK.B","BRK-B","BF.B","MMM","KO"]:
    print(f"  {t:6s} all_us_stocks={t in a}  universe={t in u}  store={t in live}")
print("  dotted/dashed tickers anywhere in the store:", [t for t in live if "." in t or "-" in t])
print("  ETFs in the store:", sorted(live & {"SPY","QQQ","GLD","USO","IWM"}))
PY
```

```
  BK     all_us_stocks=False  universe=False  store=False
  CMA    all_us_stocks=False  universe=False  store=False
  BRK.B  all_us_stocks=False  universe=False  store=False
  BRK-B  all_us_stocks=False  universe=False  store=False
  BF.B   all_us_stocks=False  universe=False  store=False
  MMM    all_us_stocks=True  universe=True  store=True
  KO     all_us_stocks=True  universe=True  store=True
  dotted/dashed tickers anywhere in the store: []
  ETFs in the store: ['GLD', 'QQQ', 'SPY', 'USO']
```

**Impact** — the "broad NYSE+Nasdaq+AMEX universe (liquid operating companies)"
described in `update_prices.py:35` excludes BNY Mellon and Comerica (both live, both
S&P 500) and every dual-class share class, while including four ETFs that then reach
`fetch_fundamentals.liquid_universe()` and produce nonsense fundamentals (`GLD`
earnings yield 16.4%, `USO` 31.0%, both in the top 8 "cheapest" — see finding 3). It is
a coverage gap in a data file rather than a code bug, but it silently shapes every
cross-section.

**Severity: LOW**

---

## Checked and CLEAN

Each of these was executed against the real caches and found correct.

**Point-in-time discipline in `fundamentals.py` — no `filed`-date leakage.** Every
returned point across `quarterly`, `annual`, `quarterly_complete`, `instant` and
`latest_any`, for 400 tickers × 4 as-of dates × 5 concept families:

```
tickers cached: 646
PIT filed<=as_of check: 456379 points checked, 0 violations
```

The `filed <= as_of_iso` string comparison is safe because all dates are ISO-8601
`YYYY-MM-DD`. 38 of 391,399 cached facts (0.010%) have `end > filed` — all cover-page
share counts and one stale `WMT` cash tag — and they cannot leak because `filed` still
gates them. **This is the most damaging class of bug and it is genuinely absent from
the fundamentals module.** The leakage in this codebase is in the *price* panel
(finding 1), not the filings.

**`quarterly_complete`'s Q4 reconstruction is arithmetically right.** 7,532 derived
quarters reconcile exactly to the filed annual against 11 failures (99.85%). Spot
checks against known filings:

```
AAPL revenue complete: ... ('2025-06-28', 94.0), ('2025-09-27', 102.5, 'D'), ('2025-12-27', 143.8) ...
   -> AAPL FY25Q4 revenue derives to $102.5B

AMZN net income TTM vs the filed fiscal-year figure:
  as_of 2025-02-20: ttm=59,248,000,000  (FY2024 filed annual = 59,248,000,000)  exact
  as_of 2025-06-01: ttm=65,944,000,000  (matches the filed 2024-04..2025-03 annual) exact
  as_of 2026-03-01: ttm=77,670,000,000  (FY2025 filed annual = 77,670,000,000)  exact
```

The 207 derived quarters that come out *negative* while their siblings are positive are
not errors — they are real Q4 losses the reconstruction correctly recovers
(`GOOG FY2017 Q4 = -$3.02B`, the Tax Cuts and Jobs Act charge; `FCX FY2008 Q4 =
-$13.98B`, the 2008 impairment; `COF FY2017 Q4 = -$971M`).

**`compact()`'s earliest-filed dedupe genuinely prevents restatement leakage.** The
cache holds exactly one point per `(start, end)` — the first-filed one — so
`quarterly()`'s `seen.setdefault` really does select first knowledge, and `instant()`'s
`(end, filed)` sort has nothing later to pick up.

**No NaN-sorting pattern anywhere in the data layer.** `live.py`, `loaders.py`,
`panel.py` and `fundamentals.py` contain zero `nlargest` / `nsmallest` / `sort_values`
/ `idxmax` calls over a cross-section. The only ranking-adjacent code is
`eligibility_mask`, which is NaN-safe by construction (`NaN >= 5.0` → `False`, and the
result is `&`-ed with `panel.close.notna()`). The `fieldwatch.py:196` fix
(`ffill(limit=3).pct_change(21).iloc[-1].dropna()`) is the only movers list and it is
correct.

**No off-by-one in the momentum window.** The `s.iloc[-1] / s.iloc[-127]` pattern used
by `backtest_positioning.py` and `backtest_improvement.py` on the per-ticker dropna'd
series:

```
tickers: 2915
calendar span of the "127 trading day" window: min=183d  p1=183d  median=183d  p99=185d  max=237d
tickers whose window is >210 calendar days: 2
```

127 trading days is a tight 183 calendar days for 99% of the universe. `pct_change(21)`
in `fieldwatch.py` operates on a date-indexed frame of trading days, so it is 21
trading days as intended.

**`validate_rows` spike detection and OHLC consistency work as designed.** The
two-day-reversal condition correctly keeps genuine crash-then-bounce sequences (WAL's
-47%/+14% pair survives), and the `close > high*1.02 | close < low*0.98` check fires on
adjusted-vs-raw mixing whenever OHL are present.

**`PriceStore` durability is sound.** `_atomic_write` (tmp + `os.replace`) and the
`fcntl.flock` read-modify-write lock are correctly implemented; there is no path that
leaves a half-written `prices.csv.gz`. `append()`'s `appended` / `restated` accounting
(`fresh_idx.difference(recent_ov)`) is arithmetically correct.

**Ticker-string handling is correct.** `converters={"ticker": str}` in
`PriceStore.load` preserves literal `"NA"`/`"NAN"` tickers; the store contains a real
`NAN` ticker and it survives the round-trip with zero null tickers.

**Timezone handling is consistent.** `fetch_yahoo` converts session-anchored epoch
timestamps through `America/New_York` before normalizing; `fetch_stockanalysis` and
`fetch_stooq` return naive dates; `validate_rows` normalizes everything with
`.dt.normalize()`; the store is uniformly `datetime64` naive. No tz-aware/naive
comparison exists in the merge path.

**Dividend non-adjustment is documented, not a bug.** `apply_split_adjustments`
deliberately filters `type == "split"` and the price-return regime is stated in both
`live.py:492` and `BUNDLED_BIASES[2]`.

**Test suite passes.** `python -m pytest tests/ -q` → `54 passed`.

---

## Not re-reported (known), with fix status

* **`--status` reports MAX date across tickers** — confirmed still unfixed;
  `freshness()` returns `days_stale_calendar: 1` while 203 tickers sit on 2026-08-10
  and two are 72+ days stale. Quantified under finding 6.
* **The 2026-08-12 partial refresh** — confirmed; the guard added in `6d3eec1` covers
  `weekly_briefing.py` only, and the aborted run still commits its partial batch and
  exits 0. See findings 6 and 7.
* **NaN-sorting promoted to top gainers** — the `fieldwatch.py` fix is correct and the
  pattern exists nowhere else in the data layer. See "Checked and CLEAN".
* **Q4 missing from SEC quarterly series** — `quarterly_complete` is arithmetically
  right (verified above), but `improvement_features` was never switched over to it. See
  finding 5.
