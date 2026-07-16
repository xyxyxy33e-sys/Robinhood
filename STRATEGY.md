# Daily Momentum Calls — Strategy Specification

**Objective:** Buy calls on stocks showing confirmed intraday momentum, hold intraday only,
and be flat by the close. News is gathered pre-market every trading day to build a candidate
thesis before any money moves.

**Account:** Robinhood "Agentic" cash account `576391551` (agentic_allowed, options Level 2 —
single-leg only: long calls/puts, covered calls, cash-secured puts).

---

## 1. Daily schedule (US/Eastern)

| Time (ET) | Phase | Runbook |
|-----------|-------|---------|
| ~8:00 AM | Pre-market news + candidate research | `runbooks/premarket.md` |
| 9:35 AM | Entry — confirm momentum after the open, buy call | `runbooks/entry.md` |
| every 15 min until 1:30 PM (only if no trade yet) | Entry re-check — catch late qualifiers | `runbooks/entry.md` |
| every 5 min while a position is open | Monitor — stop-loss, discretionary profit-taking, re-entries | `runbooks/monitor.md` |
| ~3:30 PM | Exit — discretionary profit-taking / hard stop / forced flat by 3:55 | `runbooks/exit.md` |

The 8:00/9:45/3:30 phases are cron Routines; the 5-minute monitor is a self-re-arming
`send_later` loop started by a fill and stood down at 3:25 ET when the exit run takes over.

Scheduled via Claude Code Routines (cron is UTC — see README for DST note). Every runbook
begins with a market-open check and a time check; if fired at the wrong time it reschedules
itself rather than acting.

## 2. Universe & candidate discovery

Saved Robinhood scanner **"Daily Momentum Calls"** (`5399dce3-8430-476c-ba65-89ac920af0bf`):

- % change vs prior close > +2% (1d)
- 30-day average volume > 5M shares
- 5-day average options volume > 10,000 contracts
- RSI(14, 1d) between 55 and 80 (uptrend, not blow-off overbought)
- Last price between $5 and $250 (keeps one ATM call affordable)
- Market cap > $2B (no illiquid junk)

Supplemented by pre-market news: fresh catalysts (earnings beats, guidance raises, upgrades,
product/regulatory news) rank a candidate up; binary-event risk ranks it down.

## 3. Momentum signal (all must hold at entry time)

1. Appears in the scanner **or** was a top pre-market candidate now up ≥2%.
2. Tape confirmation scaled to session age: in the first 10 minutes, above the opening
   print with no immediate reversal (1-minute bars); after 9:40, above open and holding
   above VWAP on 5-minute bars with no full gap-fade.
4. **No earnings between now and the option's expiry** (check `get_earnings_results`) —
   we trade momentum, not event lotteries.
5. A concrete catalyst or sector tailwind identified in the pre-market journal entry.

Rank multiple qualifiers by: catalyst strength > relative volume > cleanest tape. Pick one.

## 4. Contract selection

- **Type:** call, buy-to-open. **Expiry:** nearest expiration 1–21 DTE (never 0 DTE — no
  contracts expiring the same day). Short-dated (1–7 DTE) contracts are cheapest but carry
  violent gamma/theta; the forced same-day close caps expiry risk, not premium risk.
- **Strike:** at-the-money or the first strike above spot.
- **Liquidity gates:** open interest ≥ 500; bid-ask spread ≤ 10% of mid. If ATM fails the
  gates, step one strike out; if still failing, skip the underlying.
- **Order:** limit buy at mid, GFD, regular hours. If unfilled in 10 min, reprice once to
  mid + 40% of half-spread. Never market-buy an option.

## 5. Position sizing & risk limits (config.yaml is the source of truth)

- Premium per trade ≤ `max_premium_pct_of_bp`% of options buying power, hard-capped at
  `max_premium_per_trade`. No averaging down; never re-buy a symbol stopped out today.
- At most `max_open_positions` concurrent positions and `max_new_positions_per_day`
  entries per day (initial entry at 9:35; 15-min re-checks on no-trade and monitor-loop
  re-entries both end at 1:30 PM ET).
- Skip entries while options buying power < `min_buying_power_to_trade` — log why.
- Cash account: option sale proceeds settle **T+1**. The exit run's proceeds fund the
  *next* day's entry; never plan on same-day recycling of proceeds.

## 6. Exit rules (enforced by the 5-minute monitor loop and the 3:30 PM run; position never held overnight)

- **Resting take-profit order:** immediately after every entry fill, a sell-to-close limit
  at entry × (1 + `take_profit_pct`/100) is placed GFD. It captures the win automatically
  even if monitoring is interrupted (the failure mode observed 2026-07-16). Any other close
  (stop, discretionary, forced flat) must cancel it first.
- **Discretionary profit-taking below the cap:** the agent may still sell a winner before
  the take-profit level when momentum breaks (lower highs, VWAP lost, volume faded) or into
  an obvious exhaustion spike — take the gain rather than round-trip it. Record the
  reasoning in the journal every time.
- **Stop loss (hard floor):** mark ≤ −30% under entry premium → sell-to-close immediately,
  at mid, repricing toward the bid every 5 minutes until filled. Losers get no discretion.
- **Forced flat:** whatever remains is closed starting 3:40 ET: limit at mid → reprice toward
  bid at 3:48 → by 3:53, cross the spread (limit at bid) to guarantee the fill. All open
  option orders from the strategy are cancelled after the position is flat.
- If a close somehow fails before 4:00 ET, notify the user immediately with the position
  details — do not silently carry it.

## 7. Execution authorization

Per `config.yaml`:
- `entry_auto_execute: false` — the entry run reviews the order (`review_option_order`),
  posts the full quote/alerts, and asks the user to confirm before placing. Setting it to
  `true` in this file is the user's standing instruction to place entries without asking.
- `exit_auto_execute: true` — closes are risk-reducing and time-critical; they execute
  without waiting. Set `false` to be asked first (risk: unanswered = overnight hold).

## 8. Journaling

Every run appends to `journal/YYYY-MM-DD.md` (template in `journal/TEMPLATE.md`): news
digest, candidates considered, trade taken (or reason for no trade), fills, P&L, and one
lesson. Committed and pushed after every run — the journal is the system's memory.

## 9. Known limitations & warnings

- Long calls lose to theta and IV crush even when direction is right. Expect many small
  losses; the edge, if any, comes from cutting losers fast and exercising good judgment on
  when winners are done. This is a high-risk strategy — size it with money you can lose.
- Level 2 = no spreads; there is no defined-risk vertical available to cap IV exposure.
- Scanner % change filter reads ~0 outside regular hours; pre-market candidate work relies
  on news + prior-day closes, and the 9:45 run re-validates with live data.
- Nothing here is financial advice; the user owns every parameter in `config.yaml`.
