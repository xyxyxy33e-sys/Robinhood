# Runbook: Entry (10:30 AM ET, Mon–Fri; re-checks every 1 min until 1:30 PM on no-trade)

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` (pre-market section) first.
All times US/Eastern. Account = `account_number` from config.
Re-check cadence tightened from 3 min to 1 min on 2026-08-06 per user (applies to both
the no-trade re-check loop and the initial monitor-loop kickoff after a fill).

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
2. Time check: **if before 10:30 ET, schedule a self check-in (`send_later`) for 10:30 ET
   and stop**; if after 1:30 PM ET, skip the day (momentum entries decay) — journal why.
   **ENTRY START MOVED 9:35 → 10:30 on 2026-08-12 per user**, on a 20-name-day backtest
   across 8 sessions (2026-07-16 → 08-12; full tables in journal/2026-08-12.md). The
   finding: opening 30-minute ranges on gapped momentum names run **5-9%**, while a −25%
   stop on an ATM 2-DTE call tolerates only **~1.6%** of adverse underlying movement —
   the stop is 3-6× tighter than opening volatility, so a correctly-directioned position
   is stopped out by noise unrelated to its thesis. Measured stop-out rate by entry time:
   **09:30 → 60%, 10:00 → 50%, 10:30 → 45%, 11:00 → 30%**; simulated option P&L (real
   cascade: −25% stop, +50% TP, +10% floor after +20%) favoured 10:30-11:00 at every
   leverage assumption tested (10×/12×/15×), and at 12×/15× the **median** outcome of a
   9:35 entry was a full −25% stop-out. 10:30 chosen over 11:00 to keep entry-window
   length; note 10:00 is NOT a valid compromise — it was the worst non-09:30 cell at 15×.
   Caveats on the record: n=20, the sample inherits the existing screens' bias, the
   backtest assumes a name still qualifies at the later hour, and theta (~2-4%/hour on
   2-DTE premium) argues mildly against waiting. Revisit if stop-outs do not fall.
   *History:* 9:35 → 9:45 on 2026-07-31, back to 9:35 on 2026-08-03, made "permanent" on
   2026-08-07 after a week-long shadow comparison that was inconclusive (four of five
   days were washes because chain liquidity, not timing, bound). That comparison never
   measured stop-out rates against opening volatility, which is what this change is based
   on.
   **Consequence — the 9:30-9:45 stop_market blackout is now unreachable.** A 10:30+ fill
   always gets a real stop_market immediately, so the pre-9:45 stop_limit path in §4 and
   the 9:45 upgrade in monitor.md are dead code in normal operation. Both are retained
   only as safeguards in case entry timing is ever moved back.
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
3. For each surviving candidate (check the best-ranked first), tape check, direction-aware.
   Since the entry window now starts at 10:30 (see §0.2), **every pass has a full hour of
   tape** — ~12 five-minute bars — so the single tape test below always applies:
   `get_equity_historicals` interval=5minute from 9:30. Require price > open, price ≥
   prior close × (1 + min_day_change_pct/100), price > VWAP, and no full gap-fade, using
   all available 5-minute bars. Puts invert every leg: price < open, price ≤ prior close ×
   (1 − min_day_change_pct/100), price < VWAP, no full gap-fill.
   Because this is by definition a "later" pass, the §4 late-re-check volume bar
   (STRATEGY.md §3.2) **always applies too**: a volume-confirmed breakout — several
   consecutive closes in the trade direction on rising/elevated volume, sustained 15+
   minutes. Measure "elevated" against the name's own trailing baseline rather than by
   eye; on 2026-08-12 this single test correctly passed NBIS (2.9× baseline) and SMCI's
   third push (3.4×) while rejecting SMCI's first two pushes (0.9× — an advance on
   *declining* volume), and it was decisive four times in one session.
   *Removed 2026-08-12:* the old thin "initial 9:35 pass" that read only the five
   9:30-9:35 one-minute bars. It existed solely because entry started at 9:35; with a
   10:30 start there is never a five-minute-of-tape situation, and that pass was the one
   most exposed to the opening-volatility problem the timing change addresses.
4. **Opening gap-fade guard (added 2026-08-12 per user — see config.yaml
   "Opening gap-fade guard" for the full derivation and the 7-candidate evidence
   table).** Skip entirely if `opening_fade_guard_enabled` is false. Both gates are
   blocking-only: they can veto a candidate, never promote one, and they run AFTER the
   §1.3 tape check on candidates that already passed it.
   First compute the gap: `open_price` of the 9:30 5-min bar vs. prior close. If
   |gap| < `opening_fade_guard_min_gap_pct`, neither gate applies — this name has no
   premarket gap supply to distribute. Otherwise:
   - **Gate A — opening-bar acceptance.** From the FIRST 5-min regular-session bar
     (09:30-09:35), compute `close_position = (close − low) / (high − low)`.
     - Calls: require `close_position ≥ opening_bar_min_close_position`.
     - Puts: require `close_position ≤ 1 − opening_bar_min_close_position`.
     A failure means the gap is being sold into, not bought — **skip this candidate**
     and move to the next. It is not dead for the day: the name becomes eligible again
     once a later 5-min bar CLOSES above the opening bar's high (below its low for
     puts) on volume at least matching the prior bar — the overhead supply clearing.
     Journal the reclaim when it happens ("GAP-FADE GATE A cleared: SYM reclaimed
     $X opening-bar high on rising volume"). After a reclaim the candidate returns to
     the normal flow and must still pass Gate B and every §2-§3 gate.
     Always computable now that entry starts at 10:30 — the 09:30-09:35 bar closed
     ~an hour before the first pass. (Before 2026-08-12 this had to be deferred on the
     initial 9:35 pass because the bar had not closed yet.)
   - **Gate B — opening-window chase guard. ⚠ INACTIVE BY CONSTRUCTION as of 2026-08-12:**
     `opening_window_end_et` is 10:30 and the entry window now *starts* at 10:30, so this
     gate can never fire. It is left in place, not deleted, because the entry-timing
     change subsumes what it was protecting against — it existed to stop us buying the top
     of the opening push, and we no longer trade the opening push at all. **Flagged to the
     user rather than silently repurposed:** if the entry start is ever moved back before
     10:30, this gate becomes live again automatically; if instead you want chase
     protection inside the new 10:30-13:30 window, `opening_window_end_et` must be raised
     deliberately (e.g. to 11:00). Logic retained below for both cases.
     While the current ET time is before
     `opening_window_end_et`, compute the session high (session low for puts) across
     all bars so far and reject the candidate if the live price is within
     `opening_window_chase_guard_pct`% of it — that is buying the top of the push
     rather than a pullback's higher low. Journal it ("GAP-FADE GATE B: SYM $X is
     0.74% under its $Y session high, inside the 1.5% chase guard — waiting for a
     pullback"), and re-check it on the normal 1-minute cadence; a name blocked this
     cycle frequently qualifies a few minutes later once it has pulled back and based,
     which is precisely the SMCI entry that worked on 2026-08-12. After
     `opening_window_end_et` this gate is inactive and the §4 late-re-check volume bar
     governs instead.
   Journal every veto with the measured numbers, not just the verdict — these two gates
   are new and their live hit rate needs to be reviewable against outcomes.
5. `get_earnings_results` on finalists — reject if earnings before option expiry.
6. Rank the qualifiers (catalyst > relative volume > tape), calls and puts together, and
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
1. `get_option_chains` (underlying_symbol) → pick the NEAREST expiration in
   [dte_min, dte_max] (the established convention, now written down).
   **Expiry step-out on structural cap (LIVE, added 2026-08-07 per user):** if that
   nearest expiry's chain is structurally capped short of spot — no ATM or OTM strike
   exists in the trade's direction (calls: no strike ≥ spot; puts: no strike ≤ spot),
   as happened with TEAM on 2026-08-07 (spot $146-153 all session, highest 8/14 strike
   $145) — step to the NEXT expiration inside [dte_min, dte_max] and run the normal §2
   gates there instead. Structural-cap cases ONLY: never step out because a strike
   exists but fails OI/spread/size — those failures follow the normal
   next-strike-then-next-candidate cascade at the chosen expiry. Journal the step-out
   explicitly ("EXPIRY STEP-OUT: 8/14 capped at $X < spot $Y → using 8/21").
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
   journal) — read it from there, don't recompute mid-day.
   **Buying-power scaling (CHANGED 2026-08-12 per user — "Remove the forbidding scaling
   down rule, use whatever is in the buying power"):** the premium budget is
   **min(`max_premium_per_trade`, live options buying power)**. Pull buying power fresh
   from `get_portfolio` at selection time and size to whichever is smaller:
   quantity = floor(min(max_premium_per_trade, buying_power) / (mid × 100)), minimum 1.
   A qualifying setup is now taken at whatever size settled cash allows rather than
   skipped. If even 1 contract is unaffordable, that IS a no-trade for the underlying —
   journal it and notify the user.
   *Prior rule, replaced:* quantity was sized off `max_premium_per_trade` alone and
   explicitly "not capped or scaled by live buying power," with an insufficient-cash
   rejection treated as a hard stop and chasing a smaller size forbidden (added
   2026-07-30 after an MSFT setup was rejected on `OPTION_NOT_ENOUGH_BP_FOR_PREMIUM`).
   That rule cost a fully-qualified trade on 2026-08-12: SMCI $37.50C 8/14 passed every
   tape gate (3.4× volume expansion, leader re-entry, new session high) and every
   liquidity gate (OI 1,154, spread 5.71%, depth 167/183), but sizing demanded 31
   contracts ($3,255) against $1,429.66 of buying power — 13 contracts were affordable
   and the trade was skipped entirely. Per user, taking the smaller position is
   preferred to taking none.
   **Still notify the user directly** whenever buying power (not the premium cap) is what
   binds the size, so the funding constraint stays visible instead of silently shrinking
   positions — and journal the two figures side by side (budget vs. buying power).
   Gates fail ATM → next strike further out-of-the-money once → otherwise next candidate.
   **Thin-liquidity flag (added 2026-08-06):** once a contract clears all gates and is
   selected, if its OI is below `thin_liquidity_oi_threshold`, journal it explicitly —
   "LIQUIDITY: THIN (OI X < threshold Y)" — alongside the fill record in §4. This doesn't
   block the trade (it already cleared every gate); it flags the position for the
   tightened exit cascade in monitor.md/exit.md (lower ratchet-arm trigger, tighter trail,
   no last-leg hold at exit) for the rest of its life, since OI is static intraday.
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
3. **Re-verify the spread immediately before placing (added 2026-08-06):** on a contract
   that only just cleared the gates this cycle, the `review_option_order` quote can already
   be stale by the time it returns — U $40C 8/14 cleared `max_spread_pct_of_mid` at 8.7% at
   the gate check, then the review call came back seconds later at 12.86%, back over the
   line. Pull one more fresh `get_option_quotes` right before `place_option_order` and
   recompute the spread; if it's back above `max_spread_pct_of_mid`, **abort — do not
   place** — journal it as an aborted attempt (contract, both spread reads, timing) and
   fall through to the normal no-trade/re-check path for this cycle. Do not chase it by
   repricing to the wider spread; that defeats the gate's purpose. This is a pre-placement
   check only, not a new gate — OI/spread/size were already confirmed once in §2.
4. `place_option_order` with a fresh UUID ref_id (reuse the same ref_id only on transport
   retries). If unfilled after 1 min (`get_option_orders`), cancel and re-place once at
   mid + 40% of half-spread. Still unfilled after 1 more min → cancel, no-trade day.
   (Reprice windows tightened from 5 min to 1 min on 2026-08-06 per user.)

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
  2. Start the **monitor loop**: `send_later` in 1 minute to execute
     `runbooks/monitor.md` (the software side of stop/TP, discretion, re-entries, and —
     while a position's resting order is still the pre-9:45 stop_limit — the upgrade to
     stop_market once 9:45 arrives).
- **No trade** → arm a **re-check**: `send_later` in 1 minute to re-run this runbook
  from §0 (guards apply fresh each time; journal only changes, not full re-writes).
  Re-checks stop at 1:30 PM ET or when an entry fills, whichever comes first. A late
  qualifier must pass the same gates — no loosening because the morning was quiet — PLUS
  the late-re-check volume bar (STRATEGY.md §3): several consecutive closes in the trade
  direction on rising/elevated volume, sustained 15+ minutes. A quiet low-volume reclaim
  of the open does not qualify.

## TEMPORARY: single-gate-exception shadow track (2026-08-10 through 2026-08-14 —
review with user after Friday 8/14 close, then remove or promote to live)
Per user decision 2026-08-07 (analysis in journal/2026-08-07.md "DRAFT proposal"
section). PAPER ONLY — `gate_exception_shadow_only: true` in config.yaml is a hard
switch; no real order may use the exception while it is true.
1. During any §2 contract-selection pass (initial or re-check), when a tape-qualified
   candidate's contract fails the standard three-gate check, test the exception:
   - exactly ONE of the three gates (OI / spread / quote-size) failed, AND
   - the failing gate is NOT quote-size (bid_size ≥ `min_quote_size_for_entry` AND
     ask_size ≥ `min_quote_size_for_entry` must both hold), AND
   - the miss is bounded: OI ≥ `gate_exception_min_oi` if OI failed, or spread ≤
     `gate_exception_max_spread_pct`% of mid if spread failed.
   If it qualifies AND no gate-exception shadow is already open today: journal
   "GATE-EXCEPTION SHADOW ENTRY (paper only): contract, failing gate + value,
   hypothetical entry (mid), quantity = floor(max_premium_per_trade ×
   `gate_exception_size_factor` / (mid × 100)), THIN flag". One shadow per day,
   first-qualified-first-tracked; the real search continues unaffected.
2. On every subsequent loop firing (entry re-check or monitor cycle), pull the shadow
   contract's quote and apply the THIN exit cascade on paper (stop −25%, THIN ratchet
   arm at `thin_liquidity_take_profit_pct` 12% / trail
   `thin_liquidity_stop_ratchet_trail_pct` 20%, early/midday/late-day floors, hard TP
   +50%). Journal "GATE-EXCEPTION SHADOW: mark $X (±Y%) — [action]" each cycle. On a
   paper exit, journal the hypothetical fill and P&L and stop tracking for the day.
3. If the shadow is still open when the entry re-check loop ends (1:30 PM cutoff or a
   real fill switching to monitor.md), it stays open on paper; the EXIT phase (~3:30,
   exit.md reads today's journal and will see the open shadow line) closes it at the
   then-current mid and journals the result.
4. After Friday 8/14's close: compile the week's shadow results (entry, exit, P&L,
   which gate was excepted) vs. the week-of-8/4 backtest, and review with the user
   before deciding whether to flip `gate_exception_shadow_only` to false.
