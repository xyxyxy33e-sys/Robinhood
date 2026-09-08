# Daily check-in runbook

Run once per trading day after the close (the scheduled Routine fires at 16:15 ET).
Skip on market holidays — `get_equity_quotes` will still return the prior session's
close, and recording it twice under a new date would fabricate a flat day.

## 1. Confirm the session actually closed today
`get_equity_quotes(["SPY"])` → check `venue_last_trade_time` is today's date at 20:00 UTC
(19:59:59 ET-close timestamp). If it is a prior date, stop: holiday.

## 2. Snapshot closes
Call `get_equity_quotes` with SPY plus every symbol in `portfolio/holdings.json`
(currently: NVDA GOOGL MSFT JPM LLY UNH AAPL AMZN XOM V ANET CRM). Use
`quote.last_trade_price` (regular session). Write:

```json
{ "date": "YYYY-MM-DD", "source": "robinhood-mcp get_equity_quotes", "closes": { "SPY": 0.0, ... } }
```
to `data/prices/YYYY-MM-DD.json`.

## 3. Record and check
```
python3 scripts/record_close.py YYYY-MM-DD
python3 scripts/check_drift.py
```

## 4. Rebalance only if proposed
If `check_drift.py` prints proposals, apply them with
`python3 scripts/apply_trades.py YYYY-MM-DD --yes`, then re-run `record_close.py` for the
same date so history reflects post-trade cash. Respect the IPS frequency limit
(max 4 trades per 5 sessions) — check `portfolio/trades.csv` first.

If it prints a **thesis review**, do not auto-trade. Restate the thesis in one sentence
in the commit message, or close the position with a manual entry.

## 5. Publish
```
python3 scripts/build_dashboard.py
git add -A && git commit -m "checkin YYYY-MM-DD: NAV $X (+Y% vs SPY +Z%)"
git push -u origin claude/model-stock-portfolio-19nk9z
```
Then republish `dashboard/index.html` to the existing Artifact URL so the link stays stable.

## 6. Report
One line: NAV, day change, cumulative vs SPY, any trades or flags.
