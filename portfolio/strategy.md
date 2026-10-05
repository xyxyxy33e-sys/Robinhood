# Model Alpha — Investment Policy

**Mandate:** beat SPY total return, starting from $10,000 on 2026-09-04.
**Mode:** paper / model portfolio. No live orders are ever placed. Robinhood MCP is used for market data only.

## v2 · Aggressive (effective at the 2026-10-05 close)

On 2026-10-04 the owner raised the risk budget ("willing to take bigger risk"). v1 was built to beat SPY
with tracking error held down by diversifier sleeves (energy, banks, managed care, payments). Under a
bigger risk budget those sleeves are cost, not protection: they exist to *reduce* the gap to SPY, and
the mandate is to *widen* it in our favour. v2 spends the whole risk budget on the one edge with the
longest academic record behind it: cross-sectional momentum, concentrated.

### Selection (mechanical: `scripts/screen.py`)

1. **Universe:** ~30 liquid US-listed large caps, mostly technology plus the v1 names
   (list lives in `data/screens/<date>.json`).
2. **Excess return vs SPY** over 12m, 6m, 3m and 1m, from month-open prices to the latest close.
3. **Eligible only if** 12m excess > 0 **and** 6m excess > 0 (dual momentum: a name must beat the
   index over both horizons) **and** close is within 15% of its 12-month high (trend intact).
4. **Rank** eligible names by blend = 0.20·x12 + 0.35·x6 + 0.30·x3 + 0.15·x1.
5. **Book = top 8, equal weight** (12.25% each, 2% cash). Equal weight on purpose: rank-weighting would
   put the most extended name at the top of the book.
6. **Turnover buffer:** from the second reconstitution on, a held name stays if it is still eligible
   and ranks in the top 12.
7. **Valuation is not a filter.** v1 vetoed AMD at PE 123 on 2026-09-04; it then rose 36% in a month.
   In v2 the stop does the risk work, not the multiple.

### Reconstitution

- **Monthly**, on the first trading session of each month: refresh the screen data, run
  `screen.py --write <date>`, execute with `reconstitute.py <date>` at that day's close.
- Reconstitution legs are exempt from the drift-trade frequency limit.

### Risk rules (v1 value in brackets)

| Rule | v2 | v1 |
| --- | --- | --- |
| Names | 6–10, target 8 | 10–14 |
| Position cap at market (forced trim) | 25% | 15% |
| Drift band | ±25% of target or ±4 pp | ±25% or ±3 pp |
| Churn floor | $100 | $75 |
| Thesis review | −15% from cost, or −20 pp vs SPY | −20%, −15 pp |
| **Hard stop (automatic full exit)** | **−25% from cost** | none |
| Sector cap | none: single-theme book by design | 60% tech |
| Cash | ~2% | ~3% |
| Leverage / options / shorting | not permitted | not permitted |

**Why no leverage even with a bigger risk budget:** leverage scales risk and return together and adds
financing drag and path decay; it adds no edge. Concentration in names that are already beating the
index is the cheaper way to spend a risk budget when the goal is beating that index.

### What this book is, honestly

An equal-weight AI-infrastructure momentum basket: about 49% semiconductors (MU, AMD, TSM, NVDA),
12% networking, 25% security and edge software, 12% Apple. Expect it to move roughly 1.5–2× SPY.
A 25% unwind in the AI trade would plausibly take it down 35–45%. Momentum strategies also suffer
sharp reversals at market turning points; the hard stop and monthly re-screen limit, but do not
prevent, that damage.

---

# v1 · Original policy (2026-09-04 → 2026-10-05, retained for the record)

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
