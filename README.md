# Model Alpha-12 — paper portfolio vs SPY

A $10,000 model stock portfolio, started at the 2026-09-04 close, whose only job is to
beat SPY. Market data comes from the Robinhood MCP server; **no live orders are ever placed**.

| | |
|---|---|
| Rules / investment policy | [`portfolio/strategy.md`](portfolio/strategy.md) |
| Current positions & targets | [`portfolio/holdings.json`](portfolio/holdings.json) |
| Daily NAV vs SPY ledger | [`portfolio/history.csv`](portfolio/history.csv) |
| Trade log | [`portfolio/trades.csv`](portfolio/trades.csv) |
| Raw close snapshots | `data/prices/YYYY-MM-DD.json` |
| Dashboard | [`dashboard/index.html`](dashboard/index.html) (regenerated daily) |
| Daily runbook | [`CHECKIN.md`](CHECKIN.md) |

## Daily check-in (after 4pm ET)

```bash
# 1. write data/prices/YYYY-MM-DD.json from Robinhood MCP get_equity_quotes (SPY + all holdings)
python3 scripts/record_close.py YYYY-MM-DD      # append NAV/SPY row to history.csv
python3 scripts/check_drift.py                  # drift table + rebalance proposal, if any
python3 scripts/apply_trades.py YYYY-MM-DD      # only if a proposal was printed
python3 scripts/record_close.py YYYY-MM-DD      # re-mark after trades (idempotent)
python3 scripts/build_dashboard.py              # regenerate dashboard/index.html
```

Every script is plain Python 3 with no dependencies. Re-running any step for the same date
overwrites that date's row rather than duplicating it.

## How drift is handled

A position is flagged when it is more than **25% of its target away** *or* more than
**3 percentage points away** — whichever trips first — and is only traded when the
required order is at least **$75**. That floor is deliberate: on a $10k book, trading every
small wiggle hands the edge to spreads. Full rules, including position caps, thesis-review
stops and the anti-whipsaw cooldown, are in the strategy document.
