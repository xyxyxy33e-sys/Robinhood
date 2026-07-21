# Daily Momentum Calls — Strategy Specification

**Objective:** Buy calls on stocks showing confirmed intraday bullish momentum, and puts on
stocks showing confirmed intraday bearish momentum (`enable_puts`, added 2026-07-21), hold
intraday only, and be flat by the close. News is gathered pre-market every trading day to
build a candidate thesis before any money moves. The name predates the puts addition; it
still trades both directions under it.

**Account:** Robinhood "Agentic" cash account `576391551` (agentic_allowed, options Level 2 —
single-leg only: long calls/puts, covered calls, cash-secured puts).

---

## 1. Daily schedule (US/Eastern)

| Time (ET) | Phase | Runbook |
|-----------|-------|---------|
| ~8:00 AM | Pre-market news + candidate research | `runbooks/premarket.md` |
| 9:35 AM | Entry — confirm momentum after the open, buy call or put | `runbooks/entry.md` |
| every 10 min until 1:30 PM (only if no trade yet) | Entry re-check — catch late qualifiers | `runbooks/entry.md` |
| every 5 min while a position is open | Monitor — stop-loss, discretionary profit-taking, re-entries | `runbooks/monitor.md` |
| ~3:30 PM | Exit — discretionary profit-taking / hard stop / forced flat by 3:55 | `runbooks/exit.md` |

The 8:00/9:45/3:30 phases are cron Routines; the 5-minute monitor is a self-re-arming
`send_later` loop started by a fill and stood down at 3:25 ET when the exit run takes over.

Scheduled via Claude Code Routines (cron is UTC — see README for DST note). Every runbook
begins with a market-open check and a time check; if fired at the wrong time it reschedules
itself rather than acting.

## 2. Universe & candidate discovery

Two saved Robinhood scanners, run every pass:

- **Calls — "Daily Momentum Calls"** (`scan_id`, `5399dce3-8430-476c-ba65-89ac920af0bf`):
  % change vs prior close > +2% (1d); RSI(14, 1d) between 55 and 80 (uptrend, not
  blow-off overbought).
- **Puts — "Daily Momentum Puts"** (`scan_id_puts`, `1849aba7-1d06-4269-b58f-b4e42d9bfb02`,
  added 2026-07-21, gated by `enable_puts`): % change vs prior close < −2% (1d);
  RSI(14, 1d) between 20 and 45 (downtrend, not oversold-bounce territory).

Both scanners share: 30-day average volume > 5M shares; 5-day average options volume >
10,000 contracts; last price between $5 and $250 (keeps one ATM contract affordable);
market cap > $2B (no illiquid junk).

Supplemented by pre-market news: fresh catalysts (earnings beats/misses, guidance
raises/cuts, upgrades/downgrades, product/regulatory news) rank a candidate up in its
direction; binary-event risk ranks it down.

## 3. Momentum signal (all must hold at entry time)

1. Appears in the relevant scanner **or** was a top pre-market candidate now moved ≥2% in
   its direction.
2. Tape confirmation scaled to session age, direction-aware:
   - **Calls**: first 10 minutes — above the opening print with no immediate reversal
     (1-minute bars); after 9:40 — above open and holding above VWAP on 5-minute bars,
     no full gap-fade.
   - **Puts**: first 10 minutes — below the opening print with no immediate reversal
     (1-minute bars); after 9:40 — below open and holding below VWAP on 5-minute bars,
     no full gap-fill-back-to-open.
3. **No earnings between now and the option's expiry** (check `get_earnings_results`) —
   we trade momentum, not event lotteries.
4. A concrete catalyst or sector tailwind identified in the pre-market journal entry.

Rank qualifiers by: catalyst strength > relative volume > cleanest tape, calls and puts
candidates ranked together on the same list. Take up to (`max_open_calls` − currently open
calls) call qualifiers and up to (`max_open_puts` − currently open puts) put qualifiers in
one pass, best first within each direction — each independently passing every sizing and
liquidity gate. Re-entering a symbol already open (or closed earlier today, including
after a stop-out) is allowed; the only same-symbol restriction is that a symbol can't hold
a call and a put at the same time.

## 4. Contract selection

- **Type:** call for a bullish qualifier, put for a bearish qualifier; always buy-to-open
  (long only — no short options). **Expiry:** nearest expiration 1–21 DTE (never 0 DTE —
  no contracts expiring the same day). Monthly-only chains (no expiry in window): nearest
  monthly up to `dte_max_no_weekly` (45) is allowed. Short-dated (1–7 DTE) contracts are
  cheapest but carry violent gamma/theta; the forced same-day close caps expiry risk, not
  premium risk.
- **Strike:** at-the-money, or the first strike beyond spot in the direction of the trade
  (above spot for calls, below spot for puts).
- **Liquidity gates:** open interest ≥ 500; bid-ask spread ≤ 10% of mid. If ATM fails the
  gates, step one strike out (further out-of-the-money); if still failing, skip the
  underlying.
- **Order:** limit buy at mid, GFD, regular hours. If unfilled in 10 min, reprice once to
  mid + 40% of half-spread. Never market-buy an option.

## 5. Position sizing & risk limits (config.yaml is the source of truth)

- Premium per trade ≤ `max_premium_per_trade` — a flat cap, not scaled or capped by live
  buying power (removed 2026-07-21 per user instruction; the broker rejects the order if
  settled cash is actually insufficient). Quantity = floor(max_premium_per_trade /
  (premium × 100)), min 1 — multiple contracts of the same call or put allowed. No
  averaging down (don't add to a position that's currently open and red).
- Re-entering the same underlying is allowed — no one-position-per-symbol cap, and no
  restriction on re-buying a symbol that was stopped out earlier today (both removed
  2026-07-21 per user instruction). The only same-symbol restriction: never hold a call
  and a put on the same underlying at the same time.
- At most `max_open_calls` concurrent call positions AND `max_open_puts` concurrent put
  positions (up to both at once — e.g. 5 calls + 5 puts = 10 total), plus
  `max_new_positions_per_day` entries per day (initial entry at 9:35; 10-min re-checks on
  no-trade and monitor-loop re-entries both end at 1:30 PM ET).
- Skip entries while options buying power < `min_buying_power_to_trade` — log why.
- Cash account: option sale proceeds settle **T+1**. The exit run's proceeds fund the
  *next* day's entry; never plan on same-day recycling of proceeds.

## 6. Exit rules (enforced by the 5-minute monitor loop and the 3:30 PM run; position never held overnight)

- **Resting protective order (broker-side):** immediately after every entry fill, ONE
  protective sell rests at the broker per `resting_order_type` — Robinhood holds only one
  sell order per contract (no OCO for options). Default `stop_loss`: a stop_market at
  entry × (1 + `stop_loss_pct`/100), so the max-loss exit executes even if monitoring is
  interrupted (failure mode observed 2026-07-16). Alternative `take_profit`: a sell limit
  at entry × (1 + `take_profit_pct`/100). The monitor loop enforces whichever side is not
  resting, in software. Any other close must cancel the resting order first.
- **Discretionary profit-taking below the target:** the agent may sell a winner before the
  take-profit level when momentum breaks (lower highs, VWAP lost, volume faded) or into an
  obvious exhaustion spike — take the gain rather than round-trip it. Record the reasoning
  in the journal every time.
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

- Long calls and puts both lose to theta and IV crush even when direction is right. Expect
  many small losses; the edge, if any, comes from cutting losers fast and exercising good
  judgment on when winners are done. This is a high-risk strategy — size it with money you
  can lose.
- Level 2 = no spreads; there is no defined-risk vertical available to cap IV exposure on
  either side.
- Scanner % change filter reads ~0 outside regular hours; pre-market candidate work relies
  on news + prior-day closes, and the 9:45 run re-validates with live data.
- Puts are newer (added 2026-07-21) and have no live track record yet in this system —
  watch the first several put trades closely for anything the calls-only design didn't
  anticipate (e.g. downside gap risk behaves differently from upside chasing).
- Nothing here is financial advice; the user owns every parameter in `config.yaml`.
