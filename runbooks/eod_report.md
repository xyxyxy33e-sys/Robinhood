# Runbook: End-of-day report (~4:15 PM ET, Mon–Fri, after market close)

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` first. All times US/Eastern.

## 0. Guards
- Non-trading day → skip silently (no email), stop.
- If today's journal already contains an "EOD report sent" marker, skip (idempotent —
  prevents duplicates if the Routine and a manual run overlap).

## 1. Compile the report (from the journal + live account data)
Structure:
1. **P&L headline** — realized **paper** P&L for the day ($ and % on premium), **paper
   equity** from the last row of `data/paper_ledger.csv`, and the change since
   `paper_account_starting_balance` ($ and %). Label it unambiguously as a paper/test
   book — a reader skimming on a phone must not mistake it for real money.
   Then, separately and clearly marked as the REAL account: `total_value`, `cash` and
   `buying_power`, noting that the balance is shared with another strategy.
2. **Trades table** — for each position: symbol/strike/expiry, qty, entry time+price,
   exit time+price (and who closed it: agentic/user/stop/TP), P&L, fees.
3. **Monitoring timeline** — condensed: entry checks and outcomes, monitor marks
   (min/max), protective orders placed/filled/cancelled, any gaps or anomalies.
4. **No-trade reasoning** (if applicable) — which gates blocked which candidates.
5. **Market context** — one short paragraph from the pre-market section.
6. **Tomorrow** — paper equity carried forward (this is what sets tomorrow's
   `max_premium_per_trade`), watchlist carryovers, upcoming earnings exclusions.
Cross-check the journal against `get_option_orders` (created_at_gte=today). Under
`dry_run` this must come back **empty** — if it does not, a real order was placed and that
is the headline of the report, above everything else. It also catches any manual trade the
user made in the app. Note the other strategy trades equities in this same account, so
`get_equity_orders` will show its activity — that is expected and is not this strategy's.

## 2. Send the email
- Via AgentMail: use the existing inbox (create one named for this strategy if none).
- To: the account owner's email (from session context). Subject:
  "Momentum Calls — Daily Report YYYY-MM-DD: {+/-$P&L | NO TRADE}".
  While `dry_run` is on, prefix the result with "PAPER " so it reads e.g.
  "… 2026-08-17: PAPER NO TRADE".
- Body: the report, clean HTML or markdown-formatted plain text.

## 3. Record
Append "EOD report sent HH:MM (message id …)" to today's journal, commit
("journal: YYYY-MM-DD EOD report sent"), push.
