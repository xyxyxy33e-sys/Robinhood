# Runbook: Exit (~3:30 PM ET, Mon–Fri) — the account is FLAT by the close

Read `config.yaml` and today's journal first. All times US/Eastern.
Account = `account_number`. This runbook may not end its turn while a position is open —
work the close until flat or 4:00 ET.

## 0a. Dry run
If `dry_run` is true, there is nothing at the broker to close. Check today's journal for an
open **PAPER ENTRY**: if one exists, quote it live, journal the paper close at the current
mid with P&L and the reason (cascade level hit, or forced flat), and fill in the
`outcome_eod` column for its `data/leg_log.csv` row. Then run §4's reporting as normal and
stop — §1–§3 are broker operations and do not apply. Still verify with
`get_option_positions` that the account really is flat; if it is not, `dry_run` was enabled
while a real position was open, so **ignore this section and close it for real**.

## 0b. Guards
1. Market closed today / half-day: on half-days (1:00 PM close) this must run by 12:30 —
   the premarket run flags half-days in the journal; honor `send_later` reschedules from it.
2. If fired before 3:25 ET, `send_later` to 3:30 ET and stop. If after 3:55 ET, go straight
   to §3 crossing logic. The 3-minute monitor loop stands down at 3:25 ET — this runbook
   owns the position from here; ignore/cancel any monitor re-arm that slips through.
3. `get_option_positions` (nonzero=true) + `get_option_orders` (today, open states):
   no open position and no working orders → journal "flat, nothing to do", push, stop.

## 1. Cancel stale orders
Any working strategy order still open → `cancel_option_order` (part of the user's standing
daily-flat instruction). This includes BOTH unfilled entry orders AND the resting
take-profit sell — the take-profit MUST be cancelled before placing any close order in §2,
or the close will be rejected / double-sell.

## 2. Evaluate and close (per open contract from this strategy)
1. `get_option_quotes` → mark vs entry premium (entry price from today's journal / the
   filled order).
2. Whatever the P&L, the position closes today; P&L and momentum only affect timing:
   - mark ≤ stop loss (`stop_loss_pct`) → close NOW, limit at mid; if unfilled in 1 min
     reprice to bid. No discretion on losers.
   - mark ≥ entry × (1 + hard_take_profit_pct/100) → sell NOW at mid, no discretion
     (the +30% hard-TP cap applies here exactly as in the monitor loop).
   - winner or flat → discretionary (STRATEGY.md §6): pull 5-minute bars on the underlying;
     if it's still trending (higher highs, above VWAP, volume holding) you may hold until
     `forced_close_start_et` to capture the last leg — otherwise sell-to-close now at mid.
     **Thin-liquidity exception (added 2026-08-06):** if this position was journaled
     "LIQUIDITY: THIN" at entry, skip the last-leg hold entirely — sell-to-close now at
     mid regardless of how the underlying is trending. A name with proven exit-slippage
     risk shouldn't be given extra time in the position chasing a marginal further gain;
     get flat as soon as this phase runs rather than waiting for `forced_close_start_et`.
     Either way, journal the reasoning; the position is flat by 3:53 regardless.
3. `review_option_order` first; then, per `exit_auto_execute` (true = place without
   asking; false = AskUserQuestion, warning that no answer means an overnight hold).
4. `place_option_order` (sell, position_effect=close, GFD, fresh ref_id).

## 3. Work the order until flat
Poll `get_option_orders` every ~1 minute (tightened from 3 on 2026-08-06 per user; use
`send_later`/Monitor, never sleep-loops):
- 3:48 ET still unfilled → cancel, re-place at mid − 40% of half-spread.
- `forced_close_cross_et` (3:53) still unfilled → cancel, re-place limit AT THE BID.
- Repeat at-bid repricing every 1 min until filled or 3:59.
- If anything is still open after 4:00 ET: notify the user IMMEDIATELY (push notification
  if available) with contract, quantity, and mark — never silently hold.

## 4. Record
Journal: exit fill(s), realized P&L ($ and % on premium), what worked/failed, one lesson.
Note that sale proceeds settle T+1 (tomorrow's entry buying power). Commit
("journal: YYYY-MM-DD exit, P&L $X") and push.
