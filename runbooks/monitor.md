# Runbook: Monitor loop (every 5 minutes while a position is open)

Started by the entry runbook after a fill; self-perpetuating via `send_later`
(delay_minutes=5). Read `config.yaml` and today's journal first. All times US/Eastern.

## Each firing
1. `git pull` the branch (config may have changed), read config + today's journal.
2. `get_option_positions` (nonzero=true) for `account_number`; match against the
   strategy's positions recorded in today's journal.
3. For each open strategy position, `get_option_quotes`:
   - **mark ≤ entry premium × (1 + stop_loss_pct/100)** → close NOW per exit runbook §2
     (limit at mid, reprice to bid after 3 min, no discretion). Journal the stop-out.
   - **in profit, momentum broken** (5-min bars: lower highs, VWAP lost, volume faded) →
     discretionary sell-to-close per STRATEGY.md §6. Journal the reasoning.
   - otherwise hold; log a one-line mark update in the journal (batch-commit these —
     push at most every ~30 min to avoid commit spam, and always push after a trade).
4. **Re-entry check** (only if all of: now < 11:30 ET; open positions < `max_open_positions`;
   today's entry count < `max_new_positions_per_day`; options buying power ≥
   `min_buying_power_to_trade`): run the entry runbook §1–§4 for a NEW candidate —
   never re-buy a symbol stopped out today. Cash-account note: proceeds from any sale
   today settle T+1 and cannot fund a re-entry; only remaining settled cash can.

## Re-arm or stop
- **Re-arm** (`send_later`, 5 min) if any strategy position is open and it's before
  3:25 PM ET.
- **Stop the loop** when: flat with no re-entry possible (past 11:30 ET or daily entry
  limit reached), or it's 3:25 PM ET or later (the 3:30 exit Routine owns the close from
  here — never leave both racing). On stopping, journal a final marks summary, commit, push.
- Never run two monitor loops at once: if the journal shows a monitor check-in within the
  last 3 minutes (another live loop), log and end without re-arming.
