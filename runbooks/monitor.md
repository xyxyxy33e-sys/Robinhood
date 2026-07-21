# Runbook: Monitor loop (every 5 minutes while a position is open)

Started by the entry runbook after a fill; self-perpetuating via `send_later`
(delay_minutes=5). Read `config.yaml` and today's journal first. All times US/Eastern.

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
   - **mark ≥ entry × (1 + hard_take_profit_pct/100)** (position doubled) → CANCEL the
     resting stop first (verify cancelled), then sell-to-close at mid immediately — NO
     discretion, winners get capped as mechanically as losers get stopped. If unfilled in
     3 min, reprice toward the bid. Journal the win ("hard TP: doubled, sold at $X").
   - **mark ≥ entry × (1 + take_profit_pct/100)** → the ratchet ARMS (no forced sale).
     While armed: required stop = max(breakeven entry, high-water mark × (1 −
     stop_ratchet_trail_pct/100)), rounded to tick — track the high-water mark from the
     journal's mark history plus this check's quote. If the required stop exceeds the
     current resting stop, CANCEL the resting stop and place the new higher stop_market
     (fresh ref_id, verify `state: confirmed`, record the new order id). Stops only ever
     move UP. Journal each ratchet ("ratchet: stop $X → $Y, HWM $Z").
   - **in profit, momentum broken** (5-min bars: lower highs, VWAP lost, volume faded) →
     discretionary sell-to-close per STRATEGY.md §6 — CANCEL the resting order first.
     Journal the reasoning. (Applies armed or not — the ratchet is a floor, not a reason
     to hold through a confirmed breakdown.)
   - otherwise hold; log a one-line mark update in the journal (batch-commit these —
     push at most every ~30 min to avoid commit spam, and always push after a trade).
4. **Re-entry check** (only if all of: now < 1:30 PM ET; open calls < `max_open_calls` OR
   open puts < `max_open_puts`; today's entry count < `max_new_positions_per_day`; options
   buying power ≥ `min_buying_power_to_trade`): run the entry runbook §1–§4 for a NEW
   candidate in whichever bucket has room. Re-buying a symbol closed earlier today
   (including after a stop-out) is allowed. Cash-account note: proceeds from any sale
   today settle T+1 and cannot fund a re-entry; only remaining settled cash can.

## Re-arm or stop
- **Re-arm** (`send_later`, 5 min) if any strategy position is open and it's before
  3:25 PM ET.
- **Stop the loop** when: flat with no re-entry possible (past 1:30 PM ET or daily entry
  limit reached), or it's 3:25 PM ET or later (the 3:30 exit Routine owns the close from
  here — never leave both racing). On stopping, journal a final marks summary, commit, push.
- Never run two monitor loops at once: if the journal shows a monitor check-in within the
  last 3 minutes (another live loop), log and end without re-arming.
