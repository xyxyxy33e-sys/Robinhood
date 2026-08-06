# Runbook: Entry (9:35 AM ET, Mon–Fri; re-checks every 3 min until 1:30 PM on no-trade)

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` (pre-market section) first.
All times US/Eastern. Account = `account_number` from config.

## Loop resilience (added 2026-08-05 per user, after a `get_equity_historicals` call
during a no-trade re-check failed on a transient "model temporarily unavailable"
auto-mode classifier error and the re-check loop died silently — no `send_later` had
been armed yet for the next cycle, so nothing woke it back up until the user
manually said "continue")
If any tool call in a re-check firing fails on a transient/infrastructure error
(classifier unavailable, timeout, rate limit — not a logic or data error): retry
once or twice within the same firing. Whether or not the retry succeeds, still reach
the re-arm step at the end of this firing — journal "data fetch failed this cycle,
retrying next" (or similar) in place of the normal no-trade note if the retries also
failed, and call `send_later` for the next cycle regardless (guards permitting — see
§0.2). A re-check must never end a firing without either filling a position or
arming the next one; a single bad tool call should cost at most one cycle, never
the rest of the day's search.

## 0. Guards — every one must pass or the day is a no-trade
1. Trading day check (same as premarket). Market closed → journal, push, stop.
2. Time check: if before 9:35 ET, schedule a self check-in (`send_later`) for 9:35 ET and
   stop; if after 1:30 PM ET, skip the day (momentum entries decay) — journal why.
   (Entry moved 9:35 → 9:45 on 2026-07-31, then back to 9:35 on 2026-08-03 per user, now
   paired with the stop_limit-then-upgrade mechanism in §4 below instead of just waiting
   out the blackout. Rationale for going back: the 2026-08-03 diagnostic confirmed
   stop_limit orders — unlike stop_market — ARE accepted during the 9:30-9:45 blackout,
   so a fill before 9:45 can still get real resting protection immediately, just not the
   fully-guaranteed stop_market kind until 9:45. Retroactive check on 2026-08-03's BABA
   trade found a 9:35 entry would have caught a materially bigger move on a
   closer-to-the-money strike before the existing ratchet/stall-trail logic exited it
   for +15.9%, vs. the real 9:45 entry's -26.09% stop-out — though that single day never
   actually tested the stop_limit fill risk, since price never approached a stop level
   during 9:35-9:45. A parallel paper-only 9:45 shadow track (see the TEMPORARY section
   below) runs through Friday 2026-08-07 to build more evidence before this is final.)
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
   - **Initial 9:35 pass (only the single 9:30-9:35 minute bars exist yet):**
     `get_equity_historicals` interval=minute from 9:30 to now (five 1-minute bars).
     Compute VWAP from those bars (typical price × volume, summed and divided by total
     volume) and the opening-window low/high from their low/high.
     - **Calls:** require price > the 9:30 open, price ≥ prior close × (1 +
       min_day_change_pct/100), price > this VWAP, and no full gap-fade (still above the
       low of these five minutes).
     - **Puts:** require price < the 9:30 open, price ≤ prior close × (1 −
       min_day_change_pct/100), price < this VWAP, and no full gap-fill (still below the
       high of these five minutes).
     This is a thinner read than the 9:45 version below (5 minutes of tape vs. 15) —
     genuine whipsaws in the last 10 minutes of the blackout won't have played out yet.
     That's the accepted tradeoff for capturing the move earlier; it's why the resting
     stop in §4 needs to go on immediately rather than waiting for a stop_market slot.
   - **Later re-checks (any check at/after 9:45 ET — no qualifier at 9:35, or a position
     closed and this is hunting for a new one):** `get_equity_historicals`
     interval=5minute from 9:30 — require price > open, price ≥ prior close × (1 +
     min_day_change_pct/100), price > VWAP, and no full gap-fade using all available
     5-minute bars (three or more by 9:45). Same call/put logic, just against the fuller
     multi-bar read.
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
   `max_spread_pct_of_mid`% of mid; **bid_size ≥ `min_quote_size_for_entry` AND
   ask_size ≥ `min_quote_size_for_entry`** (added 2026-08-06 after U $40C 8/14 —
   OI and spread both cleared but ask_size was only 2-4 against a 16-lot buy, and the
   resting stop later swept ~26% through its trigger on a thin book; OI/spread are
   static/percentage measures and don't see top-of-book depth, so check it directly).
   Any one of the three failing is a gate failure — same next-strike-then-next-candidate
   cascade as OI/spread below. **Quantity** = floor(`max_premium_per_trade` /
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
   strong the tape gets; only the spread and quote size can improve intraday (2026-08-06:
   both can also move against you between checks — re-verify size fresh each re-check,
   don't assume a prior pass still holds). On re-checks, do NOT
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
     - `stop_loss`: **if the fill lands before 9:45 ET** — Robinhood rejects stop_market
       until 9:45 (`OPTION_STOP_MARKET_INVALID_TIME_MARKET_OPEN`, confirmed still true on
       2026-08-03), so place a **stop_limit** sell-to-close instead: stop_price =
       entry × (1 + stop_loss_pct/100) rounded to tick (the same trigger a stop_market
       would use), limit_price = stop_price × 0.85 rounded to tick (widened from a 5%
       buffer to 15% on 2026-08-03 per user, for a more realistic chance of filling if
       touched during the blackout — a too-tight limit risks sitting unmarketable on a
       fast move, defeating the point of resting protection at all; confirmed the order
       type itself is acceptable at this time of day via the 2026-08-03 diagnostic test).
       Record it in the journal as a stop_limit, flagged **"upgrade at 9:45."** **If the
       fill lands at/after 9:45
       ET** (a later same-day re-entry, well past the blackout): place stop_market
       directly, no blackout concern, nothing to upgrade later.
     - `take_profit`: limit sell-to-close at entry × (1 + take_profit_pct/100), rounded to
       tick, GFD. Monitor loop handles the stop in software.
     Quantity = the full filled position quantity. Fresh ref_id; covered by the same
     standing authorization as the entry. Record the order id (and type — stop_limit or
     stop_market) in the journal — every later close must CANCEL this order first.
  2. Start the **monitor loop**: `send_later` in 3 minutes to execute
     `runbooks/monitor.md` (the software side of stop/TP, discretion, re-entries, and —
     while a position's resting order is still the pre-9:45 stop_limit — the upgrade to
     stop_market once 9:45 arrives).
- **No trade** → arm a **re-check**: `send_later` in 3 minutes to re-run this runbook
  from §0 (guards apply fresh each time; journal only changes, not full re-writes).
  Re-checks stop at 1:30 PM ET or when an entry fills, whichever comes first. A late
  qualifier must pass the same gates — no loosening because the morning was quiet — PLUS
  the late-re-check volume bar (STRATEGY.md §3): several consecutive closes in the trade
  direction on rising/elevated volume, sustained 15+ minutes. A quiet low-volume reclaim
  of the open does not qualify.

## TEMPORARY: 9:45 shadow-entry tracking (2026-08-04 through 2026-08-07 — review with
user after Friday 8/7 close, then remove this section)
Per user request (2026-08-03): 9:35 is now the real entry time (with the stop_limit
mechanism above), but run a PAPER-ONLY parallel comparison of what waiting for the old
9:45, three-bar-confirmed entry would have done instead — the mirror image of the
tracking done on 2026-08-03 itself (which compared a 9:35 entry against the real 9:45
one). No real orders are ever placed for this track.
1. At 9:45 ET each day, using the day's premarket-ranked candidates, run the "Later
   re-checks" 9:45 three-5-minute-bar tape check from §1.3 above — the fuller-confirmation
   version — independent of whatever the real 9:35 entry already did. If it would
   qualify: pick the hypothetical contract/strike/quantity per §2's rules using that
   moment's spot price (this may differ from the real 9:35 contract if spot has moved,
   or the 9:45 read may reject a candidate the thinner 9:35 read accepted — that
   divergence is exactly what this comparison is for) and journal "9:45 SHADOW ENTRY
   (paper only): contract, hypothetical entry price (mid), quantity, planned exits." If
   no qualifier at 9:45 (including because the real 9:35 trade already reversed by
   then), journal that too.
2. During each 3-min monitor cycle for the rest of the day, ALSO pull
   `get_option_quotes` (or historicals, if catching up after a gap) for the shadow
   contract and apply the exact same cascade from monitor.md §3 (stop_loss, hard-TP,
   scale-out, ratchet-arm + stall-trail, early floor, midday floor) on paper. Journal
   "SHADOW (9:45): mark $X (±Y%) — [action]" alongside the real position's entries each
   cycle. When the shadow position would exit under any rule, journal the hypothetical
   fill price and realized P&L, and stop shadow-tracking for the day (one shadow track
   per day, no shadow re-entry search — keep this lightweight).
3. On 2026-08-07 (Friday) close, compile a comparison table (real 9:35 trades vs.
   shadow 9:45 trades: entry price, exit price/reason, P&L) across the week plus
   2026-08-03's own retroactive/live data points, and review with the user before
   deciding whether 9:35 stays the permanent entry time.
