# Runbook: End-of-day report (~4:15 PM ET, Mon–Fri, after market close)

Read `config.yaml` and today's `journal/YYYY-MM-DD.md` first. All times US/Eastern.

## 0. Guards
- Non-trading day → skip silently (no email), stop.
- If today's journal already contains an "EOD report sent" marker, skip (idempotent —
  prevents duplicates if the Routine and a manual run overlap).

## 1. Compile the report (from the journal + live account data)
Structure:
1. **P&L headline** — realized P&L for the day ($ and % on premium), account value,
   options buying power for tomorrow (note T+1 settlements).
2. **Trades table** — for each position: symbol/strike/expiry, qty, entry time+price,
   exit time+price (and who closed it: agentic/user/stop/TP), P&L, fees.
3. **Monitoring timeline** — condensed: entry checks and outcomes, monitor marks
   (min/max), protective orders placed/filled/cancelled, any gaps or anomalies.
4. **No-trade reasoning** (if applicable) — which gates blocked which candidates.
5. **Market context** — one short paragraph from the pre-market section.
6. **Tomorrow** — buying power after settlement, watchlist carryovers, upcoming
   earnings exclusions.
Cross-check the journal against `get_option_orders` (created_at_gte=today) so the report
reflects actual fills, including any manual trades the user made in the app.

## 2. Send the email
- Via AgentMail: use the existing inbox (create one named for this strategy if none).
- To: the account owner's email (from session context). Subject:
  "Momentum Calls — Daily Report YYYY-MM-DD: {+/-$P&L | NO TRADE}".
- Body: the report, clean HTML or markdown-formatted plain text.

## 3. Record
Append "EOD report sent HH:MM (message id …)" to today's journal, commit
("journal: YYYY-MM-DD EOD report sent"), push.
