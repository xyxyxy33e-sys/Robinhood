# Robinhood — Daily Momentum Calls

An agentic day-trading system for long options on Robinhood's agentic account, executed by
scheduled Claude Code sessions. It gathers news before the open, buys calls on confirmed
bullish momentum and puts on confirmed bearish momentum (`enable_puts`, added 2026-07-21),
and is always flat by the close. The name predates the puts addition; it still trades both
directions under it.

## How it works

Claude Code Routines fire into the trading session every weekday (times ET):

1. **~8:00 — Pre-market** (`runbooks/premarket.md`): news, earnings calendar, ranked
   candidates (calls and puts together) → journal. Research only, no orders.
2. **~9:00 — Pre-entry confirm** (`runbooks/premarket_confirm.md`): re-reads the same
   candidates against the 8 AM view to catch overnight reversals. Research only.
3. **9:35 — Entry** (`runbooks/entry.md`): live momentum confirmation via the saved
   "Daily Momentum Calls" / "Daily Momentum Puts" scanners + a direction-aware tape check
   → ATM calls or puts, DTE per `config.yaml`, limit at mid. Sized and authorized per
   `config.yaml`, always reviewed via `review_option_order`. On a no-trade it re-checks
   **every 5 minutes** until 1:30 PM ET — the late-entry rule measures legs over
   consecutive 5-minute bars, so a faster loop re-reads the same bar.
4. **Every 2 min while a position is open — Monitor** (`runbooks/monitor.md`):
   self-re-arming check-in loop — stop ratcheting, profit floors, scale-out, and
   re-entries up to the daily limits (until 1:30 PM ET). Each firing also arms a ~10 min
   backup wake, because scheduled-wake delivery has been running late.
5. **~3:30 — Exit** (`runbooks/exit.md`): close the position, forced flat before the bell.
   Never holds overnight.

The hard stop rests **broker-side** from the moment of entry, so it does not depend on the
monitor loop running on time.

Where to look:
- [`config.yaml`](config.yaml) — every live parameter, and nothing else.
- [`docs/RATIONALE.md`](docs/RATIONALE.md) — *why* each value is what it is. Almost all of
  them are scar tissue from a specific incident; read this before changing anything.
- [`STRATEGY.md`](STRATEGY.md) — the full ruleset.
- `data/leg_log.csv` — every momentum leg the entry phase has evaluated, accepted and
  declined, with the measurements behind each call. This is the sample the entry
  thresholds get validated against; declines alone would be survivorship-biased.
- `data/chain_log.csv` — every option strike priced, pass or fail, with OI, spread and
  displayed depth. Same purpose for the liquidity gates.
- `journal/YYYY-MM-DD.md` — every run appends and pushes, so the journal is the durable
  memory across sessions.

## Controls

- **Dry run:** `dry_run: true` in `config.yaml` (currently ON, week of 2026-08-17) runs
  every phase against live data but places **no orders at all** — fills are paper and
  marked to market through the real exit cascade, so the logs still fill up. It never
  auto-expires; turning it off is a deliberate edit.
- **All knobs:** `config.yaml` — sizing, DTE, stops, and the two authorization flags
  (`entry_auto_execute`, `exit_auto_execute`). Edit + push; next run picks it up.
- **Pause/stop:** disable or delete the Routines (ask Claude, or manage Routines in the
  Claude UI). Deleting the Routines fully stops the system.
- **Funding:** the Agentic account is a cash account — calls need settled cash, and sale
  proceeds settle T+1. The entry run skips the day (and tells you) below
  `min_buying_power_to_trade`.

## Risk disclaimer

Long options can go to zero the same day. This system caps risk per trade and forces daily
flatness, but losses are expected and can compound. Nothing in this repo is financial
advice; you own the parameters and the authorization flags.
