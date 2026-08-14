# Runbook: Entry (from 9:35 AM ET; re-checks until 1:30 PM on a no-trade)

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` (Pre-market section) first.
All times US/Eastern. Account = `account_number`.
**Why each rule exists: `docs/RATIONALE.md`.** Read thresholds from `config.yaml` by
name, never from a number written in prose.

## Cadence (revised 2026-08-14)
**Re-check every 5 minutes**, not every minute.

§1.3 measures legs over `late_entry_min_bars` consecutive **5-minute** bars, so a
sub-5-minute cadence re-reads the same bar and cannot produce a new verdict. The cost of
the slower loop is bounded: at worst one bar's worth of entry price, and on a leg that
qualifies and then immediately dies, the slower sampler is the one that stays out.

Not a proof, and it should not be quoted as one — a leg can qualify at one sample and be
dead at the next (BIRK, 8/13). What the record supports is that the loop is not where
opportunity is being lost: 94 re-check cycles across 8/11–8/14 produced 3 entries, all on
8/12, and the last 79 produced none. Wake delivery is also running ~10 min late in
practice, so the 1-minute figure was already fiction. See RATIONALE.

## Loop resilience
If a tool call fails on a transient/infrastructure error: retry once or twice in the same
firing. **Whether or not it succeeds, still reach the re-arm step** — journal "data fetch
failed this cycle, retrying next" and `send_later` regardless. A firing must never end
without either filling a position or arming the next one.

---

## 0. Guards — every one must pass
1. **Trading day.** Market closed → journal, push, stop.
2. **Time.** Before 9:35 → `send_later` to 9:35, stop. **After 1:30 PM → skip the day**
   (momentum entries decay); journal why, do not re-arm.
3. `get_option_positions` (nonzero=true) — total open (calls + puts) < `max_open_positions`.
4. `get_option_orders` (queued/confirmed, today) — no duplicate entry already working.
   Also check today's journal against `max_new_positions_per_day`.
5. `get_portfolio` — options buying power ≥ `min_buying_power_to_trade`, else journal
   "insufficient settled cash", notify once (not daily), stop.

## 1. Confirm momentum
1. `run_scan` on `scan_id`, and `scan_id_puts` if `enable_puts`.
2. Merge scan results with the pre-market candidate list; drop anything that hit its
   journaled "disqualify if".
3. **Tape check** — best-ranked candidate first, direction-aware. Puts invert every leg.

   | | initial 9:35 pass | later re-checks (≥ 9:45) |
   |---|---|---|
   | bars | 1-min, 9:30→now (five bars) | 5-min from 9:30 |
   | require | price > open · price ≥ prior close × (1 + `min_day_change_pct`/100) · price > VWAP · no full gap-fade | same, across all available bars |
   | plus | — | **the leg confirmation bar below** |

   **Leg confirmation bar (later re-checks only) — revised 2026-08-14.** Price beyond the
   open is necessary but NOT sufficient. Two things must hold, and **both are vetoes**:

   | test | requirement |
   |---|---|
   | **volume** | leg volume ÷ the name's own **pre-leg trailing baseline** ≥ `late_entry_min_volume_ratio`, measured over `late_entry_min_bars` consecutive 5-min closes in the trade direction |
   | **structure** (`late_entry_require_structure`) | the leg has made **and held** a higher low (lower high for puts) or a new local extreme — and has **not** broken the low the sequence was built on |

   - **Compute the baseline, do not eyeball it.** Use the quiet period immediately
     *preceding* the leg. Never benchmark against the opening range: it is always inflated
     and makes every later leg look weak by comparison (BIRK 8/13 read 0.58× against the
     open and 3.35× against its own baseline — same leg, opposite verdict).
   - **Breaking the structure low is an immediate disqualification**, no waiting for the
     next cycle. This is what killed RDDT at 10:26 on 8/14 and BIRK at 10:42 on 8/13.
   - Declining volume in a *consolidation* is healthy (a flag); declining volume in an
     *advance* is a failing thrust. Same direction, opposite meaning.
   - **Leg age is NOT a gate.** `late_entry_advisory_leg_minutes` (15) is recorded for
     analysis only. It never blocks and never promotes. A leg meeting volume + structure
     at 11 minutes qualifies; one failing them at 40 minutes does not. The old rule made
     the clock a co-equal veto, and review found it was the sole binding constraint exactly
     once in its life — decided by 60 seconds. See RATIONALE before reinstating it.
   - **Log every leg you evaluate** to `data/leg_log.csv` per §1.3b — declined *and*
     accepted. This is the only way the thresholds above ever become testable.

   **§1.3b — leg log (mandatory, every evaluated leg, every cycle).**
   Append one row to `data/leg_log.csv` for each candidate whose tape you measured this
   cycle, whether or not it qualified. Columns are in the file header. Leave a field blank
   rather than guessing it. Fill `outcome_30m` / `outcome_eod` on a later cycle or in the
   exit/EOD phase, retro-editing the row you wrote earlier. Without both the declines and
   the acceptances the sample stays survivorship-biased and no threshold here can be
   validated — that is the entire point of the file.

4. **Opening gap-fade guard** — skip entirely if `opening_fade_guard_enabled` is false.
   Blocking-only: can veto, never promote. Runs AFTER the §1.3 tape check.
   First compute the gap (9:30 5-min bar open vs prior close). If
   |gap| < `opening_fade_guard_min_gap_pct`, **neither gate applies** — no gap supply to
   distribute.
   - **Gate A — opening-bar acceptance.** From the FIRST 5-min RTH bar (09:30–09:35):
     `close_position = (close − low) / (high − low)`. Calls require
     ≥ `opening_bar_min_close_position`; puts ≤ 1 − it. Failure = the gap is being sold
     into: **skip this candidate**, not dead for the day. It becomes eligible again on a
     volume-confirmed 5-min close above that bar's high (below its low for puts). Not
     computable on the initial 9:35 pass — apply Gate B only there.
   - **Gate B — chase guard.** While now < `opening_window_end_et`, reject if price is
     within `opening_window_chase_guard_pct`% of the session high (session low for puts).
     Re-check next cycle; a name blocked now frequently qualifies after a pullback.
     Inactive after that time.
   - **Journal every veto with its measured numbers**, not just the verdict — both gates
     are under review and their live hit rate must stay auditable.

5. `get_earnings_results` on finalists — **reject if earnings fall before the option's
   expiry.** We trade momentum, not event lotteries.
6. **Rank and select.** Catalyst strength > relative volume > cleanest tape, calls and
   puts on one list. Take up to (`max_open_positions` − currently open) qualifiers, best
   first, each independently passing every gate in §2–§3. A symbol closed earlier today
   for a PROFIT ranks first (leader re-entry — resumption only, never the dip). Re-buying
   a symbol closed earlier today is allowed; a symbol may not hold a call and a put at
   once. No qualifier → journal, re-arm.

## 2. Select the contract
1. `get_option_chains` → keep expiries with DTE in [`dte_min`, `dte_max`], sort by
   |DTE − `dte_target`|, take the closest. **Ties break toward the LONGER expiry.**
   If it fails the §2.3 gates, advance to the next-closest expiry in the window before
   abandoning the underlying — weekly chains thin out ~3 weeks out and recover at the
   monthly. Journal which expiry was chosen and its distance from target.
   - **Structural-cap step-out only:** if the chosen expiry has no ATM or OTM strike in
     the trade's direction at all (calls: no strike ≥ spot), step to the next-closest
     expiry. **Never** step out because a strike exists but fails a gate — that follows
     the normal next-strike-then-next-candidate cascade.
2. `get_option_instruments` → ATM, or the first strike beyond spot in the trade's
   direction. **Re-derive this each cycle** — spot moves, and the ATM anchor moves with it.
3. `get_option_quotes` → all three gates must pass:

   | gate | threshold |
   |---|---|
   | open interest | ≥ `min_open_interest` |
   | spread | ≤ `max_spread_pct_of_mid`% of mid |
   | depth | `bid_size` AND `ask_size` ≥ `min_quote_size_for_entry` |

   Any one failing → next strike further OTM **once** → otherwise next candidate.
   **OI is static intraday**: a strike that fails on OI stays failed all day; do not
   re-pull it. Spread and size DO move both ways — re-verify them fresh every cycle.
   - **Sizing:** quantity = floor(min(`max_premium_per_trade`, live buying power) /
     (mid × 100)), minimum 1. `max_premium_per_trade` is the dollar figure computed once
     in today's premarket section — read it, don't recompute. Pull buying power fresh at
     selection time. If even 1 contract is unaffordable that is a no-trade for this
     underlying — journal and notify. **Notify the user whenever buying power, not the
     premium cap, is what binds the size**, and journal both figures side by side.
   - **THIN flag:** if the selected contract's OI < `thin_liquidity_oi_threshold`, journal
     "LIQUIDITY: THIN (OI X < Y)" — this follows the position for life and switches
     monitor.md/exit.md to the tightened cascade.

## 3. Review → authorize → place
1. `review_option_order` (limit buy-to-open at mid, GFD, regular hours, with
   chain_symbol + underlying_type). Surface every `order_checks` alert verbatim in the
   journal and to the user.
2. `entry_auto_execute` **false** → present via AskUserQuestion and wait; no approval =
   no trade. **true** → standing authorization, proceed.
3. **Re-verify the spread immediately before placing.** Pull one more fresh
   `get_option_quotes` and recompute. If it is back above `max_spread_pct_of_mid`,
   **abort — do not place.** Journal the aborted attempt with both spread reads and the
   timing. Do not chase it by repricing wider; that defeats the gate.
4. `place_option_order` with a fresh UUID ref_id (reuse only on transport retries).
   Unfilled after 1 min → cancel, re-place once at mid + 40% of half-spread. Unfilled
   after 1 more min → cancel, no-trade.

## 4. Record and hand off
Journal: contract, fill price (from the filled order), thesis, planned exits, order ids.
Commit ("journal: YYYY-MM-DD entry") and push. Then:

**Position opened** — two follow-ups, in order:
1. **Place the resting protective order** (only one sell can rest per contract — no OCO
   for options). Per `resting_order_type`:
   - `stop_loss`, **fill before 9:45 ET** → Robinhood rejects stop_market until 9:45, so
     place a **stop_limit**: stop = entry × (1 + `stop_loss_pct`/100) tick-rounded,
     limit = stop × 0.85. Record it as stop_limit, flagged **"upgrade at 9:45"**.
   - `stop_loss`, **fill at/after 9:45** → **stop_market** directly, nothing to upgrade.
   - `take_profit` → limit sell at entry × (1 + `take_profit_pct`/100), GFD; the monitor
     loop handles the stop in software.
   Quantity = full filled position. Fresh ref_id; covered by the same standing
   authorization as the entry. **Record the order id and type — every later close must
   CANCEL this order first.**
2. **Start the monitor loop:** `send_later` 2 min → `runbooks/monitor.md`.

**No trade** — `send_later` 5 min to re-run this runbook from §0 (guards fresh each
time; journal only material changes, not repetitive "still fading" lines). Re-checks stop
at 1:30 PM ET or on a fill. A late qualifier passes the same gates — no loosening because
the morning was quiet.

---

## TEMPORARY: single-gate-exception shadow track (2026-08-10 → 2026-08-14)
**Review due after the 2026-08-14 close, then remove or promote.** PAPER ONLY —
`gate_exception_shadow_only: true` is a hard switch; no real order may use the exception.

1. During any §2 pass, when a tape-qualified candidate's contract fails the three-gate
   check, test the exception: exactly ONE gate failed, AND it is **not** quote-size (which
   must always pass), AND the miss is bounded (OI ≥ `gate_exception_min_oi`, or spread ≤
   `gate_exception_max_spread_pct`%). If it qualifies and no shadow is open today, journal
   "GATE-EXCEPTION SHADOW ENTRY (paper only)" with contract, failing gate + value,
   hypothetical entry at mid, quantity = floor(`max_premium_per_trade` ×
   `gate_exception_size_factor` / (mid × 100)), and the THIN flag. One per day; the real
   search continues unaffected.
2. Each later firing, quote the shadow and apply the THIN exit cascade on paper (stop
   −25%, THIN arm/trail, floors subject to the FLOOR CLAMP, hard TP). Journal
   "GATE-EXCEPTION SHADOW: mark $X (±Y%) — [action]". On a paper exit, journal the fill
   and P&L and stop tracking for the day.
3. If still open when the loop ends, exit.md closes it at the then-current mid.
4. After the 8/14 close: compile results vs. the week-of-8/4 backtest and review before
   flipping `gate_exception_shadow_only`. **Known limitation: the exception can never
   apply to quote-size — precisely the gate that blocked NBIS (8/12) and several 8/14
   candidates — so as written it would not have helped the cases that hurt most.**
