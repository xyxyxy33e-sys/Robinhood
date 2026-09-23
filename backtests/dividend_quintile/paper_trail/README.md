# Paper Trail: 30-Stock Barbell, $10,000 Start

A local, simulated paper-trading ledger for the strategy in `../BARBELL_30.md`.
**No real or connected brokerage account is touched** -- this only records
trades against live market prices and tracks state in this folder.

- **Inception**: 2026-09-23, $10,000, equal-weighted across the 30 target
  names (fractional shares, so weights are exact -- no whole-share rounding).
- **Rebalance cadence**: monthly, on the first trading day of the month --
  recompute the target 10-high-yield + 20-growth list from scratch and trade
  to the new equal weights.

## Files
- `state.json` -- current cash + share counts (the source of truth).
- `ledger.csv` -- full trade history (every BUY/SELL/MARK event).
- `paper_trail.py` -- the script; see its docstring for commands.

## Commands
```
python3 paper_trail.py status       # current holdings, value, P&L (no trades)
python3 paper_trail.py mark         # same as status, but also logs a MARK row to ledger.csv
python3 paper_trail.py rebalance    # recompute target list, trade to new weights
python3 paper_trail.py init         # one-time setup (already done; re-running is a no-op)
```

## Monthly rebalance schedule
Run `rebalance` on the first trading day of each month. A scheduled Routine
in this session fires on the 1st-3rd of each month to trigger this.
