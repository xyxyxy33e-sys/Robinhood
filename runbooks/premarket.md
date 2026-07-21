# Runbook: Pre-market news & candidates (~8:00 AM ET, Mon–Fri)

Read `config.yaml` first. All times US/Eastern.

## 0. Guards
- Confirm today is a US equity trading day (WebSearch "is the US stock market open today"
  if in doubt — holidays/half-days). If closed: append a one-line journal note, push, stop.
- If fired before 7:00 ET or after 9:15 ET (DST drift), still run — this phase is research-only.

## 1. Gather news (no trading in this phase)
1. WebSearch: overnight market summary — S&P/Nasdaq futures, any macro data due today
   (CPI, Fed, jobs), and the general risk tone.
2. `get_earnings_calendar` (start_date=today, days=2, filter=high_market_cap): who reports
   today pre-open / after close, and tomorrow. Earnings names are **excluded** as entries
   but explain sector moves.
3. WebSearch: "biggest stock movers premarket today" + "stock upgrades downgrades today".
   Collect names with fresh catalysts in **both directions**: earnings beat + raise,
   guidance raises, upgrades, product/regulatory news, large contracts (bullish); and
   earnings miss + cut, guidance cuts, downgrades, negative regulatory/legal news, guidance
   withdrawals (bearish) — only if `enable_puts` is true.
4. `run_scan` on `scan_id` (calls) and, if `enable_puts`, `scan_id_puts` (puts) — pre-market
   results are limited (the % change filter needs live session data) but note any carryover
   names with RSI/volume still hot in either direction.
5. `get_equity_quotes` on the 8–15 most interesting catalyst names across both directions:
   confirm real pre-market strength (or weakness), note prior close and key levels.

## 2. Build the candidate list
Rank the **top 10** candidates, calls and puts together on one list, by: catalyst
strength > liquidity (stock + options) > cleanliness of the setup. For each: symbol,
direction (call/put), catalyst (one line), prior close, pre-market price, and a
"disqualify if" condition for the entry check. Explicitly list names REJECTED for
earnings-before-expiry or binary-event risk.

## 3. Journal & handoff
- Create `journal/YYYY-MM-DD.md` from `journal/TEMPLATE.md`; fill the **Pre-market** section
  with the news digest and ranked candidates.
- Commit ("journal: YYYY-MM-DD premarket") and push to the working branch
  (`git push -u origin <branch>`, retry with backoff per repo instructions).
- Do not place, review, or cancel any order in this phase.
