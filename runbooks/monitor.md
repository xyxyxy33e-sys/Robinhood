# Runbook: Monitor loop (every 3 minutes while a position is open)

Started by the entry runbook after a fill; self-perpetuating via `send_later`
(delay_minutes=3, tightened from 5 on 2026-07-28 per user). Read `config.yaml` and
today's journal first. All times US/Eastern.

## Each firing
1. `git pull` the branch (config may have changed), read config + today's journal.
2. `get_option_positions` (nonzero=true) for `account_number`; match against the
   strategy's positions recorded in today's journal. Check the resting protective order
   (`get_option_orders` by its id from the journal): if it FILLED, the position is closed
   (win if take_profit, stop-out if stop_loss) — journal it and treat as flat. If the
   position is gone but the resting order didn't fill, the user closed it manually —
   cancel the resting order, journal the user's fill from get_option_orders, treat as flat.
3. For each open strategy position, `get_option_quotes`. Software-side of whichever
   protection is NOT resting (per `resting_order_type`):
   - **mark ≤ entry × (1 + stop_loss_pct/100)** (when the stop is software-side) → CANCEL
     the resting order first, then close NOW per exit runbook §2 (limit at mid, reprice to
     bid after 3 min, no discretion). Journal the stop-out.
   - **mark ≥ entry × (1 + hard_take_profit_pct/100)** (raised to +50% on 2026-07-28,
     briefly +30% earlier that day, originally +100%) → CANCEL the resting stop first
     (verify cancelled), then sell-to-close at mid immediately — NO discretion, winners
     get capped as mechanically as losers get stopped. If unfilled in 3 min, reprice
     toward the bid. Journal the win ("hard TP: sold at $X, +Y%"). **Note:** at +50% both
     `take_profit_pct` (20%, arms the ratchet) and `scale_out_pct` (40%) sit live inside
     this window and are checked before the position could ever reach the hard cap.
   - **mark ≥ entry × (1 + scale_out_pct/100), quantity ≥ 2, not yet scaled out today**
     (check the journal for a "SCALED OUT" entry on this position) → partial profit lock
     (added 2026-07-23, re-activated 2026-07-28): CANCEL the resting stop (verify
     cancelled), sell floor(qty/3)
     contracts (min 1) limit at mid — reprice toward the bid after 3 min if unfilled —
     then re-place the resting stop for the REMAINING quantity at max(previous stop,
     entry × (1 + scale_out_floor_pct/100)) rounded to tick — the −15% floor keyed to
     ORIGINAL entry (or the ratcheted price if the ratchet also triggers this cycle;
     stops only move up). Fresh ref_ids throughout; verify the new stop is `confirmed`.
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
   - **mark ≥ entry × (1 + take_profit_pct/100)** (lowered to +20% on 2026-07-28, was
     50% — "start considering sale") → the ratchet ARMS (no forced sale). While armed:
     required stop = max(entry × (1 + take_profit_floor_pct/100), high-water mark × (1 −
     stop_ratchet_trail_pct/100)), rounded to tick — floor raised from breakeven to +10%
     on 2026-07-28 — track the high-water mark from the journal's mark history plus this
     check's quote. If the required stop exceeds the current resting stop, CANCEL the
     resting stop and place the new higher stop_market (fresh ref_id, verify `state:
     confirmed`, record the new order id). Stops only ever move UP. Journal each ratchet
     ("ratchet: stop $X → $Y, HWM $Z"). With a 20-50% window before the hard-TP cap above,
     arming typically snaps the stop to entry × 1.10 first (a HWM only modestly above
     entry, trailed 30%, computes below the +10% floor) — but as the position runs further
     toward +50%, the HWM-trail component can overtake the floor and raise the stop above
     +10%. Both are expected, not a bug.
   - **in profit, momentum broken** (5-min bars: lower highs, VWAP lost, volume faded) →
     discretionary sell-to-close per STRATEGY.md §6 — CANCEL the resting order first.
     Journal the reasoning. (Applies armed or not — the ratchet is a floor, not a reason
     to hold through a confirmed breakdown.)
   - otherwise hold; log a one-line mark update in the journal (batch-commit these —
     push at most every ~30 min to avoid commit spam, and always push after a trade).
4. **Re-entry check** (only if all of: now < 1:30 PM ET; total open positions <
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
- **Re-arm** (`send_later`, 3 min) if any strategy position is open and it's before
  3:25 PM ET.
- **Stop the loop** when: flat with no re-entry possible (past 1:30 PM ET or daily entry
  limit reached), or it's 3:25 PM ET or later (the 3:30 exit Routine owns the close from
  here — never leave both racing). On stopping, journal a final marks summary, commit, push.
