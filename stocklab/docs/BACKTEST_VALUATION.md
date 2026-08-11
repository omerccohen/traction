# Does adding PRICE fix the ranking? — pre-registered test (H2)

**Verdict: H2 passes the pre-registered test, and the result is still not a buy
rule.** Adding valuation flipped the ranking from backwards to forwards — a
real, out-of-sample-replicated improvement. But the decile curve shows the money
went the other way, and that gap is the most important thing on this page.

Pre-registered in `experiments/PREREGISTER_improvement.md` (addendum, committed
before the run). 592 names, ~493 per date, 59 monthly dates, held-out
(2022-03→2023-12) vs tainted (2024-01→) split.

## Result 1 — the sign flip is real and it replicated

| signal (6-month, sector-neutral) | IC | NW t | held-out | tainted |
|---|---|---|---|---|
| LEVELS ("how good is it") | **−0.053** | **−3.15** | −0.024 | −0.078 |
| IMPROVEMENT ("getting better") | +0.018 | 1.93 | +0.012 | +0.023 |
| VALUE ("what you pay") | **+0.051** | **+2.21** | +0.069 | +0.036 |
| **IMPROVEMENT + VALUE** | **+0.045** | **+2.73** | **+0.051** | **+0.040** |
| everything + momentum | **+0.091** | **+3.51** | +0.089 | +0.092 |

Per the rule fixed in advance — positive in **both** sub-periods and |t| ≥ 2 —
**H2 is SUPPORTED.** Positioning alone sorted at −0.053; positioning combined
with price sorts at +0.045, and it holds in the period never used to build it
(+0.051 held-out vs +0.040 tainted). The diagnosis was right: **the missing
ingredient really was price.**

Note *why* the combination beats either piece: its IC (+0.045) is barely above
VALUE alone (+0.051), but its **t nearly doubles** (2.73 vs 2.21) — combining
two weakly-related signals buys consistency, not magnitude.

## Result 2 — the catch: rank-IC said yes, the money said no

Sorting the universe into cheapness deciles and taking the **average forward
6-month return** of each:

| decile | 1 (priciest) | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 (cheapest) |
|---|---|---|---|---|---|---|---|---|---|---|
| fwd 6m | **+22.6%** | +12.0 | +9.3 | +12.2 | +14.6 | +11.2 | +10.9 | +10.9 | +8.9 | **+14.6%** |

**The most expensive decile was the best-performing one, by 8 points.** The
"buy cheap, avoid expensive" spread was therefore **−7.9%** per 6 months
(VALUE) and −4.7% (IMPROVEMENT+VALUE), despite the positive rank-IC.

Both facts are true at once, and the reason matters:
- **Cheap names won more *often*** → positive rank correlation (IC is a *rank*
  statistic; it counts who wins, not by how much).
- **Expensive names won far *bigger*** → the giant AI-era winners live in the
  priciest decile, and a handful of +100% moves dominate the *average*.

This is the same lottery structure found earlier in the "best positioned"
basket (median −4%, mean +1.2%, skew +3.0) — seen from the other side.

**Anyone reporting only the IC here would announce an edge that lost money.**

## Result 3 — one component is carrying it

| value component | 6m IC | t | held-out | tainted |
|---|---|---|---|---|
| **sales-to-price** | **+0.081** | **+3.22** | +0.126 | +0.041 |
| book-to-price | +0.030 | 1.35 | −0.001 | +0.057 |
| earnings yield | −0.005 | −0.19 | +0.016 | −0.024 |

The "value effect" here is almost entirely **price-to-sales**. And sales-to-price
correlates **−0.28** with margin level — a company looks cheap on sales largely
*because* it is low-margin. So this is not independent confirmation of the
earlier finding; **it is largely the same effect restated** (high margin =
expensive = lags). Treat it as one result, not two.

## Bottom line

- **Confirmed:** price is the missing ingredient. Ranking on positioning alone
  is backwards; positioning combined with valuation sorts the right way, and
  that replicated out-of-sample, sector-neutral, at both horizons. This is the
  first genuinely positive, pre-registered result in the project.
- **Not confirmed:** that it produces a buying selection. The cheapest decile
  did **not** beat the most expensive one in this sample — it lost to it by 8
  points per 6 months.
- **Use it as** a question — *"is my thesis already in the price?"* — which is
  exactly what `scripts/price_vs_position.py` prints. Never as a screen to buy
  the cheap end.

*Caveats: 2022-2026 only, and **every decile was positive** — this was a bull
market, so nothing here is tested against a drawdown. No costs or turnover.
Current-liquid universe (survivorship-tilted). ~47-59 overlapping dates ≈ 8-10
independent observations. Value is documented to have multi-year losing
stretches; one 4-year window cannot see them.*

*Reproduce: `python scripts/fetch_fundamentals.py 600 && python
scripts/backtest_valuation.py`.*
