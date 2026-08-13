# Audit — backtest / evidence layer

Scope: `scripts/backtest_{fieldwatch,positioning,improvement,valuation}.py`,
`scripts/{horizon,combination}_sweep.py`, `experiments/PREREGISTER_improvement.md`,
`docs/BACKTEST_*.md`.

Method: every number below was produced by executing the code in this repo on
this repo's data on 2026-08-13. All four backtests were re-run end to end
(`python scripts/backtest_*.py`); the experiment artifacts were then restored to
their committed state with `git checkout -- experiments/`, so every repro command
in this document runs against the *committed* rows files and reproduces the
*documented* numbers exactly before showing the correction.

The overlapping-window artifact already documented in `docs/CONSISTENCY_TEST.md`
is not re-reported. Finding 8 covers where that same overlap still contaminates
t-stats and effective sample size elsewhere.

**Headline:** the FieldWatch layer is honest and reproduces. The fundamental
layer (`positioning` / `improvement` / `valuation`) is built on a universe
selected with 2026 information, and **every one of its headline results
disappears when the universe is chosen point-in-time** — including the one the
project calls "the first genuinely positive, pre-registered result."

---

## 1. The backtest universe is chosen using data from the end of the sample

**What breaks** — `fetch_fundamentals.liquid_universe()` picks the 600 most
liquid names over the **last 252 days of the price store** (2025-08 → 2026-08)
and that fixed list is then applied back to 2018, so a name enters the 2022
backtest *because* it became liquid after a 2025 price explosion.

```python
# scripts/fetch_fundamentals.py:89-92
def liquid_universe(n: int) -> list[str]:
    p = long_to_panel(PriceStore(ROOT / "data_cache" / "live").load())
    dv = (p.close * p.volume).tail(252).median().sort_values(ascending=False)
    return list(dv.dropna().index[:n])
```

Dollar volume is price × shares, so the selection criterion *is* the outcome
variable. QBTS had $3.3M/day of volume and ranked 2190th of 2992 in mid-2024; it
sits in the 2022–2026 backtest because it ranks 141st today.

**Repro**

```
$ python - <<'EOF'
import sys, pandas as pd, numpy as np
sys.path.insert(0,'.')
from scipy import stats as sstats
from stocklab.data.live import PriceStore
from stocklab.data.panel import long_to_panel
from stocklab.backtest.metrics import newey_west_tstat
p=long_to_panel(PriceStore('data_cache/live').load())
pit=(p.close*p.volume).rolling(252,min_periods=200).median()   # liquidity KNOWN at each date
df=pd.read_csv('experiments/valuation_backtest_rows.csv',parse_dates=['as_of'])
piv=pit.stack().rename('pit_dv').reset_index(); piv.columns=['as_of','ticker','pit_dv']
df=df.merge(piv,on=['as_of','ticker'],how='left')
print("below the $150M/day the docs claim:", round(100*(df.pit_dv<150e6).mean(),1),"pct")
print("below $25M/day at the as-of date:", round(100*(df.pit_dv<25e6).mean(),1),"pct")
def dectab(d,sig='z_VALUE',tgt='fwd_126'):
    r=[]
    for _,g in d[['as_of',sig,tgt]].dropna().groupby('as_of'):
        if len(g)<40: continue
        g=g.copy(); g['dec']=pd.qcut(g[sig],10,labels=False,duplicates='drop')
        r.append(g.groupby('dec')[tgt].mean())
    return pd.DataFrame(r)
for lbl,d in [("AS SHIPPED",df),("PIT SCREEN >= $150M/day at as_of",df[df.pit_dv>=150e6])]:
    T=dectab(d); m=(T.mean()*100).round(1)
    print(lbl,"->",list(m.values),"| cheapest-priciest",round(m.iloc[9]-m.iloc[0],1),"pts")
def ic(d,sig,tgt='fwd_126'):
    a,i=[],[]
    for d0,g in d.groupby('as_of'):
        gg=g[[sig,tgt]].dropna()
        if len(gg)>=20 and gg[sig].nunique()>5:
            r=sstats.spearmanr(gg[sig],gg[tgt]).statistic
            if np.isfinite(r): a.append(r); i.append(d0)
    return pd.Series(a,index=pd.DatetimeIndex(i))
for s in ['sn_LEVELS','sn_IMPROV_VALUE','sn_VALUE','sn_IMPROVEMENT','z_mom','z_ALL']:
    a=ic(df,s); b=ic(df[df.pit_dv>=150e6],s)
    print("%-18s ship %+.4f t %+.2f | PIT %+.4f t %+.2f"%(s,a.mean(),newey_west_tstat(a,3),
                                                          b.mean(),newey_west_tstat(b,3)))
EOF
below the $150M/day the docs claim: 24.7 pct
below $25M/day at the as-of date: 3.9 pct
AS SHIPPED -> [22.6, 12.0, 9.3, 12.2, 14.6, 11.2, 10.9, 10.9, 8.9, 14.6] | cheapest-priciest -8.0 pts
PIT SCREEN >= $150M/day at as_of -> [10.2, 7.7, 7.6, 7.3, 9.4, 8.1, 7.1, 6.1, 7.2, 13.3] | cheapest-priciest 3.1 pts
sn_LEVELS          ship -0.0531 t -3.15 | PIT -0.0221 t -0.91
sn_IMPROV_VALUE    ship +0.0453 t +2.73 | PIT +0.0361 t +1.44
sn_VALUE           ship +0.0514 t +2.21 | PIT +0.0537 t +1.67
sn_IMPROVEMENT     ship +0.0179 t +1.93 | PIT +0.0009 t +0.07
z_mom              ship +0.0799 t +2.86 | PIT +0.0434 t +1.38
z_ALL              ship +0.0905 t +3.51 | PIT +0.0620 t +1.83
```

The as-shipped column reproduces `docs/BACKTEST_VALUATION.md` to the last digit,
including its decile table. The screen applied is the one the docs *claim* the
universe already satisfies ("592 most-liquid US names (median >$150M/day)") —
in fact 24.7% of the observations were below that line at their own as-of date.

**This is not a sample-size effect.** Dropping the same 31% of rows at random,
200 times, leaves every t-stat where it was:

```
$ python - <<'EOF'   # placebo control (abridged; full script in the repro above + random mask)
...
sn_LEVELS          placebo t  mean -3.09  5-95pct [-3.71,-2.60]   ACTUAL under PIT screen: -0.91
sn_IMPROV_VALUE    placebo t  mean +2.66  5-95pct [+2.18,+3.25]   ACTUAL under PIT screen: +1.44
z_mom              placebo t  mean +2.83  5-95pct [+2.52,+3.11]   ACTUAL under PIT screen: +1.38
z_VALUE spread     placebo    mean -0.0823  5-95pct [-0.1036,-0.0624]  ACTUAL under PIT: +0.0317

the COMPLEMENT (only observations that FAIL the PIT liquidity screen):
  sn_LEVELS          IC -0.1299  t -4.67
  sn_IMPROV_VALUE    IC +0.0291  t +1.49
  z_mom              IC +0.0622  t +2.46
  z_VALUE spread     -0.4292 per 6mo
```

Every observed value sits far outside the placebo's 5–95% band. The entire
effect lives in the sub-$150M/day tail — the part of the universe that only
exists in the sample because of what happened later.

**Impact**
- "Levels sort backwards: IC −0.053, t −3.15" → **−0.022, t −0.91.** Not significant.
- "Positioning + price: +0.045, t 2.73" → **+0.036, t 1.44.** Fails the
  pre-registered |t| ≥ 2 bar, so **H2 is not supported**, contradicting
  `docs/BACKTEST_VALUATION.md`.
- "IMPROVEMENT (sector-neutral) +0.018, t 1.93" → **+0.001, t 0.07.** Gone.
- "Momentum +0.080, t 2.88, held-out +0.081" → **+0.043, t 1.38.**
- Decile spread −8.0 pts → **+3.1 pts** (see finding 2).

**Severity: CRITICAL**

---

## 2. "IC positive but decile spread negative" is an artifact, not a phenomenon

**What breaks** — `docs/BACKTEST_VALUATION.md` Result 2 ("rank-IC said yes, the
money said no", "anyone reporting only the IC here would announce an edge that
lost money") rests on a single arithmetic mean that flips sign under a
point-in-time universe, flips sign on the median, flips sign geometrically, and
is 52% produced by 76 observations of 22 illiquid names counted six times each
through overlapping windows.

**Repro**

```
$ python - <<'EOF'
import sys, pandas as pd, numpy as np
sys.path.insert(0,'.')
from stocklab.data.live import PriceStore
from stocklab.data.panel import long_to_panel
p=long_to_panel(PriceStore('data_cache/live').load())
pit=(p.close*p.volume).rolling(252,min_periods=200).median()
df=pd.read_csv('experiments/valuation_backtest_rows.csv',parse_dates=['as_of'])
piv=pit.stack().rename('pit_dv').reset_index(); piv.columns=['as_of','ticker','pit_dv']
df=df.merge(piv,on=['as_of','ticker'],how='left')
sub=df[['as_of','ticker','z_VALUE','fwd_126','pit_dv']].dropna(subset=['z_VALUE','fwd_126'])
parts=[]
for _,g in sub.groupby('as_of'):
    if len(g)<40: continue
    g=g.copy(); g['dec']=pd.qcut(g['z_VALUE'],10,labels=False,duplicates='drop'); parts.append(g)
sub=pd.concat(parts)
per=sub.groupby(['as_of','dec'])['fwd_126'].mean().unstack(); d=per[9]-per[0]
g0,g9=sub[sub.dec==0]['fwd_126'],sub[sub.dec==9]['fwd_126']
print("arithmetic mean of per-date spreads ",round(100*d.mean(),1),"pts   <- THE DOC'S NUMBER")
print("median of per-date spreads          ",round(100*d.median(),1),"pts")
print("geometric (mean log return)         ",round(100*(np.expm1(np.log1p(g9).mean())-np.expm1(np.log1p(g0).mean())),1),"pts")
print("5pct-winsorized stock returns       ",round(100*(g9.clip(*np.percentile(g9,[5,95])).mean()-g0.clip(*np.percentile(g0,[5,95])).mean()),1),"pts")
print("dates where cheap beat pricey       ",round(100*(d>0).mean()),"pct")
print("dates where PRICIEST decile was best",int((per.idxmax(axis=1)==0).sum()),"of",len(per))
print("dates where CHEAPEST decile was best",int((per.idxmax(axis=1)==9).sum()),"of",len(per))
print("priciest decile mean",round(100*g0.mean(),1),"pct  MEDIAN",round(100*g0.median(),1),"pct  skew",round(g0.skew(),1))
big=sub[(sub.dec==0)&(sub.fwd_126>2)]
print("the",len(big),"obs above +200pct contribute",round(100*big.fwd_126.sum()/len(g0),1),"of those",round(100*g0.mean(),1),"pts")
print("their PIT liquidity: median $",round(big.pit_dv.median()/1e6,1),"M/day;",int((big.pit_dv<150e6).sum()),"of",int(big.pit_dv.notna().sum()),"below $150M")
print(big.ticker.nunique(),"distinct names counted",len(big),"times:", ", ".join(sorted(big.ticker.unique())))
EOF
arithmetic mean of per-date spreads  -7.9 pts   <- THE DOC'S NUMBER
median of per-date spreads           1.8 pts
geometric (mean log return)          1.9 pts
5pct-winsorized stock returns        -3.7 pts
dates where cheap beat pricey        53 pct
dates where PRICIEST decile was best 11 of 47
dates where CHEAPEST decile was best 16 of 47
priciest decile mean 23.0 pct  MEDIAN 4.2 pct  skew 4.8
the 76 obs above +200pct contribute 12.0 of those 23.0 pts
their PIT liquidity: median $ 35.5 M/day; 64 of 74 below $150M
22 distinct names counted 76 times: AAOI, AFRM, ALAB, APLD, AXTI, CIFR, CRDO, CVNA, IONQ, LITE,
NVTS, ONDS, PL, PLTR, QBTS, QUBT, RGTI, RKLB, SMR, SNDK, SOUN, WULF
```

So the answer to the project's strangest claim: the IC and the spread are not
telling contradictory truths about the same investable universe. They are
measuring different universes. The rank IC is a broad statistic that survives
the illiquid tail; the arithmetic decile mean is a point estimate that 3% of the
positions own, and those positions are *precisely* the ones that only exist in
the sample because of look-ahead selection. The cheapest decile is the
best-performing decile more often (16 dates) than the priciest one (11 dates).

**Impact** — `docs/BACKTEST_VALUATION.md` Result 2 is wrong as an inference. The
corrected statement: in the universe the doc claims to test, cheap beat expensive
by **+3.1 points per 6 months**, not lost to it by 8. The sentence "Anyone
reporting only the IC here would announce an edge that lost money" should be
"anyone reporting only the arithmetic mean of an unscreened universe would
announce a loss that never existed."

**Severity: CRITICAL**

---

## 3. The corporate-action table does not exist, so real crashes are silently zeroed

**What breaks** — `data_cache/live/corporate_actions.csv` was never written, so
`apply_split_adjustments()` is a no-op on every backtest. The only remaining
defence is the heuristic in `sanitize_corporate_actions()`, whose rule 2 treats
*any* one-day drop worse than −40% as an unadjusted distribution and rescales
prior history so the event-day return becomes **0%**. Checked against SEC share
counts, 17 of the 18 verifiable repairs are real crashes, not splits.

**Repro**

```
$ python - <<'EOF'
import sys, re, json, pandas as pd, numpy as np
from pathlib import Path
sys.path.insert(0,'.')
from stocklab.data.live import PriceStore, apply_split_adjustments
from stocklab.data.loaders import sanitize_corporate_actions
from stocklab.data.panel import long_to_panel
store=PriceStore('data_cache/live')
print("corporate_actions.csv exists:",store.actions_path.exists(),"| rows:",len(store.load_actions()))
panel=long_to_panel(store.load())
p2,split_notes=apply_split_adjustments(panel,store.load_actions())
p3,notes=sanitize_corporate_actions(p2)
print("exact split factors applied:",len(split_notes))
neg=[n for n in notes if 'step treated as un-adjusted' in n]
print("heuristic 'negative step' repairs (event-day return forced to 0):",len(neg),
      "across",len({n.split()[0] for n in neg}),"tickers")
XB=Path('data_cache/xbrl'); rows=[]
for n in neg:
    t,d=n.split()[0],n.split()[1].rstrip(':')
    f=XB/f"{t}.json"
    if not f.exists(): continue
    sh=[p for p in json.loads(f.read_text()).get('shares',[]) if p.get('end')]
    b=[p for p in sh if p['end']<d]; a=[p for p in sh if p['end']>d]
    if not(b and a): continue
    bv=sorted(b,key=lambda p:p['end'])[-1]['val']; av=sorted(a,key=lambda p:p['end'])[0]['val']
    ret=float(re.search(r'([-+][\d.]+)%',n).group(1))/100
    rows.append({'ticker':t,'date':d,'ret':ret,'shares_ratio':av/bv if bv else np.nan,'implied':1/(1+ret)})
R=pd.DataFrame(rows); R['is_split']=(R.shares_ratio/R.implied).between(0.85,1.18)
print("checkable against SEC share counts:",len(R),
      "| REAL SPLIT:",int(R.is_split.sum()),"| REAL CRASH wrongly zeroed:",int((~R.is_split).sum()))
print(R[~R.is_split][['ticker','date','ret','shares_ratio']].to_string(index=False))
EOF
corporate_actions.csv exists: False | rows: 0
exact split factors applied: 0
heuristic 'negative step' repairs (event-day return forced to 0): 231 across 193 tickers
checkable against SEC share counts: 18 | REAL SPLIT: 1 | REAL CRASH wrongly zeroed: 17
ticker       date    ret  shares_ratio
  APLD 2022-06-13 -0.526      1.649810
  BMNR 2025-07-09 -0.402     54.541567
  CIFR 2022-05-10 -0.467      1.000000
   CNC 2025-07-02 -0.404      0.995107
  CRDO 2023-02-15 -0.468      0.945496
  CVNA 2022-12-07 -0.429      0.952493
    DD 2025-11-03 -0.575      0.997323
  DOCU 2021-12-03 -0.422      1.004839
  DXCM 2024-07-26 -0.407      0.974729
  FISV 2025-10-29 -0.440      1.020727
  NBIS 2022-02-24 -0.403      1.040381
  OKLO 2024-05-10 -0.536      1.000000
  QUBT 2025-01-08 -0.433      1.461899
   QXO 2024-07-30 -0.801    616.611739
  RGTI 2025-01-08 -0.454      1.547811
  SNAP 2022-05-24 -0.431      0.995774
  SOUN 2022-06-06 -0.484      0.000000
```

SNAP −43% on 2022-05-24, CVNA −43% on 2022-12-07, DOCU −42% on 2021-12-03,
DXCM −41% on 2024-07-26, CNC −40% on 2025-07-02, FISV −44% on 2025-10-29 are all
famous single-day guidance crashes with an unchanged share count. Every one is
recorded in the backtest as a **0% day**.

54 (as-of, ticker) observations in the valuation backtest have a 126-day forward
window containing one; because 126-day windows are sampled every 21 days, one
crash contaminates six observations. Restoring the six CNC observations takes
their mean forward return from −6.3% to −44.1%.

**Impact** — forward returns are biased **up**, and the bias falls exclusively on
the left tail — the tail that finding 2's arithmetic-mean argument depends on. It
is small in count (0.22% of observations) but strictly one-directional. Separately,
splits between −20% and −40% (3:2, 4:3, 5:4) fall below the threshold and are
never repaired at all, injecting fake negative forward returns; the commit log
("MNST 2:1 split handled") shows splits are currently patched by hand.

**Severity: HIGH**

---

## 4. Survivorship is near-total and the docs describe it as a "tilt"

**What breaks** — the price store was backfilled from a fixed snapshot list
(`data_cache/universe/universe_tickers.txt`, 2991 names alive in 2026). Companies
that were delisted, acquired or went bankrupt between 2018 and 2026 were never
fetched, so they cannot appear at any as-of date. Zero of the 646-name
fundamental universe are dead.

**Repro**

```
$ python - <<'EOF'
import sys, pandas as pd
from pathlib import Path
sys.path.insert(0,'.')
from stocklab.data.live import PriceStore
from stocklab.data.panel import long_to_panel
p=long_to_panel(PriceStore('data_cache/live').load())
last=p.close.apply(lambda s:s.last_valid_index()); first=p.close.apply(lambda s:s.first_valid_index())
end=p.close.index[-1]; dead=last[last<end-pd.Timedelta(days=30)]
print("store tickers:",p.close.shape[1],"| span",p.close.index[0].date(),"->",end.date())
print("series ending >30d early (delisted):",len(dead))
xb={f.stem for f in Path('data_cache/xbrl').glob('*.json')}
print("fundamental universe:",len(xb),"| dead among them:",len(set(dead.index)&xb))
print("names with NO price before 2022-03 but present in the backtest:",
      int((first[[t for t in xb if t in first.index]]>pd.Timestamp('2022-03-04')).sum()))
print("rows with a signal but NO forward return:",
      int(pd.read_csv('experiments/valuation_backtest_rows.csv')['fwd_126'].isna().sum()))
EOF
store tickers: 2992 | span 2018-01-02 -> 2026-08-12
series ending >30d early (delisted): 2
fundamental universe: 646 | dead among them: 0
names with NO price before 2022-03 but present in the backtest: 36
rows with a signal but NO forward return: 0
```

**Impact** — 2 of 2992 (0.07%) attrition over 8.5 years, against a realistic
30–40% for a US listed universe. There is no delisting return in the data at all,
so the "0 rows with a missing forward return" line is not a sign of clean data —
it is the signature of a universe where nothing can die. The docs' phrasing
("survivorship-tilted", "survivorship-flagged") understates this: it is not a
tilt, it is the complete absence of the failure population, on both the long
side (no bankruptcies) and the entry side (36 names enter with no pre-2022
history). It compounds finding 1 rather than being separate from it.

**Severity: HIGH**

---

## 5. The as-of market cap is contaminated by events that happen after the as-of date

**What breaks** — `valuation_features()` computes
`mktcap = shares_outstanding(filed <= as_of) * price(as_of)`. But
`sanitize_corporate_actions()` rescales *all prior closes* whenever it repairs an
event, so the as-of price already embeds a split or crash that has not happened
yet, while the share count does not. Market cap is understated by the factor,
and the name looks cheaper than it was.

**Repro**

```
$ python - <<'EOF'
import sys, re, pandas as pd
sys.path.insert(0,'.')
from stocklab.data.live import PriceStore, apply_split_adjustments
from stocklab.data.loaders import sanitize_corporate_actions
from stocklab.data.panel import long_to_panel
store=PriceStore('data_cache/live'); panel=long_to_panel(store.load())
p2,_=apply_split_adjustments(panel,store.load_actions()); p3,notes=sanitize_corporate_actions(p2)
E=pd.DataFrame([(n.split()[0],pd.Timestamp(n.split()[1].rstrip(':')),
                 float(re.search(r'scaled by ([\d.]+)',n).group(1)))
                for n in notes if 'step treated as un-adjusted' in n],
               columns=['ticker','date','factor'])
df=pd.read_csv('experiments/valuation_backtest_rows.csv',parse_dates=['as_of'])
hits=[]
for t,g in E.groupby('ticker'):
    for _,row in df[df.ticker==t].iterrows():
        fut=g[g.date>row.as_of]
        if len(fut): hits.append({'x':1/float(fut.factor.prod()),'z':row.z_VALUE,'f':row.fwd_126})
H=pd.DataFrame(hits)
print("rows whose as-of PRICE is back-scaled for a FUTURE event:",len(H),"(",round(100*len(H)/len(df),2),"pct )")
print("market cap understated by median",round(H.x.median(),2),"x  max",round(H.x.max(),1),"x")
print("their mean z_VALUE:",round(H.z.mean(),3),"vs universe",round(df.z_VALUE.mean(),3))
print("their mean fwd 126d:",round(100*H.f.mean(),1),"pct vs universe",round(100*df.fwd_126.mean(),1),"pct")
EOF
rows whose as-of PRICE is back-scaled for a FUTURE event: 289 ( 1.24 pct )
market cap understated by median 1.83 x  max 5.0 x
their mean z_VALUE: 0.297 vs universe -0.005
their mean fwd 126d: 86.7 pct vs universe 12.9 pct
```

**Impact** — 289 observations are pushed toward the cheap end of the VALUE sort
by information from the future, and those same observations returned +86.7%
against a universe mean of +12.9%. This mechanically manufactures part of the
VALUE premium reported in `docs/BACKTEST_VALUATION.md`. Note the direction is
opposite to finding 3 on the same rows: the price is scaled down *and* the crash
is erased from the forward return, so the observation looks cheap and unpunished.

**Severity: MEDIUM**

---

## 6. 84 t-statistics are reported and none of them enter the project's own trial ledger

**What breaks** — the project built a multiple-testing accounting mechanism
(`experiments/trial_ledger.json`, `deflated_sharpe()` in
`stocklab/backtest/metrics.py`, a sealed-holdout register in
`experiments/HOLDOUT_OPENED.json`) and then stopped using it exactly when the
fundamental backtests began.

**Repro**

```
$ python -c "
import json
def count(d):
    c=0
    for k,v in d.items():
        if isinstance(v,dict): c += 1 if ('mean_ic' in v or 'nw_t' in v) else count(v)
    return c
tot=0
for f in ['fieldwatch','positioning','improvement','valuation']:
    n=count(json.load(open(f'experiments/{f}_backtest.json'))); tot+=n; print(f, n)
print('TOTAL', tot)
led=json.load(open('experiments/trial_ledger.json'))
print('ledger total_trials', led['total_trials'], '| last run', led['runs'][-1]['at'][:19], led['runs'][-1]['out'])
print('backtests in ledger:', any('backtest' in r['out'] for r in led['runs']))
"
fieldwatch 6
positioning 16
improvement 26
valuation 36
TOTAL 84
ledger total_trials 90 | last run 2026-08-08T17:42:14 experiments/field_effects
backtests in ledger: False
```

**Impact** — the reported t 2.73 is the best of a family of 36 statistics in
`backtest_valuation.py` alone, sitting on top of 90 already-charged trials. A
Bonferroni adjustment across just the 28 pre-registered signal × variant ×
horizon cells takes its nominal two-sided p ≈ 0.009 to ≈ 0.25. No correction is
applied anywhere and no deflated statistic is computed for this layer.

**Severity: MEDIUM**

---

## 7. The pre-registration is genuine but the decision rule was not applied as written

**What breaks** — three separate deviations, in a document that is otherwise
honest (the git order is correct: `6c90bb2` 04:26:51 precedes `cb20007` 04:30:39;
`80e490a` 06:57:50 precedes `96bc8c0` 07:01:22, and the prereg openly names the
snooped window it came from).

(a) **The primary comparison fails and the doc misstates it.** The prereg's H2 is
"`VALUE` has positive IC **and** `IMPROVEMENT + VALUE` beats either alone."

```
$ python -c "
import json; d=json.load(open('experiments/valuation_backtest.json'))['IC_126d']
print('VALUE_sn        IC',round(d['VALUE_sn']['mean_ic'],4),'t',round(d['VALUE_sn']['nw_t'],2))
print('IMPROV_VALUE_sn IC',round(d['IMPROV_VALUE_sn']['mean_ic'],4),'t',round(d['IMPROV_VALUE_sn']['nw_t'],2))
print('combination is', 'ABOVE' if d['IMPROV_VALUE_sn']['mean_ic']>d['VALUE_sn']['mean_ic'] else 'BELOW', 'VALUE alone')
"
VALUE_sn        IC 0.0514 t 2.21
IMPROV_VALUE_sn IC 0.0453 t 2.73
combination is BELOW VALUE alone
```

`docs/BACKTEST_VALUATION.md:28` says "its IC (+0.045) is barely above VALUE alone
(+0.051)". 0.045 is below 0.051. The decision statistic is then silently switched
from IC to t so the combination "wins".

(b) **The held-out window was already spent.** `backtest_improvement.py` ran at
04:30 on 2026-08-11 and reported held-out ICs for LEVELS, IMPROVEMENT, momentum
and all four components on exactly the 22 dates 2022-03-04 → 2023-12-05.
`backtest_valuation.py` ran 2h31m later and its doc calls that same window "the
period never used to build it". Neither opening is recorded in
`experiments/HOLDOUT_OPENED.json`, which still shows a single open on 2026-08-08.

(c) **The held-out period is not held out from finding 1.** Both sub-periods use
a universe chosen with 2026 liquidity. Out-of-sample in time is not out-of-sample
in universe selection — and under a point-in-time screen the held-out `sn_LEVELS`
IC actually turns *positive* (+0.006), i.e. the sign that "replicates
out-of-sample" is itself the artifact.

**Impact** — the verdict "H2 is SUPPORTED... the first genuinely positive,
pre-registered result in the project" does not hold on its own stated rule, and
would not hold on a point-in-time universe either.

**Severity: MEDIUM**

---

## 8. Newey-West lag is shorter than the overlap it is there to absorb

**What breaks** — all four scripts call `newey_west_tstat(series, lags=3)`. The
126-day forward window sampled every 21 trading days induces an MA(5) structure
(126/21 − 1 = 5); lags=3 cannot absorb it. `stocklab/backtest/metrics.py` already
knows this — `signal_report()` uses `lags = 2*horizon` and its docstring records
that `lags=horizon` "understated" — but the fundamental backtests do not follow it.

**Repro**

```
  signal              t lags=3  t lags=5  t lags=8   non-overlapping subsamples (every 6th date, n=8)
  sn_LEVELS              -3.15     -2.99     -2.98   range [-2.73 .. -1.36], 2/6 reach |t|>=2
  sn_IMPROV_VALUE        +2.73     +2.46     +2.42   range [+1.07 .. +2.22], 3/6 reach |t|>=2
  sn_VALUE               +2.21     +1.96     +1.88   range [+0.84 .. +2.05], 2/6 reach |t|>=2
  z_mom                  +2.86     +2.67     +2.84   range [+1.40 .. +2.36], 1/6 reach |t|>=2
  z_ALL                  +3.51     +3.18     +3.22   range [+1.45 .. +2.83], 4/6 reach |t|>=2
```

**Impact** — the correction is real but modest: the headline **t 2.73 → 2.46**,
and `sn_VALUE` **2.21 → 1.96** drops below the pre-registered bar. The sharper
statement is the last column: split the 47 dates into the six genuinely
non-overlapping subsamples and the headline t ranges from +1.07 to +2.22
depending on which one you draw, with only 3 of 6 clearing |t| ≥ 2. The docs'
own caveat ("~8-10 independent observations") is correct and should be the
quoted number, not the 47-point t.

**Severity: LOW** (as a t-stat error) / **MEDIUM** (as a reporting choice)

---

## 9. Several documented numbers no longer reproduce because the sample moves

**What breaks** — the FieldWatch grid is anchored to the end of the store
(`start_i = searchsorted(dates, dates[-1] - 730 days)`), and the fundamental
universe is whatever `data_cache/xbrl/` currently holds (592 → 646 names since
the docs were written). Re-running today reproduces the *shape* of every result
but not the digits, and a few specific documented claims have flipped.

**Repro** — `python scripts/backtest_improvement.py`, 126d IMPROVEMENT spread:

```
                    mean      median   hit   held_out
docs / committed   +0.0162   -0.0135   0.45   -0.0006
re-run 2026-08-13  +0.0195   +0.0023   0.51   +0.0012
```

**Impact** — `docs/BACKTEST_IMPROVEMENT.md`'s sentence "the spread was +1.6% mean
but **−1.3% median, 45% hit rate**, and −0.1% in the held-out period — i.e. out
of sample it did nothing" no longer reproduces: the median and the held-out mean
are now positive and the hit rate is 51%. The conclusion drawn from it happens to
survive, but the numbers cited do not. Every doc should pin the universe snapshot
and the date grid, or state that its numbers are as-of a date.

**Severity: LOW**

---

## 10. Positive corporate actions are exempt from repair by design

**What breaks** — `sanitize_corporate_actions()` rule 3 leaves all positive moves
alone, so an unadjusted reverse split appears as a genuine forward return. 285
one-day gains ≥ +60% exist in the store; checked against SEC share counts, 2 in
the fundamental universe are unambiguous reverse splits (QXO 2024-06-06 +69% with
shares × 0.125; SOUN 2022-05-02 +68%). The rest are real (e.g. BMNR +695% on
2025-06-30 with shares × 2.1 — a genuine move).

**Impact** — small, but strictly one-directional and in the same up-biasing
direction as finding 3. Worth fixing with the same corporate-action table that
finding 3 needs.

**Severity: LOW**

---

## Claimed vs reproduced

Re-run 2026-08-13 with `python scripts/backtest_{fieldwatch,positioning,improvement,valuation}.py`.
"PIT universe" = point-in-time trailing-252d median dollar volume ≥ $150M at the
as-of date, the screen the docs already claim the universe satisfies.

| Claimed | Source | Re-run today | PIT universe | Verdict |
|---|---|---|---|---|
| FieldWatch 21d regime persistence **IC +0.109, t 4.13, 44 dates, 128 fields** | BACKTEST_FIELDWATCH.md | **IC +0.116, t 4.70**, 44 dates, 129 fields | n/a (field-level) | **PASS** |
| FieldWatch attention → 21d return ≈ 0 (**IC +0.013, t 0.67**) | BACKTEST_FIELDWATCH.md | **IC +0.001, t 0.03** | n/a | **PASS** |
| FieldWatch STRESS highest fwd vol 0.348 / QUIET lowest 0.233 | BACKTEST_FIELDWATCH.md | 0.316 / 0.234 | n/a | **PASS** |
| Positioning alone sorts backwards, **rank-IC −0.058** (LEVELS, 126d) | BACKTEST_IMPROVEMENT.md | **−0.065, t −2.88** | **−0.029, t −0.98** | **FAIL** (universe artifact) |
| Levels sort backwards **IC −0.053, t −3.15** (sector-neutral, 126d) | BACKTEST_VALUATION.md | **−0.060, t −3.47** | **−0.022, t −0.91** | **FAIL** (universe artifact) |
| Positioning + price **+0.042, t 2.7** (IMPROV_VALUE raw, 126d) | BACKTEST_VALUATION.md | **+0.034, t 2.45** | **+0.038, t 1.50** | **FAIL** (fails prereg bar) |
| Value+improvement **IC +0.045, t 2.73** (sector-neutral, 126d) | BACKTEST_VALUATION.md | **+0.044, t 2.70** | **+0.036, t 1.44** | **FAIL** (fails prereg bar) |
| Decile spread negative: cheapest **+14.6%** vs priciest **+22.6%** / 6mo | BACKTEST_VALUATION.md | **+14.0% vs +23.0%** | **+13.3% vs +10.2%** | **Reproduces, FAILS as an inference** |
| "IMPROVEMENT+VALUE beats either alone" | PREREGISTER + BACKTEST_VALUATION.md | +0.045 vs VALUE +0.051 | +0.036 vs +0.054 | **FAIL** (arithmetic error in doc) |
| Momentum **+0.080, t 2.88**, held-out +0.081 | BACKTEST_IMPROVEMENT.md | **+0.088, t 3.12** | **+0.044, t 1.39** | **FAIL** (universe artifact) |
| Positioning composite **−0.031, t −2.27** (3m) | BACKTEST_POSITIONING.md | **−0.026, t −2.25** | — | **PASS** |
| Combined+momentum decile spread **+15.2% / 6mo, t 1.89, 64% hit** | BACKTEST_POSITIONING.md | **+14.5%, t 1.77, 68% hit** | — | **PASS** |
| margin-change **+0.036 (t 2.68), held-out +0.007, tainted +0.062** | BACKTEST_IMPROVEMENT.md | **+0.036 (t 2.67), +0.008, +0.060** | +0.027 (t 1.76) | **PASS** (and the snooping conclusion stands) |
| IMPROVEMENT spread "+1.6% mean, **−1.3% median, 45% hit**" | BACKTEST_IMPROVEMENT.md | +2.0% mean, **+0.2% median, 51% hit** | — | **STALE** |
| Universe is "592 most-liquid US names (median >$150M/day)" | BACKTEST_POSITIONING.md | 646 names; **24.7% of observations below $150M/day at their own as-of date** | — | **FAIL** |
| "~7 independent quarters / ~8-10 independent observations" | all four docs | correct, but t-stats are still quoted on 44-47 points | — | **PASS** (caveat) / see finding 8 |

---

## Checked and CLEAN

These were tested for the specific failure mode and are correct. Listing them
because they are the parts a reader should trust.

1. **Cross-sectional z-scores are fitted per date, not pooled.** `_z()` and
   `_zs()` are called inside `for _, g in df.groupby("as_of")` in all three
   fundamental scripts. Winsorization (`s.clip(s.quantile(.02), s.quantile(.98))`)
   is also per date. No percentile or z-score is fitted on the full sample.
   Sector-neutral variants group within date *and* sector. No leakage.

2. **XBRL point-in-time discipline is real and strict.** `fetch_fundamentals.compact()`
   keeps the **earliest-filed** value per `(start, end)` key, so later restatements
   cannot leak backwards; every downstream selector filters `p["filed"] <= as_of`.
   The Q4 reconstruction in `quarterly_complete()` stamps the derived quarter with
   the 10-K's filing date, which is the correct point-in-time choice.

3. **Forward-return alignment is not off by a day.** Signal and entry both use the
   as-of close. Re-testing with entry at the *next* close (observe at t, trade at
   t+1) moves nothing: z_mom IC +0.0873 → +0.0886; sn_IMPROV_VALUE +0.0440 →
   +0.0456; sn_LEVELS −0.0597 → −0.0574. No same-close look-ahead of consequence.

4. **No truncated forward windows.** `last_i = len(dates) - max(FWD) - 1` in every
   script; the `min(i + FWD, len - 1)` clamps in `backtest_fieldwatch.py` never
   bind on the grid actually used. No observation is scored against a short window.

5. **FieldWatch H2 is not an artifact of nested fields.** The 128 fields are 12
   GICS sectors plus their 116 nested sub-industries. Restricting to the 116
   sub-industries alone (no double counting) leaves the result intact: vol-state
   IC +0.097, t 4.00 (vs +0.109, t 4.13 with the sectors included). H1 stays at
   zero in both. The FieldWatch conclusions in `docs/BACKTEST_FIELDWATCH.md` are
   supported by the data as run.

6. **FieldWatch forward windows do not touch their own trailing windows.**
   `_field_fwd_vol` / `_field_eqw_return` slice from `dates[i+1]`, and
   `pct_change()` discards the first row, so the day-i+1 return enters neither the
   trailing nor the forward statistic. Trailing vol at as-of and forward vol are
   genuinely disjoint.

7. **The FieldWatch backtest's own skepticism is correct and was honoured.** The
   63d attention IC that looked significant on the S&P set (t 3.88) does collapse
   on the broad universe (t 1.13 committed / 1.33 re-run), exactly as the doc
   claims. That doc talks itself out of its own best-looking number; it is the
   most honest document in the layer.

8. **The ML sweep layer (`horizon_sweep.py`, `combination_sweep.py`) is
   disciplined.** Both run on the bundled 2013-2018 dataset, seal the holdout
   (`folds = [f for f in folds if f.test_dates[-1] < cutoff]`), pre-register an
   expected-max-of-noise band *inside the script docstring*, charge every trial to
   `experiments/trial_ledger.json`, and use `lags = 2*horizon` for Newey-West. The
   contrast with the fundamental layer (finding 6) is the point: the machinery
   exists and works; it was simply not pointed at the newer backtests.

9. **`newey_west_tstat()` itself is implemented correctly** — Bartlett weights,
   `1 - l/(lags+1)`, `gamma_l` divided by `n`, `n < 10 → NaN` guard. The problem
   is the lag argument passed to it (finding 8), not the estimator.

10. **The `deflated_sharpe()` implementation is correct** (Bailey & López de Prado
    2014) and its docstring documents the annualized-vs-daily units footgun. It is
    simply never called by this layer.

---

*Audit run 2026-08-13 against commit `6d3eec1`. All four backtests were executed;
`git checkout -- experiments/` restored the committed artifacts afterwards, and
every repro command above reproduces the documented numbers from those committed
artifacts before showing the correction. No source file was modified.*
