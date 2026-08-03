# Runbook: Entry (9:45 AM ET, Mon–Fri; re-checks every 3 min until 1:30 PM on no-trade)

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` (pre-market section) first.
All times US/Eastern. Account = `account_number` from config.

## 0. Guards — every one must pass or the day is a no-trade
1. Trading day check (same as premarket). Market closed → journal, push, stop.
2. Time check: if before 9:45 ET, schedule a self check-in (`send_later`) for 9:45 ET and
   stop; if after 1:30 PM ET, skip the day (momentum entries decay) — journal why.
   (Entry moved from 9:35 to 9:45 on 2026-07-31 per user: 9:45 is when Robinhood first
   accepts resting stop_market orders, so every fill is now protected broker-side
   immediately — no software-only window. Cost: gives up the first 15 minutes of the
   move; on 2026-07-31 that window produced two of the day's three whipsaw stop-outs.)
3. `get_option_positions` (nonzero=true): count total open positions (calls + puts
   combined). If total ≥ `max_open_positions`, stop (no room). Otherwise continue.
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
   - **Calls:** `get_equity_historicals` interval=5minute from 9:30 — require price >
     open, price ≥ prior close × (1 + min_day_change_pct/100), price > VWAP, and no
     full gap-fade (still above the low of the opening 15 minutes).
   - **Puts:** require price < open, price ≤ prior close × (1 − min_day_change_pct/100),
     price < VWAP, and no full gap-fill (still below the high of the opening 15 minutes).
   (The old 9:30–9:35 minute-bar branch was removed 2026-07-31 when entry moved to 9:45 —
   there are now always three 5-minute bars of session to confirm against, which is the
   point: the opening 15 minutes' whipsaws get to play out before capital is committed.)
4. `get_earnings_results` on finalists — reject if earnings before option expiry.
5. Rank the qualifiers (catalyst > relative volume > tape), calls and puts together, and
   take **up to (max_open_positions − currently open positions total)** qualifiers, best
   first across BOTH directions combined (no fixed split between calls and puts) — each
   independently passing every gate in §2–§3. Re-entering a symbol
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
   **Notify the user directly** when this happens for a candidate that otherwise fully
   qualified (tape + liquidity gates both passed) — don't just log it in the journal and
   move on silently (added 2026-07-30, after a genuine MSFT setup was rejected on
   `OPTION_NOT_ENOUGH_BP_FOR_PREMIUM` with buying power tied up in T+1-settling proceeds
   from earlier same-day closes). Journal it either way.
   Gates fail ATM → next strike further out-of-the-money once → otherwise next candidate.
4. **OI is static intraday (learned 2026-07-24):** open interest updates once daily,
   after settlement — a strike that fails the OI gate stays failed ALL DAY no matter how
   strong the tape gets; only the spread can improve intraday. On re-checks, do NOT
   re-pull quotes for a contract that already failed on OI today. A name whose ATM and
   step-out strikes have both failed on OI is dead for the day UNLESS spot has moved far
   enough that the ATM shifts to a strike not yet checked. The premarket journal records
   each candidate's ATM OI (chain pre-screen) — trust it; a "chain dead" flag from
   premarket means skip contract selection for that name entirely.

## 3. Review → authorize → place (per chosen underlying, best-ranked first)
1. `review_option_order`: limit buy-to-open at mid, GFD, regular hours, with chain_symbol +
   underlying_type for fees/collateral. Surface all order_checks alerts verbatim in the
   journal and to the user.
2. If `entry_auto_execute` is **false**: present the trade (symbol, catalyst, contract,
   quote, alerts, cost) via AskUserQuestion and wait. No approval → no trade; journal it.
   If **true**: config records the user's standing authorization — proceed.
3. `place_option_order` with a fresh UUID ref_id (reuse the same ref_id only on transport
   retries). If unfilled after 5 min (`get_option_orders`), cancel and re-place once at
   mid + 40% of half-spread. Still unfilled after 5 more min → cancel, no-trade day.

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
     **9:30–9:45 blackout (should no longer apply in normal operation):** Robinhood
     rejects stop_market before 9:45 ET (`OPTION_STOP_MARKET_INVALID_TIME_MARKET_OPEN`).
     Since entry moved to 9:45 (2026-07-31), fills land after the blackout and the
     resting stop can always be placed immediately — place it and confirm `confirmed`
     before doing anything else. Kept as a safeguard for edge cases only (clock drift,
     a fill racing the 9:45 boundary): if a stop_market is ever rejected with that
     error, do NOT end the turn unprotected — run software stop checks every
     `blackout_stop_check_interval_sec` (get_option_quotes; mark ≤ stop level →
     sell-to-close at mid immediately), then place the resting stop the moment it's
     accepted. History: this gap produced MSFT's slippage on 7/28-week and AAPL's
     -39.6% stop-out on 7/31 (entered 9:39:46, reversed before a ~60s-cadence check
     could act) — which is why entries now start at 9:45 at all.
     Quantity = the full filled position quantity. Fresh ref_id; covered by the same
     standing authorization as the entry. Record the order id in the journal — every later
     close must CANCEL this order first.
  2. Start the **monitor loop**: `send_later` in 3 minutes to execute
     `runbooks/monitor.md` (the software side of stop/TP, discretion, re-entries).
- **No trade** → arm a **re-check**: `send_later` in 3 minutes to re-run this runbook
  from §0 (guards apply fresh each time; journal only changes, not full re-writes).
  Re-checks stop at 1:30 PM ET or when an entry fills, whichever comes first. A late
  qualifier must pass the same gates — no loosening because the morning was quiet — PLUS
  the late-re-check volume bar (STRATEGY.md §3): several consecutive closes in the trade
  direction on rising/elevated volume, sustained 15+ minutes. A quiet low-volume reclaim
  of the open does not qualify.

## TEMPORARY: 9:35 shadow-entry tracking (2026-08-04 through 2026-08-07 — review with
user after Friday 8/7 close, then remove this section)
Per user request (2026-08-03): 9:45 stays the real entry time this week, but run a
PAPER-ONLY parallel comparison of what a 9:35 ET entry (using a resting stop_limit,
confirmed accepted during the 9:30-9:45 blackout on 2026-08-03, unlike stop_market)
would have done instead. No real orders are ever placed for this track.
1. At (or shortly after) 9:35 ET, using the day's premarket-ranked candidates and the
   SAME tape-check rules as §1.3 but with only the single 9:30-9:35 5-minute bar
   available (the pre-2026-07-31 single-bar check) — determine whether the top
   candidate would have qualified. If yes: pick the hypothetical contract/strike/
   quantity exactly per §2's rules (using that moment's spot price — this may differ
   from the real 9:45 contract if spot has since moved) and journal "9:35 SHADOW ENTRY
   (paper only): contract, hypothetical entry price (bar mid), quantity, planned
   exits." If no qualifier at 9:35, journal that too — the comparison needs the "no
   trade" cases as much as the trades.
2. During each 3-min monitor cycle for the rest of the day, ALSO pull
   `get_option_quotes` (or historicals, if catching up after a gap) for the shadow
   contract and apply the exact same cascade from monitor.md §3 (stop_loss, hard-TP,
   scale-out, ratchet-arm + stall-trail, early floor, midday floor) on paper. Journal
   "SHADOW: mark $X (±Y%) — [action]" alongside the real position's entry each cycle.
   When the shadow position would exit under any rule, journal the hypothetical fill
   price and realized P&L, and stop shadow-tracking for the day (one shadow track per
   day, no shadow re-entry search — keep this lightweight).
3. On 2026-08-07 (Friday) close, compile a comparison table (real 9:45 trades vs.
   shadow 9:35 trades: entry price, exit price/reason, P&L) across the week plus
   today's (8/3) retroactive reconstruction, and review with the user before deciding
   whether to change the real entry time.
