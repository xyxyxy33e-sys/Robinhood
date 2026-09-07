# Model Alpha-12 — Investment Policy

**Mandate:** beat SPY total return over a rolling 12-month horizon, starting from $10,000 on 2026-09-04.
**Mode:** paper / model portfolio. No live orders are ever placed. Robinhood MCP is used for market data only.

## 1. Why this can beat SPY

SPY is ~40% concentrated in its top 10 already, so simply owning megacaps is not an edge. The active bets here are:

1. **Valuation-aware momentum.** Rank the universe on excess return vs SPY blended across
   12m (30%), 6m (40%), 3m (30%), then *reject* names whose momentum is decaying at an
   extreme multiple. This is the discipline that keeps AMD (+194% 12m, PE 123, 3m relative
   already negative) out of the book.
2. **Deliberate healthcare overweight (16% vs ~10% in SPY).** LLY and UNH are the only large
   sleeves whose drivers are uncorrelated to the AI capex cycle that dominates the index.
3. **Value barbell inside tech.** GOOGL (PE 17) and AMZN (PE 21) are held against NVDA and
   ANET so the tech sleeve is not a single factor bet on multiple expansion.
4. **No index dead weight.** The bottom ~400 names of the S&P contribute most of its
   tracking noise and little of its return. 12 names, all with a stated thesis.

## 2. Position limits (hard)

| Rule | Limit |
| --- | --- |
| Max single position | 12% at cost, 15% at market before forced trim |
| Max sector | 60% (tech complex), 20% (any other single sector) |
| Min position | 4% — below this, exit rather than hold a stub |
| Cash | 2–8% ordinary; >8% requires a stated reason |
| Leverage / options / shorting | Not permitted |
| Names | 10–14 |

## 3. Drift and rebalancing

Drift is checked **after every market close**. A position is flagged when *either*:

- **Relative band:** |actual weight − target weight| / target weight > **25%**, or
- **Absolute band:** |actual weight − target weight| > **3.0 percentage points**

Both must be considered because a 5% target and a 12% target need different sensitivities —
a pure absolute band never triggers on small positions, a pure relative band triggers
constantly on them.

**Trades are only executed when a flagged position also clears the friction test:**
the required trade is ≥ $75. Below that, the drift is recorded but not acted on. This is
the drift-vs-churn guard: rebalancing a $10k book on every 3% wiggle donates the entire
edge to spreads.

Additionally: **no more than 4 rebalancing trades in any 5-trading-day window**, and a
position sold outright cannot be repurchased for 10 trading days (anti-whipsaw).

## 4. Risk exits (override the bands)

- **Stop-review at −20% from cost basis** — not an automatic sale, but the thesis must be
  restated in the log or the position is closed.
- **Relative stop at −15% vs SPY since entry** — same treatment.
- A thesis that can no longer be stated in one sentence is a sell.

## 5. Daily check-in procedure (after close)

1. Pull closes for all holdings + SPY via Robinhood MCP → `data/prices/YYYY-MM-DD.json`
2. `python3 scripts/record_close.py YYYY-MM-DD` → appends to `portfolio/history.csv`
3. `python3 scripts/check_drift.py` → prints drift table and any rebalance proposal
4. Apply approved trades with `scripts/apply_trades.py`, which writes `portfolio/trades.csv`
5. `python3 scripts/build_dashboard.py` → regenerates `dashboard/index.html`

## 6. Known risks

- **Tech concentration is 58%** vs ~35% for SPY. This is the single largest source of
  tracking error and the most likely way the portfolio underperforms. It is intentional,
  and it is capped at 60%.
- 12 names means one blow-up costs ~8% of the book. The position limits are the only defence.
- Momentum strategies suffer sharp reversals at turning points; the quarterly-ish
  reconstitution cadence (not daily) is what limits the damage.
