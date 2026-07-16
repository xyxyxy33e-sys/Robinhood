# Robinhood — Daily Momentum Calls

An agentic day-trading system for long calls on Robinhood's agentic account, executed by
scheduled Claude Code sessions. It gathers news before the open, buys one momentum call
after the open, and is always flat by the close.

## How it works

Three Claude Code Routines fire into the trading session every weekday (times ET):

1. **~8:00 — Pre-market** (`runbooks/premarket.md`): news, earnings calendar, ranked
   candidates → journal.
2. **9:35 — Entry** (`runbooks/entry.md`): live momentum confirmation via the saved
   "Daily Momentum Calls" scanner + tape check → ATM calls, 7–21 DTE, limit at mid.
   Sized and authorized per `config.yaml`, always reviewed via `review_option_order`.
   On a no-trade, re-checks every 15 minutes until 11:30 ET.
3. **Every 5 min while a position is open — Monitor** (`runbooks/monitor.md`):
   self-re-arming check-in loop — hard stop enforcement, discretionary profit-taking,
   and re-entries up to the daily limits (until 11:30 ET).
4. **~3:30 — Exit** (`runbooks/exit.md`): hard stop −30%, discretionary profit-taking
   (agent judgment on momentum/tape), forced flat by 3:53 ET. Never holds overnight.

The full ruleset lives in [`STRATEGY.md`](STRATEGY.md). Every run appends to
`journal/YYYY-MM-DD.md` and pushes, so the journal is the durable memory across sessions.

## Controls

- **All knobs:** `config.yaml` — sizing, DTE, stops, and the two authorization flags
  (`entry_auto_execute`, `exit_auto_execute`). Edit + push; next run picks it up.
- **Pause/stop:** disable or delete the three Routines (ask Claude, or manage Routines in
  the Claude UI). Deleting the Routines fully stops the system.
- **Funding:** the Agentic account is a cash account — calls need settled cash, and sale
  proceeds settle T+1. The entry run skips the day (and tells you) below
  `min_buying_power_to_trade`.

## Risk disclaimer

Long options can go to zero the same day. This system caps risk per trade and forces daily
flatness, but losses are expected and can compound. Nothing in this repo is financial
advice; you own the parameters and the authorization flags.
