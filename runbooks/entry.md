# Runbook: Entry (9:30 AM ET at the open, Mon–Fri; re-checks every 15 min until 11:30 on no-trade)

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` (pre-market section) first.
All times US/Eastern. Account = `account_number` from config.

## 0. Guards — every one must pass or the day is a no-trade
1. Trading day check (same as premarket). Market closed → journal, push, stop.
2. Time check: if before 9:30 ET, schedule a self check-in (`send_later`) for 9:30 ET and
   stop; if after 11:30 ET, skip the day (momentum entries decay) — journal why.
3. `get_option_positions` (nonzero=true): if open positions ≥ `max_open_positions`, stop.
4. `get_option_orders` (state=queued/confirmed, created today): no duplicate entry if an
   order is already working. Also check today's journal — if an entry was already made
   today (max_new_positions_per_day), stop.
5. `get_portfolio`: options buying power < `min_buying_power_to_trade` → journal
   "insufficient settled cash", notify user once (not every day — check whether yesterday's
   journal already flagged it), stop.

## 1. Confirm momentum (live)
1. `run_scan` on `scan_id` — live matches now meaningful.
2. Merge with pre-market candidates; drop anything that hit its "disqualify if".
3. For the top 2–3, tape check scaled to how much session exists:
   - **9:30–9:40:** `get_equity_historicals` interval=minute — require last > opening
     print, last ≥ prior close × (1 + min_day_change_pct/100), and no immediate reversal
     (not below the session low of the first bars). Accept that this window trades on
     pre-market conviction with less confirmation.
   - **after 9:40:** interval=5minute from 9:30 — require price > open, price > VWAP,
     and no full gap-fade (above the 9:30–9:40 low).
4. `get_earnings_results` on finalists — reject if earnings before option expiry.
5. Pick ONE winner (catalyst > relative volume > tape). No qualifier → no trade; journal it.

## 2. Select the contract
1. `get_option_chains` (underlying_symbol) → pick expiration in [dte_min, dte_max].
2. `get_option_instruments` (chain, expiration, type=call) → ATM or first strike above spot.
3. `get_option_quotes` → gates: open_interest ≥ `min_open_interest`; spread ≤
   `max_spread_pct_of_mid`% of mid; 1 contract at mid ≤ min(`max_premium_per_trade`,
   `max_premium_pct_of_bp`% of buying power). Quantity is 1 contract (this account size
   never supports more). Gates fail ATM → next strike up once → otherwise next candidate.

## 3. Review → authorize → place
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
- **Position opened** → start the **monitor loop**: `send_later` in 5 minutes to execute
  `runbooks/monitor.md` (stop-loss enforcement, discretionary profit-taking, re-entries).
- **No trade** → arm a **re-check**: `send_later` in 15 minutes to re-run this runbook
  from §0 (guards apply fresh each time; journal only changes, not full re-writes).
  Re-checks stop at 11:30 ET or when an entry fills, whichever comes first. A late
  qualifier must pass the same gates — no loosening because the morning was quiet.
