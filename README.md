# Robinhood — SPY level-reversal scalper

A rules-based version of a popular "wait for the level" SPY options scalp:

| Rule | Implementation |
|---|---|
| 0DTE first 2 hours, 3DTE last 3 hours | Entries 09:31–11:30 ET use same-day expiry. Entries 13:00–15:45 ET use the first expiry ≥ 3 calendar days out. No trades over lunch. Everything is flat by 15:55. |
| Key levels marked before the open | Prior-day high/low/close, premarket high/low, 5-day high/low, $5 round numbers within 1.5%, plus optional manual levels. Levels within $0.25 of each other are merged. Nothing after 09:30 is used. |
| Wait for price to come to the level | A 1-minute bar has to arrive from the far side and trade within $0.10 of the level without piercing it by more than $0.35. |
| Enter the reversal at the level | Within 3 bars, a bar must close ≥ $0.05 back on the arrival side, in the reversal direction (green off support, red off resistance). Then buy the ATM call (support) or put (resistance). Each level is traded at most once per day. |
| Take $0.30–$0.60, out in minutes | Target +$0.40, stop −$0.30, exit if the level breaks, 12-minute time stop. |
| Nothing reaches my levels? No trade. | No touch, no trade. Risk limits: max 5 trades, 2 losers, or $150 loss per day. |

All parameters live in `scalper/config.py`.

## Paper test run (no orders are ever sent)

```bash
pip install -r requirements.txt
python -m scalper.paper                  # start any time before 09:29 ET; runs until 16:00 ET
python -m scalper.paper --levels 760 772.5   # add your own levels
```

At 09:29:30 ET the runner marks levels. It then processes each closed 1-minute SPY bar. Entries use the real listed expiry and the implied vol from the live chain, and positions are marked with Black-Scholes on the live SPY price. For each fill, the real bid/ask is logged next to the simulated price so you can check how realistic the fills were. Output: `logs/paper-YYYY-MM-DD.log` and `.json`.

## Backtest

```bash
python -m scalper.backtest --days 6 -v
```

Free 1-minute options history doesn't exist, so the backtest prices options with Black-Scholes at a fixed IV. Use it to check that the rules behave as intended, not as a P&L forecast.

**Result on the 6 sessions from Sep 23–30, 2026 (1 contract):** 17 trades, 41% winners, about −$100. A grid over target, stop, and pierce settings came out negative in every combination. On this sample, the edge in the original post doesn't show up mechanically. Paper-trade it before risking money.

## Tests

```bash
python -m pytest -q
```
