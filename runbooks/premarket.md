# Runbook: Pre-market news & candidates (~8:00 AM ET, Mon–Fri)

Read `config.yaml` first. All times US/Eastern.

## 0. Guards
- Confirm today is a US equity trading day (WebSearch "is the US stock market open today"
  if in doubt — holidays/half-days). If closed: append a one-line journal note, push, stop.
- If fired before 7:00 ET or after 9:15 ET (DST drift), still run — this phase is research-only.

## 1. Gather news (no trading in this phase)
0. **Set today's `daily_start_balance` from the PAPER LEDGER, not the broker.**
   Read the last row of `data/paper_ledger.csv`; its `paper_equity` is today's
   `daily_start_balance`. Compute `max_premium_per_trade` = `daily_start_balance ×
   max_premium_per_trade_pct_of_daily_start / 100`, rounded to the cent. Journal both —
   entry.md reads the computed dollar figure rather than recomputing it mid-day.
   - **Why not `get_portfolio`:** this account is **shared with another strategy** whose
     equity sits inside `total_value`. Sizing off it would let that strategy's P&L move
     this one's position sizes and make the two books inseparable. The paper book runs on
     `paper_account_starting_balance` plus its own realized P&L, and nothing else.
   - **Still call `get_portfolio`, for the record only.** Journal `total_value`, `cash` and
     `buying_power.buying_power` alongside the paper figure, clearly labelled as the real
     account. Two purposes: confirming no real order was placed, and recording how far
     paper equity has drifted from what the account could actually have funded. Never feed
     these into sizing.
   - If the ledger is missing or unreadable, fall back to `paper_account_starting_balance`
     and say so in the journal — never silently substitute a broker number.
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
direction (call/put), catalyst (one line), prior close, pre-market price, ATM OI/spread
(from the pre-screen below), and a "disqualify if" condition for the entry check.
Explicitly list names REJECTED for earnings-before-expiry or binary-event risk.

**Options-chain pre-screen (added 2026-07-24):** for each ranked candidate, pull the
likely trade contract's quote — `get_option_chains` → expiration per the entry rules
([dte_min, dte_max], or nearest monthly to dte_max_no_weekly) → `get_option_instruments`
at the strike nearest the pre-market price → `get_option_quotes` — and record open
interest + spread in the candidate table. **OI is an end-of-day figure; it will not
change during the session**, so this pre-market reading is authoritative all day: a name
whose ATM and first step-out strikes both sit far below `min_open_interest` cannot pass
the entry liquidity gate today no matter what its tape does. Flag those names
"chain dead" and rank them below every candidate with a live chain (or reject outright
when no plausible strike clears) — don't spend entry-window cycles discovering
illiquidity the pre-screen already proved. Spreads DO move intraday, so a name failing
only on spread is not dead — note it as "spread-watch" instead. (Motivated 2026-07-24:
all five tape qualifiers failed entry on OI that was knowable at 8 AM.)

## 3. Journal & handoff
- Create `journal/YYYY-MM-DD.md` from `journal/TEMPLATE.md`; fill the **Pre-market** section
  with the news digest and ranked candidates.
- Commit ("journal: YYYY-MM-DD premarket") and push to the working branch
  (`git push -u origin <branch>`, retry with backoff per repo instructions).
- Do not place, review, or cancel any order in this phase.
