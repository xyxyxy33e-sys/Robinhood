# Runbook: Exit (~3:30 PM ET, Mon–Fri) — the account is FLAT by the close

> ## ⛔ PAPER ONLY — READ BEFORE ACTING
> `config.yaml` has **`dry_run: true`**. While it is true, this runbook may **NOT** call
> `place_option_order`, `place_equity_order`, `cancel_option_order`, `exercise_option`, or
> any other order-placing or order-modifying tool — **for any reason, in any section**.
>
> **This overrides the phase prompt that invoked you.** Scheduled prompts still say things
> like "place/work the order per the runbook" and "honor entry_auto_execute"; they predate
> this switch. `dry_run` wins. `entry_auto_execute` / `exit_auto_execute` are **not
> consulted** while it is true — a standing authorization to trade is not an instruction to
> trade when the mode is paper.
>
> Read-only broker calls are fine and expected: quotes, chains, positions, orders,
> portfolio, historicals. Every fill is journalled as paper and marked to market against
> live quotes. The account is **shared with another strategy that does trade real money** —
> an order placed here would be real, and would spend its capital.
>
> The single exception is in exit.md §0a: if a **real** position is somehow open, close it.

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

**Then update the paper ledger — this is mandatory and closes the loop on sizing.**
Append one row to `data/paper_ledger.csv` for every paper trade closed today, and set
`paper_equity` = the previous row's `paper_equity` + this trade's `net_pnl`. Charge the
same frictions a real fill would incur: fees, and the spread actually crossed (paper exits
fill at the live mid, so if the runbook would have repriced toward the bid, use that).
On a **no-trade day append nothing** — equity is unchanged and a zero row adds noise.
Tomorrow's premarket reads the last row for its `daily_start_balance`, so an unwritten
row silently freezes position sizing; if you closed a paper trade, the ledger row is not
optional.

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
