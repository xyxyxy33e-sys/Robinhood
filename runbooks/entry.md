# Runbook: Entry (from 9:35 AM ET; re-checks until 1:30 PM on a no-trade)

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

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` (Pre-market section) first.
All times US/Eastern. Account = `account_number`.
**Why each rule exists: `docs/RATIONALE.md`.** Read thresholds from `config.yaml` by
name, never from a number written in prose.

## Bar pulls: MANDATORY session-start guard (added 2026-08-26)

**Pull with `start_time = <date>T00:00:00Z` — midnight, not the session open.** The API
returns `bounds=regular`, so it clamps to the 13:30:00Z open regardless; passing midnight
gives a 13.5-hour margin so no plausible mistyped timestamp can land *after* the open.
Verified 2026-08-27: midnight returns a series whose first bar is 13:30:00Z.

This replaces the earlier instruction to pass `13:30:00Z` exactly, which failed five times
in three sessions (8/25 16:00Z, 8/26 14:20Z, 8/26 17:00Z, 8/27 14:00Z, 8/27 15:35Z).
Telling myself to "copy it verbatim" worked once and then failed again — the fix had to
stop depending on care. Whatever value is passed, the pull must cover the
full regular session, never a narrowed window. VWAP, the session high and low, and the
rolling-median baseline are all computed over the whole series; a pull that starts
later silently produces wrong numbers rather than an error.

I got this wrong three times: 8/25 12:55 (`16:00:00Z`), 8/26 11:12 (`14:20:00Z`),
8/26 13:20 (`17:00:00Z`). The first two were written up in the journal and the error
recurred anyway, so **the check is no longer a note — it is code**:

```
python3 tools/eval_entry.py <payload.json> <prev_closes.json> <directions.json>
```

`tools/eval_entry.py` refuses to evaluate (exit 2) unless the first bar of every
symbol begins at `...T13:30:00Z`. Feed it the `get_equity_historicals` payload
verbatim; do not hand-transcribe bars into an ad-hoc script, which was its own
source of error. Do not evaluate legs by any other route.

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
5. **Available buying power** ≥ `min_buying_power_to_trade`, else journal "insufficient
   funds", notify once (not daily), stop.
   - **Under `dry_run` (the standing mode): available = PAPER EQUITY**, i.e. the last
     `paper_equity` in `data/paper_ledger.csv`, minus the cost of any paper position
     already open today. Do **not** read the broker for this. Paper fills consume nothing
     real, and the account is shared with another strategy that holds the actual cash.
   - **In live mode: available = `get_portfolio` → `buying_power.buying_power`.** Never the
     snapshot, never paper equity.
   - Either way, journal both numbers each cycle — "paper equity $X / real BP $Y" — so the
     gap stays visible and a paper size is never mistaken for something the account could
     have funded.

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
   | **volume** | this bar's volume ÷ the trailing baseline below ≥ `late_entry_min_volume_ratio`, with `late_entry_min_bars` consecutive 5-min closes in the trade direction |
   | **structure** (`late_entry_require_structure`) | **all three**: (a) this bar closed in the trade direction *relative to its own open* (close > open for calls); (b) a new local extreme over the last `late_entry_min_bars` bars, **or** a higher low (lower high for puts); (c) the low the sequence was built on is **unbroken** |

   - **Baseline is mechanical — do not choose it by eye, and do not key it to the leg
     start.** `median(volume of the previous late_entry_baseline_bars bars, skipping the
     session's first late_entry_baseline_skip_open_bars)`. The earlier "quiet period
     preceding the leg" wording was ambiguous and broke on BIRK 8/13: a consecutive-closes
     leg start walked the baseline back into the busy post-open window and returned
     **0.48×** where the eyeballed dormant window gave **3.35×** — same leg, same bars, 7×
     apart, and the inflated-open error this rule exists to prevent. The opening bars are
     excluded by construction now.
   - **(a) is load-bearing.** A bar that prints a new high but closes below its own open is
     a rejection, not a breakout. It is the single condition that separated the two rules
     in backtest: BIRK 8/13 at 14:25 had volume 4.3× and a new session high, and closed
     $0.07 below its open — the old clock rule bought it, structure declined it, and it
     lost 2.9% over the next hour.
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

   **§1.3b — leg log (mandatory, every evaluated leg, every cycle; CONTROLLED VOCABULARY).**
   Append one row to `data/leg_log.csv` for each candidate whose tape you measured this
   cycle, whether or not it qualified. Columns are in the file header. Leave a field blank
   rather than guessing it. Without both the declines and the acceptances the sample stays
   survivorship-biased and no threshold here can be validated — that is the entire point
   of the file.

   **Do not hand-fill `outcome_30m` / `outcome_eod`.** Through 2026-08-21 they were
   populated on 4.1% / 4.9% of 267 rows, so for six weeks no threshold in this strategy
   was ever checked against what happened next, and every "finding" in the journals was
   argued from anecdote. They are now generated mechanically:

   ```
   python3 tools/backfill_outcomes.py          # idempotent; fills blanks only
   ```

   It reads `data/bars/YYYY-MM-DD_SYM.csv` and writes direction-adjusted underlying moves
   (positive = the trade direction was right), plus MFE/MAE. **The EOD phase must run it,
   after refreshing `data/bars` for the day's evaluated names** — see `eod_report.md` §5.

   **Use these exact values so the file stays machine-readable** (19 distinct `decision`
   spellings and 6 spellings of `structure_intact` had accumulated by 8/21):
   - `decision`: `declined` · `entered` · `qualified_not_taken` · `qualified_blocked_chain`
     · `qualified_aborted_3.4` · `qualified_expired` · `dropped`
   - `structure_intact`: `yes` · `no` · `partial`
   - `gate_a` / `gate_b`: `pass` · `skip` · `n/a` (append `_<value>` if useful, e.g. `skip_0.417`)

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
   - **Gate B-all — the chase guard does NOT switch off at 10:30** (added 2026-08-22).
     For the whole entry window, reject if price is within `chase_guard_all_session_pct`%
     of the session high (session low for puts). Same semantics: blocking-only, re-check
     next cycle. This runs even when §1.4's gap test does not apply, because it is not a
     gap rule — it is a correction to §1.3 structure (b), which rewards a **new local
     extreme** and therefore selects breakout bars by construction. Before 10:30 Gate B
     masked that; after 10:30 nothing did.
     Requiring distance from the extreme flips modelled P&L from negative to positive at
     every volume threshold tested (see `config.yaml` for the table and its caveats).
     Live witness: COIN on 8/21 filled 0.42% below a session high set on the qualifying
     bar itself and stopped out at −25%, with a recorded MFE of +0.14%.
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
2. **Build the strike band (revised 2026-08-14).** `get_option_instruments` → the ATM
   anchor (first strike at/beyond spot in the trade's direction), then take
   `strike_search_steps_itm` strikes on the near side and `strike_search_steps_otm` on the
   far side. **Re-derive the anchor every cycle** — spot moves, and the anchor moves with it.

   The old rule stepped "one strike further OTM" on a failure. That searched the wrong
   axis: liquidity clusters at **round strikes**, not by distance from spot, and the OTM
   direction is also where premium falls and % spread mechanically worsens. It made OI
   worse in 7 of 9 measured cases ($182.50 → OI 6). Evaluate the whole band instead.

3. `get_option_quotes` on **every strike in the band** (one batched call). All three gates
   must pass, per strike:

   | gate | threshold |
   |---|---|
   | open interest | ≥ `min_open_interest` |
   | spread | ≤ `max_spread_pct_of_mid`% of mid |
   | depth | `bid_size` AND `ask_size` ≥ **required size** (§2.4 — depends on quantity) |

   - **Selection: among strikes passing ALL gates, take the one CLOSEST TO ATM.** The band
     widens the *search*, it does not change the strike *preference* — never take a far
     strike merely because its OI is larger.
   - **No strike in the band passes → next candidate.** Do not widen the band ad hoc.
   - **OI is static intraday**: a strike that fails on OI stays failed all day; do not
     re-pull it (but DO re-pull the others — a strike can fail on spread or depth at 12:27
     and pass at 12:31; NBIS did exactly that).
   - **Log the whole band to `data/chain_log.csv`** per §2.5, pass or fail.

4. **Sizing, then the depth gate — in that order.** The depth requirement depends on the
   order, so quantity must be known first.
   - quantity = floor(min(`max_premium_per_trade`, **available buying power**) / (mid × 100)),
     minimum 1, where "available" is the §0.5 definition — **paper equity** under
     `dry_run` (the standing mode), live broker buying power only if it were ever off.
     `max_premium_per_trade` is the dollar figure computed once in today's premarket
     section — read it, don't recompute. Pull the buying-power figure fresh at selection
     time. If even 1 contract is unaffordable that is a no-trade for this underlying —
     journal and notify. **Notify the user whenever buying power, not the premium cap, is
     what binds the size**, and journal both figures side by side.
   - **Shared account:** a paper size simulates what this strategy *would* do with its own
     book, not a claim the account could fund it today. If real buying power would NOT have
     covered the paper fill, say so explicitly in the journal line — that gap is the point
     of tracking both numbers, and it is what would decide whether this strategy could ever
     run live alongside the other one.
   - **Required displayed size**, on `bid_size` AND `ask_size` both:
     ```
     required = max(min_quote_size_floor, ceil(quantity × quote_size_coverage_multiple))
     ```
     A flat constant was wrong in both directions: it demanded 3.3× coverage on a 3-lot and
     1× on a 10-lot. This scales with what is actually being bought, so it **tightens**
     large orders (a 16-lot needs 32 a side) and relaxes only small ones.
   - If the depth gate fails at the chosen quantity, **try the next-smaller affordable
     quantity once** before moving to the next strike in the band — a smaller order needs
     less displayed depth, and taking a 2-lot beats declining a 3-lot.
   - **Displayed size is ephemeral, not a property of the contract.** NBIS $250C showed
     1/1 at 12:27 and 32/93 at 12:31 with OI unchanged. A depth block is expected to clear
     on its own; it is never a reason to abandon a name for the day.
   - **THIN flag:** if the selected contract's OI < `thin_liquidity_oi_threshold`, journal
     "LIQUIDITY: THIN (OI X < Y)" — this follows the position for life and switches
     monitor.md/exit.md to the tightened cascade.

5. **§2.5 — chain log (mandatory, every cycle a chain is priced).**
   Append one row per strike evaluated to `data/chain_log.csv`, pass or fail. **Also run
   this probe for the top-ranked candidates whose tape did NOT qualify this cycle** — one
   batched `get_option_quotes` on their ATM strike, logged the same way. Tape (§1) runs
   before contract selection, so without this probe a name blocked on tape is never
   re-priced and the belief that "spreads tighten later" stays untested. On 8/14 all four
   candidates were priced once at 9:38 and never again. Cheap call, and it is the only
   way the OI and spread thresholds ever get evidence.

## 3. Review → authorize → place
1. `review_option_order` (limit buy-to-open at mid, GFD, regular hours, with
   chain_symbol + underlying_type). Surface every `order_checks` alert verbatim in the
   journal and to the user.
2. **`dry_run` true → PAPER FILL. Do not call `place_option_order`, now or later this
   cycle.** Everything above still runs for real (real scan, real quotes, real gates,
   real `review_option_order` — it places nothing). Journal
   **"DRY RUN — PAPER ENTRY"** with contract, quantity, the mid you would have paid, every
   `order_checks` alert, and the THIN flag, then go to §4. `entry_auto_execute` is not
   consulted while `dry_run` is true.
3. `entry_auto_execute` **false** → present via AskUserQuestion and wait; no approval =
   no trade. **true** → standing authorization, proceed.
4. **Re-verify the spread immediately before placing.** Pull one more fresh
   `get_option_quotes` and recompute. If it is back above `max_spread_pct_of_mid`,
   **abort — do not place.** Journal the aborted attempt with both spread reads and the
   timing. Do not chase it by repricing wider; that defeats the gate.
5. `place_option_order` with a fresh UUID ref_id (reuse only on transport retries).
   Unfilled after 1 min → cancel, re-place once at mid + 40% of half-spread. Unfilled
   after 1 more min → cancel, no-trade.

## 4. Record and hand off
Journal: contract, fill price (from the filled order; under `dry_run`, the mid at the
paper fill), thesis, planned exits, order ids. Commit ("journal: YYYY-MM-DD entry") and
push. Then:

**Position opened** — two follow-ups, in order:
1. **Place the resting protective order.** **Under `dry_run`: compute the stop level and
   type exactly as below and journal it as "PAPER STOP $X (type)", but place nothing.**
   monitor.md enforces it in software against live quotes.
   Live mode — only one sell can rest per contract (no OCO for options).
   Per `resting_order_type`:
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

## Retired: single-gate liquidity exception (2026-08-10 → 2026-08-14)
The paper window produced exactly one shadow trade — SE $130C 8/11, stopped out at
**−25.9% (−$360)** — and by construction could never apply to quote-size, the gate that
actually blocks. Retired 2026-08-14 along with its config keys. Do not reintroduce a
single-gate bypass without evidence from `data/chain_log.csv`; see RATIONALE.
