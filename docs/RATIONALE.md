# Rationale — why each rule exists

Reference only. **Nothing here is operational.** `config.yaml` holds the live values;
the runbooks hold the steps. This file exists so those two can stay short enough to
read under time pressure.

Every rule below was added after a specific incident or test. Read this before
changing a parameter — most of them are scar tissue, and the reason is rarely obvious
from the number alone. Full working is in the dated journals.

---

## Contract selection

**`dte_min: 7`, `dte_target: 14` (2026-08-12).** Previously `dte_min: 2` with
"pick the nearest expiry", which always resolved to the shortest contract on the
board — simultaneously the worst on both axes that matter: highest leverage (so the
−25% stop trips on the smallest move) and highest theta. That was never a deliberate
choice; it fell out of the word "nearest". Measured on the live SMCI $38C chain, same
strike, five expiries:

| DTE | leverage | theta/day | stop trips at |
|---|---|---|---|
| 2 | 17.1× | −26.9% | 1.46% adverse move |
| 9 | 10.4× | −5.9% | 2.40% |
| 16 | 7.9× | −3.3% | 3.16% |
| 37 | 5.7× | −1.4% | 4.39% |

A 2-DTE contract bleeds ~27% of premium per day — nearly the whole stop distance —
so the underlying must move ~1.6% in your favour just to break even on the clock.
Backtest over 20 name-days: 2 DTE was the only negative bucket (avg −1.25%, **median
−25%**, i.e. a full stop-out was the modal outcome) while 9–16 DTE returned +6–7% at
65–75% win rates. There is a real interior optimum — too short is stopped out by
noise and decay, too long lacks the leverage to reach the profit rungs (zero hard-TP
hits at 23 and 37 DTE). 14 sits centrally in the flat 9–16 band rather than on the
measured 16-DTE peak, deliberately: n=20 is too small to justify fitting the exact
maximum.

**IV/vega, measured 2026-08-12.** IV was backed out of Black-Scholes at 30-min bars
across 9 contracts. All five contracts traded that day lost IV (mean −7.0 pts over
~3.5h). Decisively, IV decay is *monotonically worse at shorter DTE* — 2 DTE cost
−8.7% of premium to vega vs −1.3% at 37 DTE. Front-month IV is both higher in level
and faster-decaying, which more than offsets the greater vega of longer contracts.
So IV adds a **fourth** independent penalty to short-dated contracts alongside
leverage, theta and vol level. Charging measured vega alongside theta pushed 2 DTE
outright negative (−0.53%) and nudged the optimum to 16 DTE. Caveat: one session.

**Expiry step-out on structural cap (2026-08-07).** TEAM traded $146–153 all session
while the highest listed 8/14 strike was $145 — no ATM or OTM strike existed at all.
Structural-cap cases only; never step out because a strike exists but fails a gate.

**`min_open_interest: 500`.** OI updates once daily after settlement, so it **lags
badly on earnings-reaction names** — a name that gapped this morning on a real
catalyst can sit on yesterday's pre-earnings OI all session. Observed repeatedly
2026-07-28/29: GNRC OI 7, VRT 33–65, GEHC 25–171, STX 23–93, BIIB 23–35, all on real
catalyst-confirmed moves. Checked whether lowering it would help: in **every** case
the same contract also failed `max_spread_pct_of_mid` independently (GEHC $71C 53%,
BIIB $210C 81%, STX 16–28%). Thin OI and wide spreads move together — both reflect
the same absent market-maker interest. Lowering this gate alone would unlock nothing,
only admit worse execution.

**`min_quote_size_for_entry: 10` (2026-08-06).** U $40C 8/14: OI (1,393) and spread
(7.7%) both cleared, but live `ask_size` was 2–4 contracts against a 16-lot buy.
Displayed depth then swung wildly (2–4 → 463/243 six minutes later → 2 right after
the stop fired) and the resting stop_market swept **~26% below its $1.70 trigger**.
Neither OI nor spread catches this — both are static/percentage measures blind to
top-of-book size.

**`thin_liquidity_oi_threshold: 2500` (2026-08-06).** A contract can clear every gate
and still be far thinner than a genuinely liquid name. U's $40C had OI 1,393
(comfortably above the 500 minimum) but its spread flickered 6–30% all day and both
exits suffered real slippage. THIN-flagged positions arm the ratchet earlier and
trail tighter. OI is static intraday, so the flag never changes for a position's life.

---

## Entry timing and momentum

**Entry at 9:35.** Has survived three separate challenges: moved to 9:45 on
2026-07-31, back to 9:35 on 2026-08-03, "permanent" 2026-08-07, then moved to 10:30
on 2026-08-12 and **reverted the same evening**. The 10:30 move came from a
20-name-day backtest showing stop-outs falling with later entry; an expanded
**47-name-day / 14-session** test did not replicate it — the cells came out
non-monotonic (09:30 +1.06%, 10:00 −0.65%, 10:30 −7.81%, 11:00 −1.40%), the signature
of noise. And once `dte_target` rose to 14 the sign flipped entirely: 09:30 +5.78%
vs 10:30 +2.18%. **The DTE change subsumes the timing change** — widening the stop's
tolerance from 1.46% to 2.90% solves the opening-volatility problem without giving up
the move, and once solved, entering early is better because more of the day's range
is still ahead. Holding 10:30 cost −3.60pp.

**§1.3 late-re-check leg confirmation (codified 2026-07-21, revised 2026-08-14).**
Price beyond the open is necessary but not sufficient. The current rule has two
vetoes — a **volume ratio** against the name's own pre-leg baseline, and **intact
structure** (a higher low or new extreme, made and held, sequence low unbroken).
Leg age is recorded but does not block. Measure "elevated" against the trailing
baseline, never against the opening range, which is always inflated and will make any
later leg look weak by comparison.

**Why the 15-minute clock was demoted (review, 2026-08-14).**

The original rule made duration a co-equal veto: "sustained 15+ minutes." Four
findings retired it as a gate.

*1. It was never independent of the volume clause.* On 5-minute bars, "several
consecutive closes" **is** 15 minutes — three bars, by construction. The rule stated
one measurement twice and presented it as two tests, which is why it so rarely added
anything.

*2. The founding cases turned on volume, never duration.* The rule was codified from
the NVS-declined / TSM-declined-then-accepted precedents. Reading them back:

| case | leg age | decision | what actually decided it |
|---|---|---|---|
| NVS 9:55 | ~20 min (4 higher closes) | declined | volume *declining* 34K→17K |
| NVS 10:13 | ~15 min | accepted | volume *rising* 16.5K→27.1K |
| TSM 11:13 | ~90 min of grind | declined | no volume surge on the reclaim |
| TSM 11:29 | ~20 min | accepted | moderate-but-real volume |

Duration was *satisfied* in both declines. The 15-minute figure appears to have been
back-derived from the bar count, not measured against outcomes.

*3. In four of the five live declines, volume failed independently* — the clock was
redundant. SMCI 0.9×; BIRK-1st collapsing; RDDT-1st 1.23% inside Gate B *and* 1.23×
volume *and* 7 minutes (three fails); RDDT-2nd 0.42×.

*4. The one case where the clock bound alone was decided by 60 seconds.* BIRK's second
leg on 8/13: volume 3.35× its own trailing baseline, a new session high made and held,
Gate A passed, Gate B inactive, above open. The journal is explicit — "**holding
strictly on the clock, not the setup quality** — 14 min, need 15." It then failed at
~16 minutes on the largest-volume down bar of the leg. Vindicated, but had the leg
begun one minute earlier it qualifies, we buy, and we lose. That is a coin landing
well, not a validated threshold.

There is a further tell: the old rule needed a patch saying "a leg already rolling over
does not qualify by aging into the window." That concedes time-in-force is meaningless
without a health check — and if the health check decides, the clock is not load-bearing.
The revised rule promotes that health check (structure) to the veto and drops the patch.

**What replaced it.** Structure is what the journals were *actually* tracking, and it
separates the cases the clock could not: it fails a rolling-over leg immediately rather
than waiting for a timer, and breaking the low the sequence was built on is a crisp,
computable disqualification — precisely what killed RDDT at 10:26 (8/14) and BIRK at
10:42 (8/13). `late_entry_min_volume_ratio: 1.5` codifies existing discretion rather
than changing it: it is consistent with every live judgment on record (passed NBIS 2.9×
and BIRK 3.35×; rejected RDDT 1.23× as "weak", SMCI 0.9×, RDDT 0.42×).

**The clock is not disproven, only unproven.** There is a plausible mechanism — in a
gapped name the first 10–15 minutes is where the marginal buyer absorbs gap supply, so
surviving it should carry information. `late_entry_advisory_leg_minutes` keeps the
figure recorded so the hypothesis stays testable. Restore it as a veto only on evidence
from `data/leg_log.csv`, not on intuition.

**Why the log exists (2026-08-14).** The old evidence was survivorship-friendly by
construction, and worse than first stated: not only do we never observe the legs the
rule wrongly blocked, the sample is *generated by the rule* — we only measure legs at
the moment they are "almost qualified," which is exactly when a dying leg is most
conspicuous. "Five for five" was never a hit rate; it described how the sample was
drawn. `data/leg_log.csv` records every evaluated leg, **accepted and declined**, with
age, volume ratio, structure, the blocking reason, and the subsequent outcome. Until it
holds acceptances as well as declines, no threshold in this section can be validated and
none should be tightened. It is backfilled with the twelve cases reconstructable from
the journals; `blocking_reason: CLOCK_ONLY` marks legs the retired clock would have
vetoed on its own.

**Volume direction means opposite things depending on price (2026-08-12).** Declining
volume during a *consolidation* is healthy — that is what a proper flag looks like.
Declining volume during an *advance* is a failing thrust. NBIS's flag ebbing to 71.5K
sh/min was constructive; SMCI's advance at 0.9× baseline was not. Applying §3.2
mechanically without this distinction would have both taken SMCI and rejected NBIS —
exactly backwards.

**Leader re-entry (2026-07-21).** A symbol closed earlier today for a profit stays
first in the rotation — it has already proven catalyst, liquidity and tape. Trigger is
a *resumption, never a dip*: the pullback must stabilise at a higher low, then resume
with the full volume bar. Expect the second entry to be structurally worse (pumped IV,
heavier theta); the volume bar is the compensation, not optional.

---

## Opening gap-fade guard (2026-08-12) — **under review, see caveats**

Added after two same-day stop-outs. Both losers were bought *into the opening
distribution of a large premarket gap*; the one winner was bought after the first
pullback completed:

| | open-bar close pos | gap | entry vs session high | vs VWAP | outcome |
|---|---|---|---|---|---|
| CRWV | 0.21 | +20.1% | −0.74% | +1.75% | STOP −27.19% |
| NBIS | 0.27 | +17.7% | −0.84% | +2.62% | STOP −25.63% |
| SMCI | 0.83 | +10.7% | −3.63% | −0.66% | WIN +3.96% |

Out-of-sample against 2026-08-11 (RIOT 0.14 faded all day, LEGN 0.24 fully reversed,
SE 0.63 strongest name of the day, HIMS put 0.72 correctly rejected by the inverted
test): **7 of 7 classified correctly**, clusters far apart (worst success 0.63 vs best
failure 0.27), so any threshold in 0.35–0.55 separates them.

**Counterintuitive finding: VWAP was inverted here.** Both losers were *above* VWAP at
entry and the winner *below* it. A naive "must be above VWAP" gate would have
green-lit both stop-outs and blocked the one winner. Being extended above VWAP in the
opening 15 minutes is a warning, not a confirmation — the opposite of its meaning
later in the session. No VWAP-based *opening* gate was added as a result.

### Live review (2026-08-14) — both gates now look weaker than at derivation

**Gate A out-of-sample record is poor.** Four passes since going live; three finished
below their opening price:

| date | name | Gate A | what followed |
|---|---|---|---|
| 8/13 | HLIT | 0.75 | collapsed +23% → +7%, fresh lows, well below open |
| 8/13 | BIRK | 0.59 | two failed legs, closed below open |
| 8/14 | NU | 0.535 | decayed +15.1% → +8.6%, never reclaimed open |
| 8/14 | RDDT | **0.988** | peaked +16.5%, faded to +11.3%, two failed legs |

RDDT is the damaging case: **0.988 is the strongest reading ever recorded** — a
near-perfect bullish opening bar, exactly what the gate identifies — and it still
faded all day. The original 7/7 may have been fitted to two unusually clean sessions.
*Caveat: none were traded, and end-of-day price is not trade P&L; a stop/ratchet could
have exited very differently.*

**Gate B is 4-for-4 live but structurally biased.** Correct blocks: BIRK 8/13 (0.263%
under high, closed ~$1.50 lower), RDDT 8/14 ×3 (0.014%, 1.30%, 1.23% under high, all
above where it ended). Against that, the known counterfactual: **PLTR on 2026-08-04,
where Gate B would have blocked both entries (0.76% and 1.06% under the high) — the
only two winners that week, +$724 combined.**

The defect is structural, not luck. Gate B measures distance from a **running** session
high that ratchets upward, so a name making continuous new highs is *by construction*
always near its high. RDDT oscillated in and out of the band three times on 8/14
(0.014% → 2.01% → 1.23%). **Gate B is therefore systematically most restrictive on the
strongest-trending names** — precisely the PLTR failure mode.

**Neither gate has yet been the sole binding constraint on any candidate.** Every name
they blocked was simultaneously failing liquidity or §3.2. They have produced zero
realized P&L impact in either direction, which also means Gate B's 4/4 is weaker
evidence than it looks — nothing was riding on it.

**Proposals for the weekend review (not implemented):** (1) test Gate A against the
existing 47-name-day sample rather than another handful of days; (2) replace Gate B's
ratcheting reference with a non-ratcheting one — distance from the *opening-range*
high, or require the pullback-and-higher-low structure directly instead of proxying it
with a raw percentage. Do **not** tighten either on current evidence.

---

## Exits

**`stop_loss_pct: -25` (tightened from −30, 2026-07-30).** MSFT #2: the stop_market
trigger fired correctly at exactly −30% ($5.60) but filled at $4.80 (−40%) on ordinary
slippage. stop_market guarantees the exit, not the fill. Tightening the trigger buys
cushion against that gap. **Deliberately not scaled** when leverage halved on
2026-08-12 — holding it at −25% while leverage falls is exactly what widens tolerance
from 1.71% to 2.90% of underlying movement. That widening *is* the DTE change. Do not
"finish the job" by scaling it. It was also the least stable parameter in the
2026-08-12 scan (ALL says −30, July −20, August −25) — that spread across subsamples is
what an overfit parameter looks like.

**`hard_take_profit_pct: 50` (raised from 30, 2026-07-28).** +30% was cutting winners
short: NBIS 7/21 capped at +33% vs the +80% actually banked; TSLA 7/23 ~+44% vs +87%;
SMCI 7/22 ~+38% vs +67% — roughly $1,050 of shortfall in one week. +50% is the
compromise between that and the old +100% cap, which let NBIS run to +113% completely
unprotected.

**`take_profit_pct: 12` and `stop_ratchet_trail_pct: 20` (2026-08-12 scan).** Each exit
parameter was scanned individually at the 14-DTE profile across 47 name-days with a
July/August split-sample stability check. Only two showed a stable, monotonic effect
(both subsamples agreeing): arm 20→12 and trail 30→20. Combined effect +4.71% → +6.05%,
improving the full sample *and* both subsamples; stops 18→17, median +7.7% → +10.5%.

**Deliberately stopped short of the scan optimum (arm 10 / trail 15, which measured
+6.98%).** The response curve stayed monotonic to the edge of the tested range, which
usually means the simulation is missing a cost rather than that an optimum was found —
and here the missing cost is identified: the backtest checks the trail on **30-minute
bars** (9 checks/session) while monitor.md checks every cycle, so tight trails are
systematically flattered. The arm is a one-time trigger and far less
resolution-sensitive, which is why it moved closer to its optimum than the trail did.

**Not changed, and why:** `take_profit_floor_pct: 10` was completely flat in the scan
(0/3/5/8/10 all returned an identical +4.71%) — no evidence either way. `hard_take_profit_pct`
and `scale_out_pct` were near-flat and subsample-unstable.

**Floor clamp ordering constraint.** The effective floor once armed is
**min(`take_profit_floor_pct`, the arm level that applied)**. With THIN arming at +8%
against a +10% floor, an unclamped floor would sit *above* the mark at the instant of
arming and force an immediate sell — turning the THIN ratchet into a hard take-profit
at +8%. Surfaced as a bug in the scan harness before it could reach live config.

**Stall-trail (2026-07-28).** Reconstructing that day's MU/AMD trades against actual
monitor checkpoints showed a 10% trail on a stalling bar would have caught MU's stall
at 10:26 (peaked +35.4% at 10:16, flat at 10:26) and exited ~+22% instead of riding the
wider trail down — roughly +$538 better across MU+AMD.

**Early floor (2026-07-30).** AMD peaked +11.5% and MSFT's re-entry +8.44% — real,
thesis-confirming pops — then ground down on theta for nearly an hour without ever
reaching the arm level, round-tripping to full stop-outs (−$1,020 and −$1,280).
Nothing between 0% and the arm existed to protect either. Backtested over 19 trades
(07/16–07/30): would have improved 4 trades for +$2,423 combined, with zero winners
where it clipped a later recovery.

**Midday floor (2026-08-03).** BABA peaked only +5% at 11:40 — below the early floor's
+8% — so no protection engaged, then faded through midday to a full −25% stop-out.
Backtest 07/16–08/03 (23 trades): only 3 had a high-water mark inside 11:30–13:30 AND
were still open past 13:30 (the only ones that test "does a midday peak keep
extending?") — **all three faded**, averaging −28%. Zero counterexamples, but n=3.

**Late-day floor (2026-08-06).** U's second trade sat at +10–11% around 15:00–15:06,
well before the ratchet armed at 15:20, and the eventual stop banked only +2.28% after
slippage. Unlike the midday floor this one locks in real profit (trigger = floor = +5%)
rather than protecting breakeven.

**`min_quote_size_for_stop_update: 5` (2026-07-31).** AMZN: the ratchet computed a new
stop off a live mark, cancelled the old resting stop and placed the new stop_market —
which filled *instantly* at $3.50 against a $3.60 trigger, because the option's quote
had cratered on a print backed by single-digit depth, even though AMZN stock was still
near session highs. This gate only ever *delays* raising a stop; it never removes
protection.

**`ratchet_stop_type: stop_limit` (2026-08-06).** U's resting stop_market fired at
15:33:52 on a $2.41 trigger but filled at $2.24 (~7% slippage) — mild next to the same
contract's ~26% that morning, but still real banked profit given back. Once a genuine
profit cushion exists, bounding slippage is worth the fill risk. Reverts to stop_market
at `ratchet_stop_limit_cutoff_et` because that close to the forced close, certainty of
getting flat matters more than a few points of slippage.

**Scale-out (2026-07-23).** GOOGL peaked +44.1% — under the then-+50% arm — and
round-tripped to −3.9%. `scale_out_floor_pct: -15` guarantees the whole trade stays net
positive once the scale-out banks (1/3 × 40% > 2/3 × 15%) while sitting below normal
chop; a breakeven floor was evaluated and rejected because it would have chopped
GOOGL's remainder out in the −3.9% dip.

**Buying-power sizing (2026-08-12).** Previously sizing ignored live buying power and an
insufficient-cash rejection was a hard stop, with downsizing forbidden. That cost a
fully-qualified SMCI trade: it passed every tape gate (3.4× volume expansion, leader
re-entry, new session high) and every liquidity gate, but sizing demanded 31 contracts
($3,255) against $1,429.66 of buying power — 13 were affordable and the trade was
skipped entirely. Per user, the smaller position is preferred to none.

---

## Execution mechanics

**9:30–9:45 stop_market blackout.** Robinhood rejects resting stop_market orders until
9:45 (`OPTION_STOP_MARKET_INVALID_TIME_MARKET_OPEN`). **stop_limit IS accepted** during
the blackout — confirmed by direct diagnostic test on 2026-08-03 (AAPL $305C, order
accepted and cancelled cleanly). The blackout is scoped to the unbounded-price order
type, not to stops in general. Hence the pre-9:45 stop_limit path with a 15% limit
buffer (widened from 5% so it has a realistic chance of filling if touched), upgraded
to stop_market at 9:45.

**Pre-placement spread re-check (2026-08-06).** U $40C cleared the spread gate at 8.7%,
then `review_option_order` came back seconds later at 12.86% — back over the line. A
quote can go stale between the gate check and placement.

**Only one resting sell per contract.** Robinhood has no OCO for options, so only one
of the two protective orders can rest broker-side; the monitor loop enforces the other
in software. The stop keeps the broker-side slot.

**Loop resilience (2026-08-05).** A `get_equity_historicals` call failed on a transient
classifier error mid-cycle and the loop died silently — no next wake had been armed, so
nothing resumed until the user intervened manually. A firing must never end without
either closing a position or arming the next one.

---

## Infrastructure — scheduled-wake delivery (2026-08-14)

Measured across all 229 `send_later` fires recording both scheduled and actual times:

| date | fires | median lag | max | >5 min late |
|---|---|---|---|---|
| 07-17…07-22 | 100 | 0.4 min | 2.2 min | **0/100** |
| 08-12 | 67 | 0.9 min | 22.9 min | 8/67 |
| 08-13 | 38 | 8.0 min | 32.8 min | 21/38 |
| 08-14 | 24 | 9.5 min | **101.5 min** | 18/24 |

**Delivery has degraded ~20× and is still worsening.** In July not one of 100 wakes was
>5 min late; on 8/14 three-quarters were, with one at 101 minutes. On the same day the
~8 AM premarket Routine arrived 4h41m late and phases arrived **out of order** (entry
~9:40 near on-time, premarket not until 12:41) — evidence of a delivery-queue problem
rather than a bad cron. The daily phase Routines do not appear in `list_triggers` at all
(paginated ~160 back through 8/12, separately through 8/05), so their lag cannot be
measured directly; the premarket link is inferred from shape, not proven.

**Correctly scoping the risk:** the hard stop is always resting **broker-side** and does
not depend on the loop being alive. So a late monitor cycle does *not* expose the
position to unbounded loss. What it delays is **profit protection** — ratchet arms,
floor raises, hard-TP and scale-out are all software-side. The exposure is give-back of
gains, not catastrophic downside. (An earlier framing of this as "genuine capital risk"
overstated it.)

This is what motivates the cadence design in `runbooks/monitor.md`.
