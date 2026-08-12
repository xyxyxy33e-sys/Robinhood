# Runbook: Monitor loop (every 1 minute while a position is open)

Started by the entry runbook after a fill; self-perpetuating via `send_later`
(delay_minutes=1, tightened from 3 on 2026-08-06 per user, which itself was tightened
from 5 on 2026-07-28 per user). Read `config.yaml` and
today's journal first. All times US/Eastern.

## Loop resilience (added 2026-08-05 per user, after a `get_equity_historicals` call
failed mid-cycle on a transient "model temporarily unavailable" auto-mode classifier
error and the loop died silently — no `send_later` had been armed yet for the next
cycle, so nothing woke it back up until the user manually said "continue")
If any tool call in a firing fails on a transient/infrastructure error (classifier
unavailable, timeout, rate limit — not a logic or data error): retry once or twice
within the same firing. Whether or not the retry succeeds, still reach the re-arm
step at the end of this firing — journal "data fetch failed this cycle, retrying
next" (or similar) in place of the normal update if the retries also failed, and
call `send_later` for the next cycle regardless. The loop must never end a firing
without either closing a position or arming the next one; a single bad tool call
should cost at most one cycle's data, never the whole loop.

## Each firing
1. `git pull` the branch (config may have changed), read config + today's journal.
2. `get_option_positions` (nonzero=true) for `account_number`; match against the
   strategy's positions recorded in today's journal. Check the resting protective order
   (`get_option_orders` by its id from the journal): if it FILLED, the position is closed
   (win if take_profit, stop-out if stop_loss) — journal it and treat as flat. If the
   position is gone but the resting order didn't fill, the user closed it manually —
   cancel the resting order, journal the user's fill from get_option_orders, treat as flat.
3. **Stop_limit → stop_market upgrade (added 2026-08-03). ⚠ DEAD CODE as of 2026-08-12 —
   entry now starts at 10:30, so no fill can land inside the 9:30-9:45 blackout and no
   position will ever carry an "upgrade at 9:45" flag. Retained purely as a safeguard in
   case entry timing is moved back before 9:45; skip this step in normal operation:**
   if today's journal flagged this position's resting order as a pre-9:45 stop_limit
   ("upgrade at 9:45") and current ET time is now ≥ 9:45, cancel it (`get_option_orders`
   confirms `cancelled`) and place a stop_market at the SAME stop_price, fresh ref_id,
   verify `state: confirmed`. Update the journal with the new order id/type and drop the
   "upgrade at 9:45" flag. One-time transition per position — do this before any of the
   cascade checks below, and skip entirely for positions whose resting order is already
   a stop_market (either placed that way originally, at/after 9:45, or already upgraded
   on a prior cycle).
3b. **Ratchet stop_limit → stop_market upgrade near close (added 2026-08-06):** if this
   position's resting order is currently a ratchet-placed stop_limit (see the ratchet-arm
   bullet in §4 below) and current ET time is now ≥ `ratchet_stop_limit_cutoff_et`, cancel
   it (`get_option_orders` confirms `cancelled`) and place a stop_market at the SAME
   stop_price, fresh ref_id, verify `state: confirmed`. Update the journal with the new
   order id/type. One-time transition per position, same mechanic as the 9:45 upgrade in
   §3 — past this cutoff, certainty of getting flat before `forced_close_start_et` matters
   more than bounding slippage. Skip entirely for positions whose resting order is a
   stop_market already, or whose ratchet hasn't armed yet.
4. For each open strategy position, `get_option_quotes`. Software-side of whichever
   protection is NOT resting (per `resting_order_type`):
   **Quote-depth gate (added 2026-07-31, applies to every resting-stop cancel+replace
   below — ratchet-arm, stall-trail, early floor — whether the new order is stop_market
   or, per the 2026-08-06 ratchet_stop_type option, stop_limit):** immediately before cancelling the
   resting stop and placing a new one, re-`get_option_quotes` fresh (don't reuse the
   read from earlier this cycle — it may be stale by the time cancel+place executes)
   and require `bid_size ≥ min_quote_size_for_stop_update` AND
   `ask_size ≥ min_quote_size_for_stop_update`. If either side is thinner than that,
   the quote is too thin to trust for firing a stop_market — do NOT cancel/replace
   this cycle; leave the current resting stop exactly where it is (it still fully
   protects the position, just hasn't been raised yet) and journal "ratchet would
   raise stop to $Y but quote too thin (bid Xc/ask Yc) — holding at $Z, retrying next
   cycle." Motivated by AMZN (2026-07-31): the ratchet computed a new stop off a mark
   backed by thin size, and by the time cancel+place executed the quote had already
   cratered on a print backed by a single-digit contract of depth — the stop_market
   fired instantly at $3.50 even though the underlying itself was still near its
   session highs. This gate only ever delays a stop from being raised (never removes
   protection, since the existing resting stop stays in place) and is a numeric
   threshold, not a judgment call — the mechanical no-discretion property of the stop
   system is unchanged. Does NOT apply to the stop_loss/hard-TP/scale-out mark
   comparisons above (those trigger a LIMIT sell at mid with a reprice window, not a
   blind stop_market fire, so thin-quote risk doesn't apply the same way).
   - **mark ≤ entry × (1 + stop_loss_pct/100)** (when the stop is software-side) → CANCEL
     the resting order first, then close NOW per exit runbook §2 (limit at mid, reprice to
     bid after 3 min, no discretion). Journal the stop-out.
> **⚠ THRESHOLD VALUES BELOW ARE PRE-2026-08-12 AND ARE NOW HISTORICAL NARRATIVE.**
> On 2026-08-12 expiry selection moved to `dte_target: 14`, roughly halving contract
> leverage (~14.6x → ~8.6x), and every profit-side threshold was scaled by 0.59 so it
> represents the **same underlying move** as before. Current values live in
> `config.yaml`, which is authoritative — the runbooks read them by name, so behaviour
> is already correct; only the prose numbers below are stale.
> **arm 20→12 · hard TP 50→30 · scale-out 40→24 · TP floor 10→6 · THIN arm 12→7 ·
> early floor 8→5 / −3→−2 · midday trigger 3→2 · late-day 5→3 · scale-out floor −15→−9.**
> **`stop_loss_pct` stays −25 deliberately** — not scaling it is what widens the stop's
> tolerance from 1.71% to 2.90% of underlying movement, which is the entire point.
> Trail percentages (30/20/10) also unchanged: give-back from a peak is leverage-neutral.
> Rationale, arithmetic and verification: `config.yaml` "EXIT-THRESHOLD RECALIBRATION"
> and `journal/2026-08-12.md`.

   - **mark ≥ entry × (1 + hard_take_profit_pct/100)** (raised to +50% on 2026-07-28,
     briefly +30% earlier that day, originally +100%) → CANCEL the resting stop first
     (verify cancelled), then sell-to-close at mid immediately — NO discretion, winners
     get capped as mechanically as losers get stopped. If unfilled in 1 min, reprice
     toward the bid. Journal the win ("hard TP: sold at $X, +Y%"). **Note:** at +50% both
     `take_profit_pct` (20%, arms the ratchet) and `scale_out_pct` (40%) sit live inside
     this window and are checked before the position could ever reach the hard cap.
   - **mark ≥ entry × (1 + scale_out_pct/100), quantity ≥ 2, not yet scaled out today**
     (check the journal for a "SCALED OUT" entry on this position) → partial profit lock
     (added 2026-07-23, re-activated 2026-07-28): CANCEL the resting stop (verify
     cancelled), sell floor(qty/3)
     contracts (min 1) limit at mid — reprice toward the bid after 1 min if unfilled —
     then re-place the resting stop for the REMAINING quantity at max(previous stop,
     entry × (1 + scale_out_floor_pct/100)) rounded to tick (depth-gated per above) —
     the −15% floor keyed to ORIGINAL entry (or the ratcheted price if the ratchet
     also triggers this cycle; stops only move up). Fresh ref_ids throughout; verify
     the new stop is `confirmed`.
     Journal "SCALED OUT: sold N of M @ $X, stop raised to $Y for remainder". Once per
     position per day; 1-contract positions skip. Checked AFTER hard-TP, BEFORE the
     ratchet.
   - **Scaled-out tranche RE-BUY** (lighter bar, user-approved 2026-07-23; check each
     cycle while a "SCALED OUT" position is still open, not yet re-bought today, and
     it's before 3:00 PM ET): if the latest 5-min bar closed with the underlying back
     on the trade-direction side of VWAP (put: below; call: above) — no volume or
     15-minute-sustain requirement — buy back up to the scaled-out quantity of the SAME
     contract, limit at mid, funded by settled cash only (scale-out proceeds are T+1
     and cannot fund it). Position may not exceed its original size. After the fill,
     cancel the resting stop and re-place it for the full new quantity at the SAME
     stop level (unchanged — floors stay keyed to original entry). Journal
     "RE-ENTERED tranche: bought N @ $X (sold @ $Y), stop re-placed for full qty".
   - **Thin-liquidity thresholds (added 2026-08-06):** if this position was journaled
     "LIQUIDITY: THIN" at entry (per entry.md §2), use `thin_liquidity_take_profit_pct`
     (12) in place of `take_profit_pct` (20) for the arm trigger below, and
     `thin_liquidity_stop_ratchet_trail_pct` (20) in place of `stop_ratchet_trail_pct`
     (30) in the required-stop formula once armed — bank the profit lock sooner and trail
     tighter on a name with proven exit-slippage risk. Liquid positions are unaffected.
   - **mark ≥ entry × (1 + take_profit_pct/100)** (lowered to +20% on 2026-07-28, was
     50% — "start considering sale"; or `thin_liquidity_take_profit_pct`/12 for
     THIN-flagged positions per above) → the ratchet ARMS (no forced sale). While armed:
     required stop = max(entry × (1 + take_profit_floor_pct/100), high-water mark × (1 −
     stop_ratchet_trail_pct/100, or `thin_liquidity_stop_ratchet_trail_pct`/20 if THIN)),
     rounded to tick — floor raised from breakeven to +10%
     on 2026-07-28 — track the high-water mark from the journal's mark history plus this
     check's quote. If the required stop exceeds the current resting stop, CANCEL the
     resting stop and place the new higher stop (depth-gated per above; fresh
     ref_id, verify `state: confirmed`, record the new order id). Stops only ever move
     UP. **Order type (added 2026-08-06):** if `ratchet_stop_type` is `stop_limit` AND
     current ET time is before `ratchet_stop_limit_cutoff_et`, place the new stop as a
     stop_limit (stop_price as computed above; limit_price = stop_price × (1 −
     `ratchet_stop_limit_buffer_pct`/100), rounded to tick) instead of stop_market —
     bounds slippage on a contract already carrying a real profit cushion. Otherwise
     (config set to `stop_market`, or at/after the cutoff) place stop_market as before.
     Once a stop_limit is placed this way, every subsequent ratchet/stall-trail raise on
     this position also re-computes its limit_price the same way and stays stop_limit
     until either filled or upgraded to stop_market by §3b near the close. Journal each
     ratchet with its order type ("ratchet: stop $X → $Y (stop_limit, limit $L), HWM $Z"
     or "... (stop_market) ..."). With a 20-50% window before the hard-TP cap above,
     arming typically snaps the stop to entry × 1.10 first (a HWM only modestly above
     entry, trailed 30%, computes below the +10% floor) — but as the position runs further
     toward +50%, the HWM-trail component can overtake the floor and raise the stop above
     +10%. Both are expected, not a bug.
     **Stall-trail (added 2026-07-28, secondary layer, checked every cycle while armed):**
     classify this cycle's 5-min bar on the underlying as EXTENDING (new local high, still
     on the trade-direction side of VWAP, volume steady/rising) or STALLING (anything
     short of that — a lighter bar than the full momentum-broken check below, which needs
     ALL three conditions against it together). On a STALLING read, also compute HWM × (1
     − stop_ratchet_stall_trail_pct/100) (10%, vs. the normal 30% trail) and take the
     higher of it vs. the normal required stop from above (this replacement is also
     depth-gated per above). This reacts to a pause the
     moment it happens rather than waiting for the wider trail or the +10% floor to
     eventually be crossed. If the resulting level is already at or above the current
     mark (a sharp single-cycle pullback jumped past it before a stop could be placed),
     don't attempt to place a stop_market above the live price — instead CANCEL the
     resting stop and sell-to-close at mid immediately this cycle (same mechanic as the
     hard-TP cap). Journal which classification applied each cycle while armed ("stall
     check: EXTENDING/STALLING, tightened stop $X → $Y" or "... sold at mid, stop already
     breached").
   - **Early floor (added 2026-07-30, pre-arm only — a no-op once the ratchet above has
     armed): mark ≥ entry × (1 + early_floor_trigger_pct/100)** (+8%, first touch) →
     required stop = entry × (1 + early_floor_pct/100) (-3%, i.e. just below breakeven).
     If this exceeds the current resting stop, CANCEL and place the new higher
     stop_market same as the ratchet (depth-gated per above; fresh ref_id, verify
     confirmed). Stops only ever move UP. Motivated by AMD and MSFT's failed leader
     re-entry on 2026-07-30, both of
     which peaked +8-11.5% — real, thesis-confirming pops — then ground down on theta for
     nearly an hour without ever reaching the +20% arm level, round-tripping all the way
     to the stop_loss floor with zero protection in between. Journal ("early floor: stop
     $X → $Y"). Once take_profit_pct (+20%) arms, its floor (+10%) is already higher than
     this one, so no conflict — just check the ratchet first each cycle.
   - **Midday floor (added 2026-08-03, pre-arm only, checked only while the current ET
     time is within [`midday_floor_window_start_et`, `midday_floor_window_end_et`] —
     11:30 AM-1:30 PM ET): mark ≥ entry × (1 + midday_floor_trigger_pct/100)** (+3%,
     first touch during the window) → required stop = entry × (1 + midday_floor_pct/100)
     (breakeven). If this exceeds the current resting stop, CANCEL and place the new
     higher stop_market (depth-gated per above; fresh ref_id, verify confirmed). Stops
     only ever move UP. Check this AFTER the early floor above each cycle — whenever both
     are eligible (mark ≥ 8% during the window), this floor (breakeven) is always the
     higher constraint and supersedes the early floor's -3%. Outside the window, this
     check is skipped entirely and the early floor alone applies as before. Motivated by
     BABA (2026-08-03): peaked only +5% at 11:40 ET — below the +8% early-floor trigger,
     so no protection engaged — then faded through the midday session to a full -25%
     stop-out. A backtest of 07/16-08/03 (23 trades) found only 3 trades whose
     high-water mark occurred in this window AND were still open past 1:30 PM (the only
     ones that actually test "does a midday peak keep extending?"); all 3 faded, averaging
     -28% (IREN 7/21, BABA 122C 7/20, BABA 8/03) — zero counterexamples, though n=3 is
     thin. Journal ("midday floor: stop $X → $Y"). No re-entry restriction is tied to
     this rule — a close it triggers gets the standard §5 re-entry check like any other
     exit, still subject to the 1:30 PM cutoff.
   - **Late-day floor (added 2026-08-06, pre-arm only, checked only while current ET time
     is within [`late_day_floor_window_start_et`, `late_day_floor_window_end_et`] —
     1:30-3:00 PM ET, picking up right where the midday window ends): mark ≥ entry × (1 +
     late_day_floor_trigger_pct/100)** (+5%, first touch during the window) → required
     stop = entry × (1 + late_day_floor_pct/100) (+5% — an actual profit lock, not just
     breakeven like the midday floor). If this exceeds the current resting stop, CANCEL
     and place the new higher stop (depth-gated per above; order type follows the same
     `ratchet_stop_type`/cutoff logic as the ratchet-arm bullet if that's also eligible,
     otherwise stop_market; fresh ref_id, verify confirmed). Stops only ever move UP. When
     multiple pre-arm floors are eligible at once (early floor, midday floor, this one),
     take the highest required stop of the group — purely mechanical, no ordering
     judgment needed since they're all just candidate floors feeding the same "stops only
     move up" rule. Motivated by U's second trade (2026-08-06): sat around +10-11% for
     several cycles around 3:00 PM ET, well below the +20% ratchet, then the eventual exit
     banked only +2.28% after slippage — a position that spends real time solidly positive
     this late in the day, without ever arming the full ratchet, should already be locking
     in some of that gain rather than staying exposed to a full round-trip risk with only
     ~40 minutes left before `forced_close_start_et`. Journal ("late-day floor: stop $X →
     $Y").
   - **in profit, momentum broken** (5-min bars: lower highs, VWAP lost, volume faded) →
     discretionary sell-to-close per STRATEGY.md §6 — CANCEL the resting order first.
     Journal the reasoning. (Applies armed or not — the ratchet is a floor, not a reason
     to hold through a confirmed breakdown.)
   - otherwise hold; log a one-line mark update in the journal (batch-commit these —
     push at most every ~30 min to avoid commit spam, and always push after a trade).
5. **Re-entry check** (only if all of: now < 1:30 PM ET; total open positions <
   `max_open_positions`; today's entry count < `max_new_positions_per_day`; options
   buying power ≥ `min_buying_power_to_trade`): run the entry runbook §1–§4 for a NEW
   candidate, call or put. **Check leader re-entries FIRST** (STRATEGY.md
   §3): any symbol closed earlier today for a profit is the top-priority candidate — but
   only on a resumption signal (pullback stabilized at a higher low, then a fresh
   volume-confirmed push per the late-re-check bar), never on the dip itself. Re-buying a
   symbol closed earlier today (including after a stop-out) is allowed. Cash-account note:
   proceeds from any sale today settle T+1 and cannot fund a re-entry; only remaining
   settled cash can.

## Re-arm or stop
- **Re-arm** (`send_later`, 1 min) if any strategy position is open and it's before
  3:25 PM ET.
- **Stop the loop** when: flat with no re-entry possible (past 1:30 PM ET or daily entry
  limit reached), or it's 3:25 PM ET or later (the 3:30 exit Routine owns the close from
  here — never leave both racing). On stopping, journal a final marks summary, commit, push.
