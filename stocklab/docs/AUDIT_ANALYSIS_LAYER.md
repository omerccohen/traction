# Audit — analysis / signal layer

**Scope:** `stocklab/fieldwatch.py`, `stocklab/analyst.py`, `stocklab/indicators/base.py`,
`stocklab/target_finder.py` (`member_moves`), `scripts/analyze.py`, `docs/ANALYST_PROMPT.md`.

**Method:** ran `scripts/analyze.py` against the live store on 2026-08-13, then re-derived every
intermediate with the same loaders (`weekly_briefing.load_panel` / `load_field_config`) so the numbers
below come from the same objects the pack is built from. Live artifact:
`briefings/analysis_pack_2026-08-12.json` (130 fields, universe 2 992, `source: "live-misaligned"`).
Nothing in the repo was modified except this file; `analysis_pack_2026-08-12.json` is the output the
mandated run wrote.

Findings are ordered most severe first.

---

## F1 — The pack shipped on a day when 4.5% of the universe had a price, and the warning that
## detected it was thrown away

**Severity: CRITICAL**

### What breaks

`weekly_briefing.load_panel()` has an alignment guard (lines 66-73). It fired. It returned
`source="live-misaligned"` plus a `banner` string explaining the problem. `scripts/analyze.py` line 32:

```python
panel, source, _banner = wb.load_panel()
```

The banner is bound to `_banner` and never used again. `source` *is* written into the pack — but
`docs/ANALYST_PROMPT.md` never mentions the `source` key, never lists `live-misaligned` as a value, and
gives the analyst no instruction to check it. The whole pack is then computed at
`as_of = panel.dates[-1]`, which is precisely the misaligned day.

`analyze.py` also has no equivalent of `weekly_briefing.py`'s staleness gate (lines 140-156). The
briefing refuses to write on bad data; the pack writes unconditionally and exits 0.

### Repro

```
$ python scripts/analyze.py
...
saved -> /home/user/traction/stocklab/briefings/analysis_pack_2026-08-12.json

$ python -c "import json; d=json.load(open('briefings/analysis_pack_2026-08-12.json')); print(d['source'], d['as_of'])"
live-misaligned 2026-08-12
```

Coverage of the panel that pack was built on:

```
source = 'live-misaligned'
banner = "> **PARTIAL DATA**: only 5% of tickers have the newest date (2026-08-12) — the last price
          refresh did not complete, so the store is misaligned and field statistics would compare
          different days. ..."

last 15 dates: n tickers with a price
  2026-08-06   2989 / 2992   (99.9%)
  2026-08-07   2990 / 2992   (99.9%)
  2026-08-10   2988 / 2992   (99.9%)
  2026-08-11   2783 / 2992   (93.0%)
  2026-08-12    135 / 2992   (4.5%)     <-- the pack's as_of

total universe dollar volume, last 8 dates:
  2026-08-10  $710.6B
  2026-08-11  $597.7B
  2026-08-12  $13.0B                    <-- 2% of a normal day
```

Per-field, on the as_of day:

```
fields: 130   median members 15   median PRINTING on as_of: 1
fields where <=2 members printed (cross-sectional std is over <=2 names): 105
fields where 0 or 1 member printed (std undefined/NaN): 87

top-6 fields and how many of them printed on as_of:
   Electric Utilities: Central [sub]          3/45 members printed
   Oil and Gas Field Machinery [sub]          0/12 members printed
   Utilities                                  6/108 members printed
   Food Chains [sub]                          0/9 members printed
   Advertising [sub]                          1/7 members printed
   Packaged Foods [sub]                       0/23 members printed
```

Rerunning the identical `field_snapshot` calls at 2026-08-12 / 08-11 / 08-10:

```
=== as_of 2026-08-12 ===   (4.5% coverage — what shipped)
  volume_influx pctile: median 0.167   <=0.10: 49/130   >=0.90: 1/130
  character census: {'DISPERSION': 51, 'MIXED': 36, 'QUIET': 25, 'STRESS': 8, 'VOLATILE': 8, 'MOMENTUM': 2}
  TOP 6: Electric Utilities: Central / Oil and Gas Field Machinery / Utilities /
         Food Chains / Advertising / Packaged Foods

=== as_of 2026-08-10 ===   (99.9% coverage — last clean day)
  volume_influx pctile: median 0.296   <=0.10: 30/130   >=0.90: 2/130
  character census: {'MIXED': 51, 'DISPERSION': 44, 'QUIET': 15, 'VOLATILE': 10, 'STRESS': 8, 'MOMENTUM': 2}
  TOP 6: Electric Utilities: Central / Oil and Gas Field Machinery / Utilities /
         Engineering & Construction / Finance/Investors Services / Farming/Seeds/Milling

Top-6 overlap 08-12 vs 08-10: 3/6
in 08-12 top6 but NOT 08-10 top6: ['Advertising [sub]', 'Food Chains [sub]', 'Packaged Foods [sub]']
in 08-10 top6 but NOT 08-12 top6: ['Engineering & Construction [sub]', 'Farming/Seeds/Milling [sub]',
                                   'Finance/Investors Services [sub]']

volume_influx pctile shift caused by including the 4.5%-coverage day (n=130):
  mean shift -0.080  median -0.077
    Garments and Clothing [sub]     p 84.5 -> p 59.1  (-0.254)
    Finance                         p 29.8 -> p  7.5  (-0.222)
    Consumer Staples                p 34.9 -> p 13.1  (-0.218)
    Real Estate                     p 46.0 -> p 27.0  (-0.190)
```

### Impact

Half the top-6 is an artifact of a failed price refresh. `dv = (close*volume).sum(axis=1)` treats a
missing print as zero dollar volume, so the 21d/126d ratio collapses market-wide: 49 of 130 fields land
at `volume_influx <= p10` versus 30 on the clean day, and `QUIET` ("activity draining — calm, being
ignored") is assigned to 25 fields instead of 15. Every one of the six top fields carries
`depressed: volume_influx` in its `flags`. The two fields ranked #2 and #4 (`Oil and Gas Field
Machinery`, `Food Chains`) had **zero** members with a price on the date the pack claims to describe.
`dispersion` for most fields is a cross-sectional std over ≤2 members on the final day, folded into the
21d mean (`Electronic Components [sub]` p75.8 → p98.4). Downstream, `find_targets.py`'s ordering guard
compares `pack["as_of"]` to `panel.dates[-1]` — both are the bad date, so the guard passes and the
target dossiers inherit the same day.

---

## F2 — The cohesion percentile counts NaN history windows as real comparisons; 33 fields get
## "p0, stocks decoupling" from **zero** valid comparisons

**Severity: CRITICAL**

### What breaks

`fieldwatch.py` lines 147-165. The history loop appends the mean of the upper triangle of a correlation
matrix:

```python
hist = []
for end in range(126, len(ret1) - 63, 21):
    sub = ret1.iloc[max(0, end - 63):end]
    if len(sub) >= 40:
        c = sub.corr().to_numpy()
        hist.append(c[np.triu_indices_from(c, 1)].mean())
if len(hist) >= 8:
    pct = float((np.array(hist) <= avg_corr_now).mean())
```

`sub.corr()` returns `NaN` for any pair without ≥2 overlapping observations, and `np.mean` propagates —
so **one** member without history in that window NaNs the **entire** window. Those NaNs are appended
anyway. Then:

* `len(hist) >= 8` — the guard added by the earlier F2 fix — counts NaN entries, so it passes on
  windows that contain no information at all.
* `np.array(hist) <= avg_corr_now` evaluates `NaN <= x` as `False`, i.e. every unusable window is
  silently scored as "history was **above** today", dragging the percentile toward 0.

The live panel makes this universal: it runs 2018-01-02 → 2026-08-12 but only ~22 tickers exist before
2021-08 (`dates with < 80% coverage: 902 of 2164`), and new listings keep arriving after that.

### Repro

```
field                                      cols  corr_now  nhist  nNaN  pct_CODE  pct_dropna  hist_med
------------------------------------------------------------------------------------------------------
Electric Utilities: Central [sub]            45     0.225     95    95     0.000         nan       nan
Utilities                                   108     0.206     95    95     0.000         nan       nan
Semiconductors [sub]                         74     0.547     95    95     0.000         nan       nan
Technology                                  412     0.153     95    95     0.000         nan       nan
Food Chains [sub]                             9     0.239     95    94     0.011       1.000     0.207
Packaged Foods [sub]                         23     0.243     95    92     0.032       1.000     0.161
Real Estate                                 148     0.288     95    94     0.011       1.000     0.273
Thematic Proxies                             20     0.317     95     0     0.074       0.074     0.433

fields with a cohesion indicator: 130
fields with >=1 NaN history point: 129
median NaN history points: 84.0  max: 95  (of n_hist median 95.0)

cohesion pctile as the CODE computes it:      <=0.10 : 88    >=0.90 : 0
cohesion pctile with NaN history DROPPED:     <=0.10 : 17    >=0.90 : 18
mean pctile shift from the NaN bug: +0.364   max: +0.989

fields where EVERY history point is NaN (pctile from 0 valid comparisons): 33 of 130
  Consumer Discretionary (592), Finance (510), Health Care (448), Technology (412),
  Industrials (384), Biotech: Pharmaceutical Preparations (204), Prepackaged Software (139),
  Energy (124), Industrial Machinery (115), Utilities (108), Basic Materials (93),
  Semiconductors (74), Oil & Gas Production (72), EDP Services (71), ...

mean n_nan by member-count bucket:
bucket  fields  mean_nan  mean_pct_code  frac_allnan
4-7         27    54.630          0.161        0.000
8-15        40    64.575          0.142        0.075
16-30       27    76.667          0.068        0.185
31-60       15    90.133          0.020        0.533
61+         21    94.190          0.002        0.810      <-- 81% of large fields are pure noise
```

Four fields have a NaN **current** correlation as well, and still get a confident p0 label:

```
Health Care                     score=0.581 cohesion={'value': nan, 'pctile': 0.0, 'note': 'stocks decoupling (idiosyncratic phase)'}
Basic Materials                 score=0.530 cohesion={'value': nan, 'pctile': 0.0, 'note': 'stocks decoupling (idiosyncratic phase)'}
Biotech: Pharmaceutical Prep    score=0.637 cohesion={'value': nan, 'pctile': 0.0, 'note': 'stocks decoupling (idiosyncratic phase)'}
Precious Metals [sub]           score=0.724 cohesion={'value': nan, 'pctile': 0.0, 'note': 'stocks decoupling (idiosyncratic phase)'}
```

Recomputing every character with the NaN history points dropped:

```
character census AS SHIPPED:                     {'DISPERSION': 51, 'MIXED': 36, 'QUIET': 25, 'STRESS': 8, 'VOLATILE': 8, 'MOMENTUM': 2}
character census WITH COHESION NaNs DROPPED:     {'MIXED': 48, 'QUIET': 38, 'VOLATILE': 22, 'DISPERSION': 12, 'STRESS': 8, 'MOMENTUM': 2}
fields whose character FLIPS: 39 / 130

cross_cutting AS SHIPPED (top-6):
  - Breadth: 4/6 top fields are in a stock-picker's phase (names decoupling) — a selection market, not a beta market.
  - Stress cluster: Electric Utilities: Central [sub], Food Chains [sub] under pressure together.
cross_cutting WITH COHESION FIXED:
  - Stress cluster: Electric Utilities: Central [sub], Food Chains [sub] under pressure together.
```

### Impact

Three separate harms, all reaching the desk note:

1. **Attention score inflation.** `score = mean(|pctile - 0.5| * 2)` — a cohesion pctile of 0.000
   contributes the maximum possible 1.0. For the 33 all-NaN fields, one fifth of the headline score is
   manufactured. Every one of the 11 GICS sectors is in that set.
2. **Systematic misclassification.** `stockpicker = disp_p >= 0.8 and coh_p <= 0.2` (`analyst.py:46`).
   With cohesion pinned near 0 the second clause is free, so DISPERSION is assigned 51 times instead of
   12 — a 4× over-count, and 39 of 130 fields carry the wrong character.
3. **A fabricated market-structure claim.** The `Breadth: ... a selection market, not a beta market`
   pattern (`analyst.py:157-160`) exists **only** because of this bug; it vanishes when the NaNs are
   dropped. It appeared in the shipped packs for 2026-08-11 and 2026-08-12, and the analyst prompt
   presents `cross_cutting` as a computed fact.

The pack also asserts the note `"stocks decoupling (idiosyncratic phase)"` for 88 of 130 fields. A
percentile that fires for two thirds of the market simultaneously is a regime statement, not the
field-specific unusualness the module docstring claims.

---

## F3 — `buried_moves` is not a mitigation for the averaging flaw: it covers one tail of one of five
## indicators, skips ranks 7-15, and silently truncates

**Severity: HIGH**

### What breaks

`scripts/analyze.py:89`:

```python
if i > 15 and (tr.get("pctile") or 0) >= 0.80 and s.name not in top_names:
```

Four independent gaps:

1. **One indicator of five.** Only `trend_21d` is checked. A field at p100 volatility, p100 dispersion,
   p0 volume_influx or p0 cohesion with a middling mean is caught by nothing.
2. **One tail.** `>= 0.80` only. A field having its *worst* 21-day stretch in a year (`pctile <= 0.20`)
   is not a buried move by this rule.
3. **Rank 7-15 hole.** `top_n=6` for the pack but the buried gate is `i > 15`. Ranks 7-15 are in neither
   list.
4. **Silent truncation.** `pack_dict["buried_moves"]["n"]` reports the full count; `["fields"]` is
   `buried[:12]`. The `note` says nothing about a cap.

### Repro

```
n fields = 130; top_fields = 6; buried_moves = 20
buried_moves SHIPPED to analyst (buried[:12]) = 12          <-- 8 dropped, "n": 20 still reported

BLIND GAP A: ranks 7-15
  rank   7  score 0.840  n=16   trend_p=0.933  ret21=0.0386  Finance/Investors Services [sub]   <== shown NOWHERE
  rank   8  score 0.823  n=10   trend_p=0.968  ret21=0.0855  Consumer Electronics/Appliances [sub]  <== shown NOWHERE
  rank  13  score 0.774  n=21   trend_p=0.968  ret21=0.1362  Professional Services [sub]        <== shown NOWHERE
  -> 3 of the 9 rank-7..15 fields have trend >= p80 and are shown NOWHERE

BLIND GAP B: trend pctile <= 0.20 outside top 6 (count = 12)
  rank  84  ret21 -0.1402  trend_p 0.004  n=6    Misc Health and Biotechnology Services [sub]
  rank  83  ret21 -0.0910  trend_p 0.079  n=14   Trucking Freight/Courier Services [sub]
  rank  12  ret21 -0.0712  trend_p 0.044  n=9    Farming/Seeds/Milling [sub]
  rank  36  ret21 -0.0679  trend_p 0.091  n=12   Memory/compute chain [custom]
  rank 126  ret21 -0.0553  trend_p 0.012  n=14   Power Generation [sub]
```

Largest 21-day moves that appear in neither list:

```
  rank  87 score 0.530 n=93   ret21 +0.1556 trend_p 0.76  Basic Materials
  rank  84 score 0.542 n=6    ret21 -0.1402 trend_p 0.00  Misc Health and Biotechnology Services [sub]
  rank  90 score 0.521 n=23   ret21 +0.1368 trend_p 0.65  Metal Mining [sub]
  rank  13 score 0.774 n=21   ret21 +0.1362 trend_p 0.97  Professional Services [sub]
  rank  51 score 0.643 n=15   ret21 +0.1209 trend_p 0.79  Clothing/Shoe/Accessory Stores [sub]
```

Note `Basic Materials +15.6%` at rank 87 — the same field the `buried_moves` code comment cites as the
motivating example. Its trend pctile is 0.76, four points under the 0.80 gate, so the mitigation written
for it does not catch it this week.

### Impact

The averaging flaw is only patched for high-trend fields ranked 16+. On this run 93 of 130 fields carry
at least one indicator past p90/p10 and appear in neither `top_fields` nor `buried_moves` — see the
table below. The analyst prompt (lines 44-53) tells the analyst that `buried_moves` is *the* correction
for the averaging problem, which overstates what the section does by roughly 5×.

---

## Fields invisible to both top_fields and buried_moves

Real data, `briefings/analysis_pack_2026-08-12.json`, 130 fields.
"Invisible" = not in `top_fields` (top 6) **and** not in the `buried_moves` detection set. The
comparison is generous: it uses all **20** detected buried fields, not the 12 actually shipped.
Visible union = **26 of 130 fields (20%)**.

| indicator | fields at pctile ≥0.90 | …invisible | fields at pctile ≤0.10 | …invisible | total extreme | **INVISIBLE** | worst invisible example |
|---|---|---|---|---|---|---|---|
| `trend_21d` | 15 | 3 | 11 | 8 | 26 | **11** | Misc Health and Biotechnology Services [sub] (p0, rank 84, score 0.54, −14.0%/21d) |
| `volatility` | 24 | 19 | 3 | 3 | 27 | **22** | Other Consumer Services [sub] (p100, rank 9, score 0.81) |
| `dispersion` | 38 | 27 | 5 | 4 | 43 | **31** | Other Consumer Services [sub] (p100, rank 9, score 0.81) |
| `volume_influx` | 1 | 1 | 49 | 39 | 50 | **40** | Energy (p0, rank 14, score 0.77, 124 names) |
| `cohesion` | 0 | 0 | 88 | 68 | 88 | **68** | Military/Government/Technical [sub] (p0, rank 11, score 0.80) |
| **any of the five** | | | | | 117 | **93** | |

Structural summary:

* **91** fields are extreme *only* on a non-trend indicator — `buried_moves` cannot reach them by
  construction. **82** of those are invisible.
* **117 of 130 fields (90%)** have at least one indicator past p90/p10. **93 (72%)** are shown nowhere.

Named examples of loud-but-invisible fields (pctiles: trend / volatility / dispersion / volume_influx / cohesion):

```
  rank   9 score 0.815 n=25   Other Consumer Services [sub]           0.099 0.996 1.000 0.714 0.074
  rank  11 score 0.795 n=30   Military/Government/Technical [sub]     0.750 0.948 0.821 0.032 0.000
  rank  14 score 0.767 n=124  Energy                                  0.706 0.833 0.881 0.004 0.000
  rank  15 score 0.767 n=74   Semiconductors [sub]                    0.198 0.909 0.710 0.004 0.000
  rank  16 score 0.752 n=8    Railroads [sub]                         0.210 0.889 1.000 0.806 0.105
  rank  20 score 0.733 n=115  Industrial Machinery/Components [sub]   0.381 0.845 0.968 0.099 0.000
  rank  24 score 0.725 n=14   Retail-Auto Dealers and Gas Stations    0.472 0.972 0.968 0.155 0.000
  rank  29 score 0.694 n=384  Industrials                             0.611 0.627 1.000 0.004 0.000
  rank  38 score 0.678 n=25   Auto Parts:O.E.M. [sub]                 0.540 0.321 0.992 0.016 0.000
```

`Semiconductors [sub]` — 74 names, volatility at p91 — is invisible to the desk note. So is `Energy`
(124 names) and `Industrials` (384 names, dispersion p100).

*Caveat, stated honestly:* the `cohesion` and `volume_influx` rows are inflated by F2 and F1
respectively. Even excluding both columns entirely, `volatility` + `dispersion` + `trend_21d` alone put
70 fields past p90/p10, of which **49 have no route into the pack**.

---

## F4 — `dislocations` can only ever see 4 stocks per field; 241 of 439 real 20% movers are
## structurally unreachable, and the hard `[:12]` cap was read as a census

**Severity: HIGH**

### What breaks

`fieldwatch.py:196-201` keeps only 2 worst + 2 best names per field. `analyst.py:180-197` then scans
*only that list* for `|21d| >= 0.20` and caps at `dislocations[:12]`. Worse, it re-parses the number out
of the display string:

```python
tkr, pct = m.rsplit(" ", 1)
val = float(pct.strip("%")) / 100
```

The string was produced by `f"{t} {m21[t]:+.0%}"` — zero decimal places. The pack's `move_21d` is
therefore a value rounded to the nearest percent, round-tripped through text, and the `>= 0.20` gate is
applied to the rounded number.

### Repro

```
=== DISLOCATIONS COVERAGE ===
universe names with |21d| >= 20% (same ffill(3)/pct_change(21) recipe): 439 of 2979
names reachable at all (2 worst + 2 best per field, 130 fields): 475 distinct
of the 439 real 20%+ movers, reachable by _cross_cutting: 198  -> INVISIBLE: 241
actually SHIPPED in pack['dislocations'] (hard cap [:12]): 12

biggest INVISIBLE dislocations (real, never reachable):
   BXC     +61.2%      HZO     +52.6%      BLKB    +52.0%      SLN     +50.5%
   XNCR    +47.8%      PAYC    +47.7%      ZBRA    +47.3%      TNDM    +46.8%
   ABCL    +44.8%      INTA    +43.9%

=== float -> '%s' -> float ROUND TRIP ===
  movers whose reported value differs from the real return by >0.4pp: 109
   DDS     real +0.2250  pack says +0.22   RBLX  real -0.3350  pack says -0.34
   TIC     real +0.4549  pack says +0.45   ASPN  real +0.1651  pack says +0.17
  names BELOW the 20% gate that round to '+/-20%' and would be admitted: 22
     ABX -19.93%, BILL +19.60%, BVS +19.81%, CDRE +19.94%, CLBK +19.88%, CSW +19.96% ...
```

Downstream consequence, from the shipped desk note `briefings/desk_note_2026-08-11_v2.md`:

> "Twelve names moved 64%+ in 21 days — know why if you hold them"

```
as_of 2026-08-11: real count |21d| >= 64%: 14
  AEHR BSP BXC CDNA EFOR FBRX FET LIFE MATV NEWP PLSE QMCO UTZ VREX
dislocations shipped: 12   min |move| in list: 0.64
```

BXC (+61%→ above the bar on 08-11), BSP and CDNA are missing from the pack. The analyst read the length
of a truncated list as a market statistic.

### Impact

`dislocations` is documented in `ANALYST_PROMPT.md` beat 4 as "big single-stock dislocations". It is in
fact "the twelve largest of the ≤4-per-field extremes", i.e. 45% of real 20% movers, capped, with values
rounded to the nearest whole percent. Names in no field at all (F9) can never appear. The pack carries
no `n_total` to signal truncation.

---

## F5 — `physical_proxies` measures a different window than the rest of the pack; 18 of 20 ETFs are
## quoted as of a day other than the pack's `as_of`

**Severity: HIGH**

### What breaks

`target_finder.member_moves` (lines 30-41) drops NaN *per ticker* before indexing:

```python
s = close[t].dropna()
...
"ret_21d": round(float(s.iloc[-1] / s.iloc[-1 - lookback[0]] - 1), 4),
```

so `lookback` counts that ticker's own available prints, not market days. `fieldwatch.field_snapshot`
uses the calendar-aligned `close.ffill(limit=3).pct_change(21).iloc[-1]`. Both numbers land in the same
pack. Because the as_of day is 95.5% empty (F1), essentially every ticker's window is shifted a row.

### Repro

```
Thematic Proxies field size: 20     ETFs declared in broad_sectors.csv: 20
of those present as a PRICE COLUMN in the panel: 20     MISSING from the price panel entirely: []
member_moves returned rows: 20 -> silently dropped: []

per-ETF last real print date used by member_moves:
   {'2026-08-11': 15, '2026-08-12': 2, '2026-08-10': 3}
  18/20 ETFs are quoted as of a DIFFERENT day than the pack's as_of 2026-08-12

SAME TICKER, TWO 21d NUMBERS IN THE SAME PACK (member_moves vs field_snapshot movers):
  tkr     member_moves   fieldsnap      diff
  COPX          0.1915      0.1254    0.0661
  REMX          0.0059     -0.0306    0.0365
  TAN          -0.0079     -0.0441    0.0362
  XME           0.1542      0.1284    0.0258
  SOXX         -0.0351     -0.0594    0.0243
  SLX           0.1105      0.0871    0.0234
```

Traced for COPX:

```
member_moves anchor:   iloc[-1] = 2026-08-11 88.59   iloc[-22] = 2026-07-13 74.35
field_snapshot anchor: idx[-1]  = 2026-08-12 88.59   idx[-22]  = 2026-07-14 78.72
```

Same end price, base date one row apart, +6.6pp difference on the headline physical cross-check.

`member_moves` also skips any name with fewer than `max(lookback)+1 = 64` prints, with no record:

```
universe 2992 -> member_moves returns 2954   SILENTLY DROPPED: 38
  AADX ADIG APMD ATTO BRVE BSP BXDC CBRS CSQR DPC EROC EROK FDXF FISN FRVO GMRS HONA IMC INIO IOND ...
```

BSP appears here *and* in the missing-dislocations list of F4 — a name that moved >64% in 21 days is
dropped by one path and unreachable by the other.

### Impact

`ANALYST_PROMPT.md` lines 17-25 instructs the analyst to "name the proxy's move when it corroborates a
field". The proxy move it names is measured over a longer, ticker-specific window than the equity field
it is corroborating, and is anchored to a different day. The 2026-08-11 desk note quotes
"copper miners +19.2%" against equity fields measured the other way — the comparison is not like-for-like.
On the `tracks` label: it is read from `data_cache/universe/broad_sectors.csv`, the same file used for
field membership, but the 20 ETF rows carry hand-authored pseudo-GICS strings (`'Copper Miners'`,
`'Aerospace & Defense ETF'`, `'Energy Sector'`) rather than real GICS metadata. The labels themselves are
accurate; the side effect is F9.

---

## F6 — `analyze.py` filters NaN scores in one ranking pass and not the other; a field with no
## computable score sorts to rank 1

**Severity: MEDIUM**

### What breaks

Three lines that disagree:

```
weekly_briefing.py:163   snaps = [s for s in snaps if s and np.isfinite(s.score)]
analyze.py:36            snaps = [s for s in snaps if s]                    # no isfinite filter
analyze.py:83            ranked_all = sorted([s for s in snaps if s and np.isfinite(s.score)], ...)
```

`build_analysis_pack` sorts the unfiltered list with `key=lambda s: -s.score`. NaN comparisons are all
False, so Python's sort leaves a NaN-scored field wherever it started — in practice, position 1.
`fieldwatch.py:188` produces exactly that score (`np.nanmean` of all-NaN pctiles) for a field whose
history is too short for any percentile.

### Repro

Real snapshot object, score replaced with the value `fieldwatch.py:188` yields when every pctile is NaN:

```
simulated snapshot score: nan  isfinite: False

analyze.py's build_analysis_pack ranking, positions 1-4:
   1. score=nan  Paper [sub] (NaN-score simulation)
   2. score=0.99  Electric Utilities: Central [sub]
   3. score=0.922  Oil and Gas Field Machinery [sub]

top_fields[0] emitted by the pack:
   {"name": "Paper [sub] (NaN-score simulation)", "attention": NaN, "character": "DISPERSION",
    "headline": "splitting into winners and losers (stock-picker's phase)", "trend_21d": 0.179}
   json.dumps of that attention value: NaN (non-strict JSON)

ranks used by buried_moves vs by top_fields differ for 130 of 130 positions
```

Today's live run has 0 NaN-score fields (`NaN/inf score snaps: 0`), so this is latent — it becomes live
the moment a new sub-industry crosses `min_members` with under 126 days of history, which the F1
coverage profile shows is routine for this store.

### Impact

Top slot given to a field with no measurable attention; `attention: NaN` written into the JSON, which
`json.dumps` emits as a bare `NaN` literal that strict JSON parsers reject; and `attention_rank` inside
`buried_moves` refers to a different ranking than the one that produced `top_fields`, so the "rank 25 of
130" numbers the analyst quotes are off by the number of NaN fields.

---

## F7 — The `character` classifier mixes raw returns with percentiles and turns on hard cutoffs that
## many fields sit within noise of

**Severity: MEDIUM**

### What breaks

`analyst.py:41-65`. `rising`/`falling` test the **raw 21-day return** against ±2%, while every other
input (`hot_vol`, `inflow`, `draining`, `stockpicker`) tests a **percentile**. A 2% move means something
different in Utilities than in Biotech, and the mixed basis means "unusual for this field" and
"directional" are decided on incompatible scales. The if-chain is first-match-wins with no tie-break,
and `MOMENTUM` requires `rising and inflow` — `inflow` needs `volume_influx >= 0.85`, which exactly
**one** field in 130 achieves this week.

### Repro

```
=== THRESHOLD KNIFE-EDGES (|x - cut| <= 0.02) ===
  hot_vol      volatility     cut 0.85: 7 fields within 0.02
                 Energy 0.833, Consumer Staples 0.869, Industrial Machinery 0.845,
                 Business Services 0.865, Memory/compute chain 0.869
  draining     volume_influx  cut 0.15: 12 fields within 0.02
  stockpicker  dispersion     cut 0.80: 7 fields within 0.02
  rising/falling trend_ret cut +/-0.02: 13 fields within 0.005
                 Semiconductors -0.0247, Consumer Staples +0.0189, Finance +0.0243,
                 Telecommunications +0.0189

=== rising/falling uses the RAW 21d return, everything else uses percentiles ===
  fields with an ORDINARY trend percentile (.35-.65) but |ret| > 2%
  (=> classifier treats them as rising/falling): 27
    p 38.1  ret +0.0278  Industrial Machinery/Components [sub]
    p 51.6  ret +0.0641  Electronic Components [sub]
    p 54.0  ret +0.0455  Auto Parts:O.E.M. [sub]
    p 51.6  ret +0.0648  Biotechnology: Biological Products [sub]

=== fields labelled QUIET or MIXED whose trend is at/above p90 or at/below p10 ===
  count = 9
    MIXED   trend p 99.2 ret +0.1625 score 0.625  Medical/Dental Instruments [sub]
    QUIET   trend p 94.0 ret +0.1528 score 0.606  Biotech: Electromedical Apparatus [sub]
    MIXED   trend p  0.4 ret -0.1402 score 0.542  Misc Health and Biotechnology Services [sub]
    QUIET   trend p 99.6 ret +0.1220 score 0.681  Cable & Other Pay Television Services [sub]
    QUIET   trend p 92.9 ret +0.0612 score 0.687  Investment Managers [sub]
```

`Energy` at volatility p0.833 misses `hot_vol` by 0.017; had it cleared, its `falling` test (+7.3%, so
false) would still route it away from STRESS, but the same 0.017 decides VOLATILE vs MIXED. Seven fields
sit that close.

### Impact

`ANALYST_PROMPT.md` line 62 explicitly instructs the analyst to de-prioritise a high-score field whose
character is QUIET. Four fields at trend p92-p99.6 are labelled QUIET or MIXED this week, so that
instruction actively suppresses the largest moves in the book. Combined with F2, 39 of 130 characters are
wrong outright. The thresholds carry no derivation anywhere in the repo (`docs/PREREGISTRATION.md` covers
the macro indicator thresholds, not these).

---

## F8 — "Confirmed field-level move" fires on a sub-industry and the sector that contains it

**Severity: MEDIUM**

### What breaks

`analyst.py:165-178` looks for two classified fields whose base names are substrings of one another and
both STRESS, then asserts:

> `"Confirmed field-level move: '{A}' and '{B}' both stressed — a real sector signal, not one-name noise."`

Substring matching on names is precisely what pairs a sector with its own sub-industry, and a
sub-industry's members are a subset of its sector's members. Confirming a sector move with a subset of
the same stocks is circular.

### Repro

```
pairs the substring rule treats as 'related fields': 11
...of which one field is a COMPLETE SUBSET of the other: 4
  overlap  100%  Finance (510) <-> Finance: Consumer Services [sub] (66)
  overlap  100%  Finance (510) <-> Finance/Investors Services [sub] (16)
  overlap  100%  Finance (510) <-> Finance Companies [sub] (10)
  overlap  100%  Real Estate (148) <-> Real Estate Investment Trusts [sub] (129)
  overlap   96%  Utilities (108) <-> Electric Utilities: Central [sub] (45)
  overlap   64%  Telecommunications (53) <-> Telecommunications Equipment [sub] (45)
  overlap    0%  Major Banks [sub] (149) <-> Banks [sub] (6)
  overlap    0%  Real Estate Investment Trusts [sub] (129) <-> Real Estate [sub] (26)
  overlap    0%  Commercial Banks [sub] (31) <-> Banks [sub] (6)
```

The rule is wrong in both directions: `Real Estate Investment Trusts` ⊃ 129 of `Real Estate`'s 148 names
would be called "confirmation", while `Major Banks` and `Banks` share **zero** members yet also match the
substring test. It did not fire on 2026-08-12 only because `Utilities` classified DISPERSION rather than
STRESS — and F2 shows that classification is itself wrong.

`Utilities` and `Electric Utilities: Central` occupied slots 1 and 3 of `top_fields` this week; the
2026-08-11 desk note already noticed the double-count by hand ("the parent field is carried by the same
two names as its children") without the pack flagging it.

### Impact

A latent false "independent confirmation" claim, aimed at exactly the hierarchical pairs the field map
guarantees will co-move. No overlap check exists anywhere in `_cross_cutting`.

---

## F9 — Exception swallowing: a failed section becomes an empty section, and a downstream script
## converts the failure into a positive claim

**Severity: MEDIUM**

### What breaks

`analyze.py:71-72` and `106-107` write `{"error": str(e)}`. Nothing reads that key.

### Repro

```
pack with a failed physical_proxies: {"physical_proxies": {"error": "data_cache/universe/broad_sectors.csv"}}

scripts/open_questions.py line 125 does:
    for mv in pack.get("physical_proxies", {}).get("movers", []):
  -> yields: []   (empty list, NO complaint)

grep for any consumer that inspects an 'error' key in the pack:
    scripts/open_questions.py:125:    for mv in pack.get("physical_proxies", {}).get("movers", [])
    scripts/find_targets.py:79:       inp["physical_proxies"] = {"n": len(recs), "movers": recs}
    docs/ANALYST_PROMPT.md:17         **Physical cross-check.** The pack includes a `physical_proxies` section
    docs/ANALYST_PROMPT.md:44         **Check `buried_moves` before you finalise your themes.**
  -> no consumer checks for 'error'; ANALYST_PROMPT.md gives the analyst no instruction for a missing section.
```

`open_questions.py` then reaches its `else` branch and prints:

> *"None — every large physical move has a corresponding equity field drawing attention."*

A crash is rendered as a verified all-clear.

A second, quieter path needs no exception at all — `analyze.py:55` guards with `if etfs:`:

```
analyze.py:  etfs = fields.get('Thematic Proxies', []);  if etfs: ...
  resulting pack keys: []   <- 'physical_proxies' absent, exit code still 0
```

If the ETF rows ever leave `broad_sectors.csv`, or the sector is renamed, the key is not written at all —
no error, no log line, exit 0 — while `ANALYST_PROMPT.md` still promises the section exists.
`find_targets.py` has an explicit STALE-PREREQUISITE guard for pack *age* (lines 45-65) but none for pack
*completeness*.

### Impact

The two sections that the prompt file singles out as mandatory reading are also the two that can vanish
silently. `find_targets.py` exits 3 on a stale pack but 0 on a hollow one.

---

## F10 — `_trailing_pctile` has no tie handling, cannot return 0, accepts half a window, and reports a
## percentile for a stale value when the current one is NaN

**Severity: LOW**

### What breaks

`fieldwatch.py:81-87`:

```python
def _trailing_pctile(series: pd.Series, window: int = 252) -> float:
    s = series.dropna()
    if len(s) < window // 2:
        return np.nan
    w = s.iloc[-window:]
    return float((w <= w.iloc[-1]).mean())
```

Four separate issues, none individually fatal:

### Repro

```
  self-inclusion: series 0..299, last value is the max -> 1.0
  last value is the strict MINIMUM -> 0.003968  (cannot reach 0.0; floor = 1/252)
  perfectly FLAT series (no information) -> 1.0        <-- reads as p100
  126 points (the minimum accepted, window//2) -> pctile computed over 126 points, returns 0.429
  125 points -> nan
  series 0..1 then a trailing NaN: iloc[-1] is NaN, but _trailing_pctile returns 1.0
      <- percentile OF YESTERDAY, paired with value=NaN by the caller
```

* **No midrank.** `(w <= last)` resolves ties to the *highest* rank, so an indicator that has not moved
  reads p100, never p50. `indicators/base.py:212` already fixed this for the macro layer
  (`((window < val).mean() + (window <= val).mean())/2`, "audit F15"); `fieldwatch.py` was never updated.
* **Self-inclusion.** The current point is inside its own comparison window, so the floor is 1/252 and
  the scale is asymmetric (max extremeness 1.000 on the high side, 0.992 on the low side).
* **Half a window accepted.** The docstring and `briefing()` present these as 252-day percentiles;
  126 observations suffice.
* **Stale-value percentile.** `dropna()` before `iloc[-1]` means the reported pctile can describe a value
  from a previous day while the caller writes `round(float(x.iloc[-1]), 4)` = NaN into `value`.

The window is recomputed from scratch on every call — nothing is fitted once and reused, and no future
data enters, so the point-in-time claim in the module docstring holds. Overlapping windows mean a
"252-point" trend percentile rests on ~12 independent 21-day blocks, but a Monte Carlo shows the marginal
rate is still calibrated (see *Checked and CLEAN*).

### Impact

Mild upward bias in every field's score. Combined with F2's exact-0.000 cohesion, `score` is not
symmetric around 0.5 in the way `mean(|pctile − 0.5| × 2)` assumes.

---

## F11 — Field membership: 4 panel names belong to no field, 12 belong to three, and 20 ETFs sit in the
## universe as if they were companies

**Severity: LOW**

### Repro

```
=== FIELD MEMBERSHIP CENSUS ===
panel tickers: 2992   rows in broad_sectors.csv: 2991
panel tickers NOT in the sector CSV (=> in NO field at all): 4 ['CBOE', 'NVR', 'QQQ', 'SPY']
tickers appearing in >=1 field: 2988      panel tickers in ZERO fields: 4
membership multiplicity: {1: 106, 2: 2870, 3: 12}
tickers in >=3 fields: AAPL AMAT AMD HPQ INTC KLAC LRCX MU NVDA STX TXN WDC
sum over fields of n_members = 5882 vs universe 2992 -> average ticker counted 1.97 times

base-name COLLISIONS in the target-finder roster:
  {'Real Estate': ['Real Estate', 'Real Estate [sub]']}
  roster passed to the target-finder strips suffixes: 129 names for 130 fields
```

* **CBOE and NVR** are real operating companies in the price panel that appear in no field and therefore
  in no snapshot, no mover list, and no dislocation — permanently invisible to the analysis layer.
  `QQQ`/`SPY` being unmapped is harmless.
* **12 semiconductor names** sit in sector + sub-industry + the custom `Memory/compute chain`, so a move
  in NVDA is counted three times across the ranking; `_cross_cutting` dedupes by ticker (`seen`) but
  attributes each to whichever field ranked first.
* **`Real Estate` vs `Real Estate [sub]`** collide once suffixes are stripped
  (`target_finder.build_target_input:108`), so the roster the target-finder agent picks from has 129
  entries for 130 fields and one ambiguous name.
* The 20 ETFs are rows in `broad_sectors.csv`, so they are counted in `universe_size: 2992` (the prompt
  describes this as "~2,900 NYSE+Nasdaq **companies**") and they surface from
  `keyword_universe_search`, which searches only the GICS Sub-Industry column because the CSV has no
  `Name` column:

```
broad_sectors.csv columns: ['Symbol', 'GICS Sector', 'GICS Sub-Industry']
  ai_power_datacenter: 114 hits, 3 of them ETFs ['URA', 'NLR', 'XLE']
  sub-industries matched: Construction/Ag Equipment/Trucks, Electric Utilities: Central,
    Electrical Products, Energy Sector, Engineering & Construction, Nuclear Energy,
    Power Generation, Uranium & Nuclear Fuel
```

`'Energy Sector'`, `'Nuclear Energy'` and `'Uranium & Nuclear Fuel'` are the ETF pseudo-labels, so the
value-chain pull returns 3 ETFs alongside 111 companies with no marker distinguishing them.

### Impact

Small but real: two large caps are unanalysable, semiconductor names are triple-weighted in the ranking,
and the target-finder can be handed an ETF as a "company most exposed to the thesis".

---

## F12 — Small-n fields: the floor is 5 members and a 7-name field ranked #5 this week

**Severity: LOW**

### What breaks

`fields.yml` sets `min_members: 5`; `load_field_config` clamps to `max(3, …)`; `build_fields` applies
that only to **sub-industries** (custom fields need 3, sectors have no floor at all) and
`field_snapshot` returns `None` below 3 columns. Nothing scales the score, the percentile, or the
`character` by member count, and nothing in the pack tells the analyst how thin a field is beyond
`n_members`.

### Repro

```
=== SMALL-n FIELDS ===
   n   score  char        trend_p  vol_p disp_p  coh_p vinf_p  field
   5   0.393  QUIET        0.528  0.516  0.020  0.495  0.048  Other Metals and Minerals [sub]
   5   0.370  QUIET        0.417  0.571  0.306  0.421  0.004  Building Products [sub]
   5   0.585  DISPERSION   0.333  0.952  0.972  0.168  0.540  Integrated Freight & Logistics [sub]
   5   0.532  MOMENTUM     0.667  0.488  0.774  0.042  0.921  Movies/Entertainment [sub]
   5   0.674  STRESS       0.194  0.972  0.921  0.495  0.020  Water Sewer Pipeline Comm & Power Line Construction [sub]
   5   0.662  DISPERSION   0.496  0.968  0.806  0.095  0.028  Meat/Poultry/Fish [sub]
   5   0.636  QUIET        0.790  0.206  0.448  0.042  0.004  Specialty Foods [sub]
   6   0.542  MIXED        0.004  0.464  0.667  0.126  0.782  Misc Health and Biotechnology Services [sub]
   6   0.635  QUIET        0.591  0.274  0.774  0.000  0.004  Agricultural Chemicals [sub]

fields with <=7 members: 27 of 130
  best rank achieved by a <=7-member field: 5
  mean score <=7 members: 0.520  vs >=30 members: 0.660
  smallest sector field (no minimum applies): 20 ('Thematic Proxies')
```

The #5 field on the pack this week is `Advertising [sub]`, 7 members, with the top-2/bottom-2 movers
`CRTO -23%, GRPN -13%, IBTA +21%, WPP +48%` — the mover list *is* four sevenths of the field. Its
dispersion p99 is a cross-sectional std over 7 names. `Water Sewer Pipeline …` with 5 members carries
`STRESS` at score 0.674 (rank 40) on the strength of volatility p97 over five stocks.

### Impact

The score is comparable across fields by construction (all percentiles) but its *reliability* is not, and
nothing in the pack or the prompt reflects that. Mean score does trend the other way (0.52 for ≤7 vs 0.66
for ≥30), so small fields are not systematically loud — but a 5-name field can and does reach the top
quartile on one indicator computed over 5 observations.

---

## Checked and CLEAN

* **Data-quality census arithmetic (`analyst.py:110-127`).** Verified against the registry:
  `live=2 stale=3 missing=7 sum=12 vs n_inds=12`. Every indicator lands in exactly one bucket; the
  bucket test (`age is None or latest_value is None` → missing; `age > 45` → stale; else live) matches a
  hand-recomputation for all 12. The `warning` key fires (`len(live) <= 2`) and its counts —
  "only 2 of 12 … (7 unavailable, 3 stale)" — are all correct. `STALE_AFTER_DAYS = 45` is well chosen
  for the mix: `sp500_trend_12m` at 43d stays live, the three 1 077-day series are all named as stale
  with their ages.
* **`regime.valuation` is not silently laundered.** `sp500_pe10` appears in `regime.valuation` despite
  being 1 077 days old, but it carries `age_days: 1077` in the same dict and is listed in
  `data_quality.stale`. `ANALYST_PROMPT.md` lines 34-42 instruct the analyst to check the age, and the
  2026-08-11 desk note did exactly that ("CAPE 30.81, **1,076 days old** … Ignore it entirely").
  Working as designed.
* **Indicator staleness note is frequency-aware.** `base.py:234` (`expected_lag = 2.5*365/ppy + 15`)
  correctly flags the three monthly series as `STALE (1077d old vs ~91d expected)` without flagging
  `sp500_trend_12m` at 43d.
* **Registry load-time validation.** `load_registry` dry-runs every threshold rule through `parse_rule`
  and refuses a missing or future `registered_on`; all 12 indicators pass.
* **Percentile point-in-time discipline.** `_trailing_pctile` is recomputed from scratch on each call
  over a trailing slice only; no parameters are fitted once and reused, and no observation after the
  slice endpoint enters. `field_snapshot(as_of=…)` truncates `close`/`volume`/`news_net` before any
  computation. No look-ahead found.
* **Percentile marginal calibration.** Despite the 21-day overlap, the trend percentile is not inflated
  in the marginal sense — 2 000 iid-Gaussian synthetic fields gave
  `P(trend pctile >= 0.90) = 0.105` against a nominal 0.10. The overlap caveat is about *effective
  sample size* (~12 independent months behind a "252-day" percentile), not about a false-positive rate.
* **The cohesion history windows do not overlap the current window.** `range(126, len(ret1)-63, 21)`
  with `sub = ret1.iloc[end-63:end]` ends at most at index `len-64`, while `avg_corr_now` uses
  `ret1.iloc[-63:]`. The earlier "audit F2" self-comparison fix is correct — the defect in F10 above is
  the NaN accounting, not the windowing.
* **Movers list NaN handling.** `close.ffill(limit=3).pct_change(21).iloc[-1].dropna()` behaves as its
  comment claims: no not-yet-reported name was promoted into a mover list on this run, and the
  `len(m21) >= 4` guard prevents duplicate picks on tiny fields.
* **`build_fields` sub-industry counting.** `sub.reindex(mapped).value_counts()` with
  `n >= min_members` reproduces exactly; `broad_sectors.csv` has 0 duplicate symbols and 0 NaN sector or
  sub-industry cells, so no garbage field names are produced.
* **`load_field_config` never raises.** Verified it returns `(fields, warn)` with the documented
  defaults; `min_members = max(3, …)` and the sectors/subindustries gates resolve consistently
  (the earlier "audit F10" fix holds).
* **Pack JSON is strict-parseable on this run.** `analysis_pack_2026-08-12.json` contains no `NaN`
  literal — though F6 shows the path that would introduce one.
* **`find_targets.py` stale-prerequisite guard.** Correctly compares `pack["as_of"]` against the live
  data date and exits 3 rather than writing a stale dossier. (It does not check pack *completeness* —
  see F9.)

---

*Audit run 2026-08-13 against the live store. All numbers reproduced from
`briefings/analysis_pack_2026-08-12.json` and re-derivations using the same loaders. No repository file
was modified except this document; the pack JSON is the artifact written by the mandated
`scripts/analyze.py` run.*
