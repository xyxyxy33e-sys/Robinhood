# Daily Momentum Calls — Strategy Specification

**Objective:** Buy calls on stocks showing confirmed intraday bullish momentum, and puts on
stocks showing confirmed intraday bearish momentum (`enable_puts`, added 2026-07-21), hold
intraday only, and be flat by the close. News is gathered pre-market every trading day to
build a candidate thesis before any money moves. The name predates the puts addition; it
still trades both directions under it.

**Account:** Robinhood "Agentic" cash account `576391551` (agentic_allowed, options Level 2 —
single-leg only: long calls/puts, covered calls, cash-secured puts).

---

## 1. Daily schedule (US/Eastern)

| Time (ET) | Phase | Runbook |
|-----------|-------|---------|
| ~8:00 AM | Pre-market news + candidate research | `runbooks/premarket.md` |
| ~9:00 AM | Pre-entry sentiment-shift check (added 2026-07-27) — re-reads the same candidates against the 8 AM read to catch reversals/fades before 9:35 | `runbooks/premarket_confirm.md` |
| 9:35 AM | Entry — confirm momentum after the open, buy call or put | `runbooks/entry.md` |
| every 5 min until 1:30 PM (only if no trade yet) | Entry re-check — catch late qualifiers | `runbooks/entry.md` |
| every 5 min while a position is open | Monitor — stop-loss, discretionary profit-taking, re-entries | `runbooks/monitor.md` |
| ~3:30 PM | Exit — discretionary profit-taking / hard stop / forced flat by 3:55 | `runbooks/exit.md` |

The 8:00/9:45/3:30 phases are cron Routines; the 5-minute monitor is a self-re-arming
`send_later` loop started by a fill and stood down at 3:25 ET when the exit run takes over.

Scheduled via Claude Code Routines (cron is UTC — see README for DST note). Every runbook
begins with a market-open check and a time check; if fired at the wrong time it reschedules
itself rather than acting.

## 2. Universe & candidate discovery

Two saved Robinhood scanners, run every pass:

- **Calls — "Daily Momentum Calls"** (`scan_id`, `5399dce3-8430-476c-ba65-89ac920af0bf`):
  % change vs prior close > +2% (1d); RSI(14, 1d) between 55 and 80 (uptrend, not
  blow-off overbought).
- **Puts — "Daily Momentum Puts"** (`scan_id_puts`, `1849aba7-1d06-4269-b58f-b4e42d9bfb02`,
  added 2026-07-21, gated by `enable_puts`): % change vs prior close < −2% (1d);
  RSI(14, 1d) between 20 and 45 (downtrend, not oversold-bounce territory).

Both scanners share: 30-day average volume > 5M shares; 5-day average options volume >
10,000 contracts; last price between $5 and $250 (keeps one ATM contract affordable);
market cap > $2B (no illiquid junk).

Supplemented by pre-market news: fresh catalysts (earnings beats/misses, guidance
raises/cuts, upgrades/downgrades, product/regulatory news) rank a candidate up in its
direction; binary-event risk ranks it down. Each ranked candidate's ATM option OI and
spread are pre-screened during the premarket run (added 2026-07-24): OI is static
intraday, so a chain that's dead at 8 AM is dead all day — those names rank below every
candidate with a live chain.

## 3. Momentum signal (all must hold at entry time)

1. Appears in the relevant scanner **or** was a top pre-market candidate now moved ≥2% in
   its direction.
2. Tape confirmation scaled to session age, direction-aware:
   - **Calls**: first 5 minutes — above the opening print with no immediate reversal
     (1-minute bars); after 9:35 — above open and holding above VWAP on 5-minute bars,
     no full gap-fade.
   - **Puts**: first 5 minutes — below the opening print with no immediate reversal
     (1-minute bars); after 9:35 — below open and holding below VWAP on 5-minute bars,
     no full gap-fill-back-to-open.
   - **Late re-checks (any entry after the initial 9:35 pass):** price beyond the open is
     necessary but NOT sufficient — require a volume-confirmed breakout: several
     consecutive closes in the trade direction on rising/elevated volume, sustained for
     15+ minutes. A quiet, low-volume grind back through the open does not qualify
     (codified 2026-07-21 from the NVS-declined / TSM-declined-then-accepted precedents).
3. **No earnings between now and the option's expiry** (check `get_earnings_results`) —
   we trade momentum, not event lotteries.
4. A concrete catalyst or sector tailwind identified in the pre-market journal entry.

Rank qualifiers by: catalyst strength > relative volume > cleanest tape, calls and puts
candidates ranked together on the same list. Take up to (`max_open_positions` − currently
open positions total) qualifiers in one pass, best first across both directions combined
(no fixed split between calls and puts) — each independently passing every sizing and
liquidity gate. Re-entering a symbol already open (or closed earlier today, including
after a stop-out) is allowed; the only same-symbol restriction is that a symbol can't hold
a call and a put at the same time.

**Leader re-entry (added 2026-07-21):** a symbol closed earlier today for a PROFIT (hard
take-profit, ratcheted stop above breakeven, or discretionary win) stays FIRST in the
re-check rotation until the 1:30 PM entry cutoff — it has already proven its catalyst,
liquidity, and tape, which makes it a better-than-random candidate for a second leg. The
trigger is a **resumption, never a dip**: the pullback must stabilize (higher low), then
resume with the full late-re-check volume bar above (consecutive directional closes on
rising/elevated volume, 15+ min). All standard gates re-apply, and — cash account — the
re-entry can only be funded by remaining settled cash, never by the just-banked proceeds
(T+1). Expect the second entry to be structurally worse than the first (pumped IV,
heavier theta): the volume bar is the compensation, not optional.

## 4. Contract selection

- **Type:** call for a bullish qualifier, put for a bearish qualifier; always buy-to-open
  (long only — no short options). **Expiry:** nearest expiration 2–21 DTE — never 0 or 1
  DTE (raised from 1 on 2026-07-21: a 1-DTE MU contract with theta −9.9 hit the −30%
  floor in 20 minutes on a modest underlying pullback; the contract structure, not the
  thesis, drove the speed of the loss). Monthly-only chains (no expiry in window): nearest
  monthly up to `dte_max_no_weekly` (45) is allowed. Short-dated contracts are cheapest
  but carry violent gamma/theta; the forced same-day close caps expiry risk, not premium
  risk.
- **Strike:** at-the-money, or the first strike beyond spot in the direction of the trade
  (above spot for calls, below spot for puts).
- **Liquidity gates:** open interest ≥ 500; bid-ask spread ≤ 10% of mid. If ATM fails the
  gates, step one strike out (further out-of-the-money); if still failing, skip the
  underlying. **OI updates only once daily (after settlement) — it cannot improve
  intraday**, so a strike that fails the OI gate at first check stays failed for the day
  (only spreads move intraday); re-checks must not re-pull quotes on OI-failed contracts
  unless spot has shifted the ATM to an unchecked strike. The premarket run pre-screens
  each candidate's ATM OI for exactly this reason (both added 2026-07-24, after all five
  tape qualifiers burned the whole entry window failing on OI that was knowable at 8 AM).
- **Order:** limit buy at mid, GFD, regular hours. If unfilled in 5 min, reprice once to
  mid + 40% of half-spread. Never market-buy an option.

## 5. Position sizing & risk limits (config.yaml is the source of truth)

- Premium per trade ≤ `max_premium_per_trade` — a flat cap, not scaled or capped by live
  buying power (removed 2026-07-21 per user instruction; the broker rejects the order if
  settled cash is actually insufficient). Quantity = floor(max_premium_per_trade /
  (premium × 100)), min 1 — multiple contracts of the same call or put allowed. No
  averaging down (don't add to a position that's currently open and red).
- Re-entering the same underlying is allowed — no one-position-per-symbol cap, and no
  restriction on re-buying a symbol that was stopped out earlier today (both removed
  2026-07-21 per user instruction). The only same-symbol restriction: never hold a call
  and a put on the same underlying at the same time.
- At most `max_open_positions` concurrent positions total, any mix of calls and puts
  (changed 2026-07-28 from separate max_open_calls=5/max_open_puts=5 buckets [10 total]
  to one combined 6-total cap), plus `max_new_positions_per_day` entries per day (initial
  entry at 9:35; 10-min re-checks on no-trade and monitor-loop re-entries both end at
  1:30 PM ET).
- Skip entries while options buying power < `min_buying_power_to_trade` — log why.
- Cash account: option sale proceeds settle **T+1**. The exit run's proceeds fund the
  *next* day's entry; never plan on same-day recycling of proceeds.

## 6. Exit rules (enforced by the 5-minute monitor loop and the 3:30 PM run; position never held overnight)

- **Resting protective order (broker-side):** immediately after every entry fill, ONE
  protective sell rests at the broker per `resting_order_type` — Robinhood holds only one
  sell order per contract (no OCO for options). Default `stop_loss`: a stop_market at
  entry × (1 + `stop_loss_pct`/100), so the max-loss exit executes even if monitoring is
  interrupted (failure mode observed 2026-07-16). Alternative `take_profit`: a sell limit
  at entry × (1 + `take_profit_pct`/100). The monitor loop enforces whichever side is not
  resting, in software. Any other close must cancel the resting order first.
- **9:30–9:45 stop blackout:** Robinhood rejects stop_market orders in the first 15
  minutes after the open (`OPTION_STOP_MARKET_INVALID_TIME_MARKET_OPEN`, observed
  2026-07-21). An entry filled before 9:45 is protected in software until then: the entry
  run does NOT end its turn — it runs ~1-minute quote checks and sells-to-close at mid
  immediately if the mark crosses the stop level, then places the resting stop at 9:45
  sharp and hands off to the normal 5-minute monitor loop.
- **Partial scale-out at +40% (added 2026-07-23):** on a position holding 2+ contracts,
  the first touch of entry × (1 + `scale_out_pct`/100) sells floor(quantity/3) contracts
  (min 1) at mid; the rest keeps the ratchet path. Once per position per day; 1-lot
  positions skip (nothing to split). Mechanics mirror every other close: cancel the
  resting stop, place the partial sell, confirm the fill, re-place the stop for the
  remaining quantity. Checked after the hard take-profit, before the ratchet arm.
  Motivation: GOOGL 2026-07-23 peaked +44.1% — under the +50% ratchet arm — then
  round-tripped to −3.9% with nothing locked; a one-third sale at +40% both banks the
  mid-size winner and insures the round-trip. The cost is a slice of uncapped runners
  (SMCI 2026-07-22 would have made ~$104 less), accepted as the insurance premium. An
  earlier trailing arm (+35%) was evaluated against the same data and REJECTED: it
  would have stopped GOOGL out at ~+1% in the midday dip instead of the +21.3% actual
  exit — trailing early punishes exactly the choppy winner it tries to protect.
  **Post-scale-out floor (added 2026-07-23):** once the scale-out fills, the
  remainder's stop rises to at least entry × (1 + `scale_out_floor_pct`/100) (−15%,
  keyed to original entry, tick-rounded, stops only move up) — guaranteeing the whole
  trade nets positive after the scale-out banks (⅓ × 40% > ⅔ × 15%) while sitting
  below ordinary chop; a breakeven floor was evaluated and rejected (would have cut
  GOOGL's remainder in the −3.9% dip). The ratchet's breakeven+ trail supersedes it at
  +50%. **Scaled-out tranche re-buy (user-approved 2026-07-23):** while the remainder
  is open, the sold tranche may be re-bought — same contract, up to the scaled-out
  quantity, once per position per day, before 3:00 PM ET, settled cash only — on a
  LIGHTER signal than leader re-entry: a 5-minute close with the underlying back on
  the trade-direction side of VWAP, with no volume or sustain requirement. The
  position may not exceed its original size, and the resting stop is re-placed for
  the full quantity at the unchanged level after the fill. (Agent's strict-bar
  recommendation was declined; risks accepted: chop re-buys and double spread cost.)
- **Stop ratchet on winners — arms at +20% (lowered from 50% on 2026-07-28, "start
  considering sale"):** touching entry × (1 + `take_profit_pct`/100) does not force a
  sale — it ARMS the ratchet. From then on the resting stop must sit at
  max(entry × (1 + `take_profit_floor_pct`/100), high-water mark × (1 −
  `stop_ratchet_trail_pct`/100)), rounded to tick; whenever the required level exceeds
  the current resting stop, the monitor loop cancels-and-replaces it (verify the new stop
  is confirmed). The stop only ever moves UP. The floor was raised from plain breakeven
  to +10% on 2026-07-28 (per user) — once a position is up 20%, the worst outcome is now
  a +10% win, not a scratch. In practice, with only a 20%-30% window before the hard cap
  below, a 30% trail off a high-water mark that's at most +30% above entry rarely if
  ever exceeds the +10% floor — so arming the ratchet effectively snaps the stop straight
  to entry × 1.10 and holds it there, while the hard cap two steps above still bounds the
  upside. The winner keeps running under the discretionary rules below in the meantime
  (motivated by NBIS peaking +113% intraday with the stop still at −30%).
- **Hard take-profit — instant sale at +30% (lowered 2026-07-28, was +100%):** mark ≥
  entry × (1 + `hard_take_profit_pct`/100) → cancel the resting stop and sell-to-close at
  mid immediately, no discretion — the profit is locked the moment it's seen. Enforced
  software-side by the monitor loop (5-minute granularity): Robinhood holds only one
  resting sell per contract and that slot belongs to the stop, so the cap cannot rest
  broker-side. Checked BEFORE the ratchet logic each cycle. Motivated by 2026-07-28: MU,
  AMD, and MRVL puts each peaked between +21% and +35% intraday, then round-tripped to
  breakeven or red well before the old +50%/+100% thresholds ever engaged — capturing a
  solid +30% mechanically was judged more reliable than letting winners run through that
  kind of intraday whipsaw. `scale_out_pct` (40%) remains above this hard cap and stays
  dormant — a position is always forced out at +30% before it can reach 40%.
- **Discretionary profit-taking:** the agent may sell a winner at any gain level — before
  or after the ratchet arms — when momentum breaks (lower highs, VWAP lost, volume faded)
  or into an obvious exhaustion spike — take the gain rather than round-trip it. The
  ratchet is a floor, never a reason to hold through a confirmed breakdown. Record the
  reasoning in the journal every time.
- **Stop loss (hard floor):** mark ≤ −30% under entry premium → sell-to-close immediately,
  at mid, repricing toward the bid every 5 minutes until filled. Losers get no discretion.
- **Forced flat:** whatever remains is closed starting 3:40 ET: limit at mid → reprice toward
  bid at 3:48 → by 3:53, cross the spread (limit at bid) to guarantee the fill. All open
  option orders from the strategy are cancelled after the position is flat.
- If a close somehow fails before 4:00 ET, notify the user immediately with the position
  details — do not silently carry it.

## 7. Execution authorization

Per `config.yaml`:
- `entry_auto_execute: false` — the entry run reviews the order (`review_option_order`),
  posts the full quote/alerts, and asks the user to confirm before placing. Setting it to
  `true` in this file is the user's standing instruction to place entries without asking.
- `exit_auto_execute: true` — closes are risk-reducing and time-critical; they execute
  without waiting. Set `false` to be asked first (risk: unanswered = overnight hold).

## 8. Journaling

Every run appends to `journal/YYYY-MM-DD.md` (template in `journal/TEMPLATE.md`): news
digest, candidates considered, trade taken (or reason for no trade), fills, P&L, and one
lesson. Committed and pushed after every run — the journal is the system's memory.

## 9. Known limitations & warnings

- Long calls and puts both lose to theta and IV crush even when direction is right. Expect
  many small losses; the edge, if any, comes from cutting losers fast and exercising good
  judgment on when winners are done. This is a high-risk strategy — size it with money you
  can lose.
- Level 2 = no spreads; there is no defined-risk vertical available to cap IV exposure on
  either side.
- Scanner % change filter reads ~0 outside regular hours; pre-market candidate work relies
  on news + prior-day closes, and the 9:45 run re-validates with live data.
- Puts are newer (added 2026-07-21) and have no live track record yet in this system —
  watch the first several put trades closely for anything the calls-only design didn't
  anticipate (e.g. downside gap risk behaves differently from upside chasing).
- Nothing here is financial advice; the user owns every parameter in `config.yaml`.
