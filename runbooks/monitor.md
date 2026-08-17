# Runbook: Monitor loop (while a position is open)

Started by entry.md after a fill; self-perpetuating via `send_later`.
Read `config.yaml` and today's journal first. All times US/Eastern.
**Why each rule exists: `docs/RATIONALE.md`.** All thresholds below are named — read
values from `config.yaml`, never from a number written in prose anywhere.

## Cadence (revised 2026-08-14)
- **Re-arm every 2 minutes** while a position is open.
- **In the same firing, also arm a backup wake ~10 minutes out.** Scheduled-wake
  delivery has degraded badly (8/14: median 9.5 min late, max 101 min — see
  RATIONALE), so a single dropped or badly-delayed wake can strand an open position.
  The backup is cheap insurance; if the primary arrives first, the backup fires into
  an already-updated state and is a no-op.
- **Scope the risk correctly:** the hard stop rests **broker-side** and does not depend
  on this loop. A late cycle delays *profit protection* (ratchet, floors, hard-TP,
  scale-out) — it does not expose the position to unbounded loss.

## Loop resilience
If any tool call fails on a transient/infrastructure error (classifier unavailable,
timeout, rate limit — not a logic error): retry once or twice within the same firing.
**Whether or not the retry succeeds, still reach the re-arm step.** Journal "data fetch
failed this cycle, retrying next" in place of the normal update. A firing must never end
without either closing a position or arming the next one.

---

## 0. Dry run
If `dry_run` is true the position is a **paper position recorded in today's journal**, not
a broker position. Everything below runs unchanged and for real — live `get_option_quotes`,
the full cascade, the depth gate, the stall classification — but **no order tool is ever
called**. "Cancel and replace the stop" becomes "journal the new paper stop level";
"sell at mid" becomes "journal the paper exit at the live mid, with P&L". Skip §1's broker
reconciliation and §2's order-type upgrades (nothing rests), and enforce the paper stop in
software: if the live mark trades through it, that is a paper stop-out — journal it and
stop the loop. Everything else, including §5 re-entry, behaves as normal.

## 1. Reconcile
1. `git pull` (config may have changed), read config + today's journal.
2. `get_option_positions` (nonzero=true); match against positions recorded in today's
   journal. Check the resting protective order by its journaled id:
   - **filled** → position closed. Journal it (win/stop-out), treat as flat.
   - **position gone but order not filled** → the user closed manually. Cancel the
     resting order, journal their fill from `get_option_orders`, treat as flat.

## 2. One-time stop upgrades (before any cascade check)
- **9:45 upgrade:** if the journal flagged this position's resting order "upgrade at
  9:45" (a pre-9:45 stop_limit) and it is now ≥ 9:45 — cancel it (confirm `cancelled`),
  place a **stop_market at the same stop_price**, fresh ref_id, verify `confirmed`.
  Update the journal, drop the flag.
- **Near-close upgrade:** if the resting order is a ratchet-placed stop_limit and it is
  now ≥ `ratchet_stop_limit_cutoff_et` — same swap to stop_market at the same stop_price.
- Skip either if the resting order is already a stop_market.

## 3. Depth gate — applies to EVERY stop cancel+replace below
Immediately before cancelling a resting stop, re-pull `get_option_quotes` **fresh**
(do not reuse an earlier read this cycle — it can go stale before cancel+place executes)
and require `bid_size` AND `ask_size` ≥ `min_quote_size_for_stop_update`.

If either side is thinner: **do not cancel/replace this cycle.** Leave the existing stop
exactly where it is — it still fully protects the position, it just has not been raised.
Journal "ratchet would raise stop to $Y but quote too thin (bid X/ask Y) — holding at $Z,
retrying next cycle." This only ever *delays* raising a stop; it never removes protection.

## 4. The cascade — check in this order, per open position
Pull `get_option_quotes`. Handle the software side of whichever protection is NOT resting
(per `resting_order_type`).

**THIN positions** (journaled "LIQUIDITY: THIN" at entry): substitute
`thin_liquidity_take_profit_pct` for the arm trigger and
`thin_liquidity_stop_ratchet_trail_pct` for the trail. Liquid positions unaffected.

**FLOOR CLAMP:** the effective floor is **min(`take_profit_floor_pct`, the arm level that
applied)**. Without it a THIN position arming below the floor would need a stop above the
live mark, forcing an instant sell.

1. **Hard TP** — mark ≥ entry × (1 + `hard_take_profit_pct`/100) → cancel the resting
   stop (verify), sell-to-close at mid **now**, no discretion. Reprice toward the bid if
   unfilled in 1 min. Journal "hard TP: sold at $X, +Y%".

2. **Scale-out** — mark ≥ entry × (1 + `scale_out_pct`/100), quantity ≥ 2, not yet scaled
   today → cancel the stop, sell floor(qty/3) (min 1) limit at mid (reprice toward bid
   after 1 min), then re-place the stop for the REMAINING quantity at
   max(previous stop, entry × (1 + `scale_out_floor_pct`/100)), tick-rounded, depth-gated.
   Journal "SCALED OUT: sold N of M @ $X, stop raised to $Y". Once per position per day;
   1-contract positions skip.
   - **Tranche re-buy** (lighter bar, before 3:00 PM, once per position, settled cash
     only): if a 5-min bar closes with the underlying back on the trade-direction side of
     VWAP, re-buy up to the scaled-out quantity of the SAME contract at mid. Deliberately
     exempt from the §1.3 volume and structure vetoes — this re-buys a position whose
     thesis already proved out, at a level already banked. Then cancel and re-place the
     stop for the full new quantity at the SAME level. Position may not exceed original
     size.

3. **Ratchet arm** — mark ≥ entry × (1 + `take_profit_pct`/100) → the ratchet ARMS
   (no forced sale). While armed:
   ```
   required stop = max( entry × (1 + effective_floor/100),
                        high-water mark × (1 − trail/100) )
   ```
   tick-rounded, where `trail` is `stop_ratchet_trail_pct` (or the THIN variant). Track
   the HWM from the journal's mark history plus this cycle's quote. If the required stop
   exceeds the current resting stop → cancel and place the higher stop (depth-gated,
   fresh ref_id, verify `confirmed`). **Stops only ever move UP.**
   - **Order type:** if `ratchet_stop_type` is `stop_limit` AND now < `ratchet_stop_limit_cutoff_et`,
     place stop_limit (limit = stop × (1 − `ratchet_stop_limit_buffer_pct`/100), tick-rounded);
     otherwise stop_market. Once placed as stop_limit, every later raise on this position
     stays stop_limit until filled or upgraded by §2.
   - Journal: "ratchet: stop $X → $Y (stop_limit, limit $L), HWM $Z".
   - **Stall-trail** (every cycle while armed): classify this cycle's 5-min bar as
     **EXTENDING** (new local high, still on the trade-direction side of VWAP, volume
     steady/rising) or **STALLING** (anything less). On STALLING, also compute
     HWM × (1 − `stop_ratchet_stall_trail_pct`/100) and take the **higher** of that and the
     normal required stop. If the result is already at/above the current mark, a stop
     cannot be placed above the live price — **cancel the resting stop and sell at mid
     now**. Journal the classification each cycle.

4. **Pre-arm floors** — no-ops once the ratchet has armed. Each is a first-touch trigger
   raising a floor; when several are eligible, **take the highest**. Stops only move UP.
   Depth-gated like any other replacement.

   | floor | active when | trigger | resulting floor |
   |---|---|---|---|
   | early | always | `early_floor_trigger_pct` (+8%) | `early_floor_pct` (−3%) |
   | midday | `midday_floor_window_*` (11:30–13:30) | `midday_floor_trigger_pct` (+3%) | `midday_floor_pct` (breakeven) |
   | late-day | `late_day_floor_window_*` (13:30–15:00) | `late_day_floor_trigger_pct` (+5%) | `late_day_floor_pct` (+5%, real profit) |

   Journal "early/midday/late-day floor: stop $X → $Y".

5. **Momentum broken, in profit only** — 5-min bars showing lower highs AND VWAP lost AND
   volume faded, all three → discretionary sell-to-close at mid; cancel the resting order
   first. Journal the reasoning. Applies armed or not: the ratchet is a floor, never a
   reason to hold through a confirmed breakdown. **Does not apply at a loss** — the −25%
   stop is the only downside mechanism there.

6. **Otherwise hold** — log a one-line mark update. Batch these; push at most every
   ~30 min, and always immediately after a trade.

## 5. Re-entry check
Only if ALL of: now < 1:30 PM ET · open positions < `max_open_positions` · today's entries
< `max_new_positions_per_day` · **available buying power** ≥ `min_buying_power_to_trade`
(entry.md §0.5 definition — live buying power normally, the notional figure while
`dry_run`; this account is shared with another strategy).

Run entry.md §1–§4 for a new candidate, call or put. **Leader re-entries rank first**: a
symbol closed earlier today for a PROFIT is top priority — but only on a resumption
(pullback stabilised at a higher low, then a fresh volume-confirmed push), never on the
dip itself. Re-buying a symbol closed earlier today, including after a stop-out, is
allowed. **Cash account:** today's sale proceeds settle T+1 and cannot fund a re-entry;
only remaining settled cash can.

## 6. Re-arm or stop
- **Re-arm** (2 min, plus the ~10 min backup) if any position is open and it is before
  3:25 PM ET.
- **Stop** when flat with no re-entry possible (past 1:30 PM or the daily limit), or at
  3:25 PM ET — the 3:30 exit Routine owns the close from there; never leave both racing.
  On stopping: journal a final marks summary, commit, push.
