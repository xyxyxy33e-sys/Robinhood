# Daily check-in runbook (v3 · daily reversal, from 2026-10-05)

Run once per trading day after the close (the scheduled Routine fires at 16:15 ET).

1. `git pull origin claude/model-stock-portfolio-19nk9z`
2. `get_equity_quotes` for **SPY plus all 29 symbols in `data/universe.json`** — two calls of 15
   (closes are omitted above 20 symbols per call). If SPY's `venue_last_trade_time` is not today,
   the market was closed: stop, record nothing.
3. Write `data/prices/YYYY-MM-DD.json` with `quote.last_trade_price` for all 30 symbols.
4. Mark the book, compute the signal, trade, re-mark:
   ```
   python3 scripts/record_close.py YYYY-MM-DD
   python3 scripts/daily_signal.py YYYY-MM-DD
   python3 scripts/reconstitute.py YYYY-MM-DD
   python3 scripts/record_close.py YYYY-MM-DD
   ```
   If the dashboard shows a drawdown worse than −30% from peak, stop after the first
   `record_close` and ask the owner before trading.
5. `python3 scripts/build_dashboard.py`, commit `checkin YYYY-MM-DD: NAV $X (day ±Y%, cum ±Z%)`,
   push, and republish `dashboard/index.html` to the existing artifact.
6. Report: NAV, day change, cumulative return, max drawdown, today's buys and sells.

---

# Earlier runbook (v1/v2, retained for the record)


Run once per trading day after the close (the scheduled Routine fires at 16:15 ET).
Skip on market holidays — `get_equity_quotes` will still return the prior session's
close, and recording it twice under a new date would fabricate a flat day.

## 1. Confirm the session actually closed today
`get_equity_quotes(["SPY"])` → check `venue_last_trade_time` is today's date at 20:00 UTC
(19:59:59 ET-close timestamp). If it is a prior date, stop: holiday.

## 2. Snapshot closes
Call `get_equity_quotes` with SPY plus every symbol in `portfolio/holdings.json` **plus every
target in `portfolio/pending_reconstitution.json` if that file exists**. Use
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

## 4a. Execute a pending reconstitution
If `portfolio/pending_reconstitution.json` exists and its `effective` date is today or earlier:
```
python3 scripts/reconstitute.py YYYY-MM-DD
python3 scripts/record_close.py YYYY-MM-DD   # re-mark post-trade
```
Skip step 4 that day.

## 4b. Monthly re-screen (first trading session of each month)
Pull monthly bars (`get_equity_historicals`, interval=month, 12 months) and the official close for
the universe in the latest `data/screens/*.json`, write `data/screens/YYYY-MM-DD.json` in the same
format, then:
```
python3 scripts/screen.py data/screens/YYYY-MM-DD.json --write YYYY-MM-DD
```
and execute it per 4a at the same close.

## 4. Rebalance only if proposed
If `check_drift.py` prints proposals, apply them with
`python3 scripts/apply_trades.py YYYY-MM-DD --yes`, then re-run `record_close.py` for the
same date so history reflects post-trade cash. Respect the IPS frequency limit
(max 4 trades per 5 sessions) — check `portfolio/trades.csv` first.

A **hard stop** (−25% from cost) is proposed as a full sell and is applied like any other proposal.
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
