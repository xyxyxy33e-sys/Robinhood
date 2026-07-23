# Runbook: Entry (9:35 AM ET, Mon–Fri; re-checks every 10 min until 1:30 PM on no-trade)

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` (pre-market section) first.
All times US/Eastern. Account = `account_number` from config.

## 0. Guards — every one must pass or the day is a no-trade
1. Trading day check (same as premarket). Market closed → journal, push, stop.
2. Time check: if before 9:35 ET, schedule a self check-in (`send_later`) for 9:35 ET and
   stop; if after 1:30 PM ET, skip the day (momentum entries decay) — journal why.
3. `get_option_positions` (nonzero=true): split by option_type. If open calls ≥
   `max_open_calls` AND open puts ≥ `max_open_puts`, stop (no room in either bucket).
   Otherwise continue — the surviving bucket(s) may still take a new entry.
4. `get_option_orders` (state=queued/confirmed, created today): no duplicate entry if an
   order is already working. Also check today's journal — if an entry was already made
   today (max_new_positions_per_day), stop.
5. `get_portfolio`: options buying power < `min_buying_power_to_trade` → journal
   "insufficient settled cash", notify user once (not every day — check whether yesterday's
   journal already flagged it), stop.

## 1. Confirm momentum (live)
1. `run_scan` on `scan_id` (calls) and, if `enable_puts` is true, `scan_id_puts` (puts) —
   live matches now meaningful.
2. Merge both scan results with pre-market candidates (top 10, each tagged call/put); drop
   anything that hit its "disqualify if".
3. For each surviving candidate (check the best-ranked first), tape check scaled to how
   much session exists, direction-aware:
   - **Calls — 9:30–9:40:** `get_equity_historicals` interval=minute — require last >
     opening print, last ≥ prior close × (1 + min_day_change_pct/100), and no immediate
     reversal (not below the session low of the first bars).
   - **Calls — after 9:40:** interval=5minute from 9:30 — require price > open, price >
     VWAP, and no full gap-fade (above the 9:30–9:40 low).
   - **Puts — 9:30–9:40:** require last < opening print, last ≤ prior close ×
     (1 − min_day_change_pct/100), and no immediate reversal (not above the session high
     of the first bars).
   - **Puts — after 9:40:** require price < open, price < VWAP, and no full gap-fill back
     above the 9:30–9:40 high.
   Accept that the 9:30–9:40 window trades on pre-market conviction with less confirmation.
4. `get_earnings_results` on finalists — reject if earnings before option expiry.
5. Rank the qualifiers (catalyst > relative volume > tape), calls and puts together, and
   take **up to (max_open_calls − currently open calls)** call qualifiers and **up to
   (max_open_puts − currently open puts)** put qualifiers, best first within each
   direction — each independently passing every gate in §2–§3. Re-entering a symbol
   already open, or one closed earlier today (including after a stop-out), is allowed —
   the only same-symbol restriction is never both a call and a put on the same underlying
   at once. A symbol closed earlier today for a PROFIT ranks first among qualifiers
   (leader re-entry, STRATEGY.md §3) — but only on a volume-confirmed resumption after
   its pullback, never on the dip itself, and funded by settled cash only. A position MAY hold multiple contracts — see §2 sizing. No qualifier → no
   trade; journal it.

## 2. Select the contract (per chosen underlying)
1. `get_option_chains` (underlying_symbol) → pick expiration in [dte_min, dte_max].
2. `get_option_instruments` (chain, expiration, type=call for a bullish qualifier / put for
   a bearish qualifier) → ATM or first strike beyond spot in the trade's direction (above
   spot for calls, below spot for puts).
3. `get_option_quotes` → gates: open_interest ≥ `min_open_interest`; spread ≤
   `max_spread_pct_of_mid`% of mid. **Quantity** = floor(`max_premium_per_trade` /
   (mid × 100)), minimum 1 — multiple contracts of the same call or put are allowed.
   `max_premium_per_trade` is the dollar figure computed once in today's premarket run
   (`daily_start_balance × max_premium_per_trade_pct_of_daily_start / 100`, from today's
   journal) — read it from there, don't recompute mid-day. Not capped or scaled by live
   buying power; if settled cash is actually insufficient the order will be rejected at
   placement — treat that as a hard stop for the underlying, don't chase a smaller size.
   Gates fail ATM → next strike further out-of-the-money once → otherwise next candidate.

## 3. Review → authorize → place (per chosen underlying, best-ranked first)
1. `review_option_order`: limit buy-to-open at mid, GFD, regular hours, with chain_symbol +
   underlying_type for fees/collateral. Surface all order_checks alerts verbatim in the
   journal and to the user.
2. If `entry_auto_execute` is **false**: present the trade (symbol, catalyst, contract,
   quote, alerts, cost) via AskUserQuestion and wait. No approval → no trade; journal it.
   If **true**: config records the user's standing authorization — proceed.
3. `place_option_order` with a fresh UUID ref_id (reuse the same ref_id only on transport
   retries). If unfilled after 10 min (`get_option_orders`), cancel and re-place once at
   mid + 40% of half-spread. Still unfilled after 10 more min → cancel, no-trade day.

## 4. Record
Journal the entry: contract, fill price (from the filled order), thesis, planned exits
(`stop_loss_pct`% hard stop / discretionary profit-taking / forced flat), order ids. Commit
("journal: YYYY-MM-DD entry") and push. Then:
- **Position opened** → two follow-ups, in order:
  1. **Place the resting protective order** per `resting_order_type` (only one sell order
     can rest per contract — Robinhood has no OCO for options):
     - `stop_loss`: stop_market sell-to-close, stop_price = entry × (1 + stop_loss_pct/100),
       rounded to tick, GFD. Monitor loop handles profit-taking in software.
     - `take_profit`: limit sell-to-close at entry × (1 + take_profit_pct/100), rounded to
       tick, GFD. Monitor loop handles the stop in software.
     **9:30–9:45 blackout:** Robinhood rejects stop_market before 9:45 ET
     (`OPTION_STOP_MARKET_INVALID_TIME_MARKET_OPEN`). If the fill lands before 9:45, do
     NOT end the turn unprotected — run ~1-minute software stop checks (get_option_quotes;
     mark ≤ stop level → sell-to-close at mid immediately), then place the resting stop at
     9:45 sharp and confirm it before proceeding.
     Quantity = the full filled position quantity. Fresh ref_id; covered by the same
     standing authorization as the entry. Record the order id in the journal — every later
     close must CANCEL this order first.
  2. Start the **monitor loop**: `send_later` in 5 minutes to execute
     `runbooks/monitor.md` (the software side of stop/TP, discretion, re-entries).
- **No trade** → arm a **re-check**: `send_later` in 10 minutes to re-run this runbook
  from §0 (guards apply fresh each time; journal only changes, not full re-writes).
  Re-checks stop at 1:30 PM ET or when an entry fills, whichever comes first. A late
  qualifier must pass the same gates — no loosening because the morning was quiet — PLUS
  the late-re-check volume bar (STRATEGY.md §3): several consecutive closes in the trade
  direction on rising/elevated volume, sustained 15+ minutes. A quiet low-volume reclaim
  of the open does not qualify.
