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

**Marker check (§0) must match the whole line, not a substring.** Use `grep -cx` (or an
exact-line comparison), never a bare `grep -c`. The phrase appears in ordinary prose
whenever a journal *discusses* the guard, and that has produced a false positive twice:
on 8/19 the phrase appeared while explaining the marker had been deliberately WITHHELD
after a failed send — a naive count would have suppressed a report that never went out —
and again on 8/21 when the guard's own audit note created a second match.

## 4. Keep the corpus current (do this BEFORE §5)
For every symbol evaluated today (the distinct `symbol` values in today's `data/leg_log.csv`
rows), pull RTH 5-minute bars and write `data/bars/YYYY-MM-DD_SYM.csv` with header
`t,o,h,l,c,v` where `t` is UTC `HHMM`:

```
get_equity_historicals(symbols=[…], interval='5minute',
                       start_time='YYYY-MM-DDT13:30:00Z', end_time='YYYY-MM-DDT20:00:00Z')
```

Large responses persist to a file rather than returning inline — read that file with `jq`
or python rather than pulling it into context. Then append today's rows to
`data/bars/manifest.csv` (`file,prior_close,is_call,direction`); `prior_close` is the
previous session's daily close (`interval='day'`).

This step exists because through 8/21 the backtest corpus held 9 name-days from 7/23–8/14
while the strategy had evaluated 31 more live and added none of them. The harness was
starved of exactly the data the strategy was generating.

## 5. Maintain the evidence base
```
python3 tools/backfill_outcomes.py      # fills outcome_30m / outcome_eod, idempotent
python3 tools/backtest_legs.py          # leg-rule fires + forward returns
python3 tools/backtest_legs.py --audit  # guard block accounting — run this FIRST
python3 tools/backtest_legs.py --pnl    # modelled P&L through the real exit cascade
```
`backtest_legs.py` now imports the rule from `tools/eval_entry.py` instead of carrying its
own copy. It used to carry a copy, the two drifted, and for a week the reports quoted
**−6.9% / 4-in-23** for a rule the strategy does not actually run. Never reimplement the
rule in the harness; import it.

Report, every day, until each stops being true:

1. **`--audit` result.** As of 2026-08-28 the chase guard blocks **25 of 25** qualifying
   bars across the 58 name-day corpus, i.e. the strategy has produced **zero executable
   entries, ever**. The guard and the `seq` session-extreme condition are mutually
   exclusive by construction. Report the live no-trade streak as *this*, not as a quiet
   tape, for as long as `--audit` says 100%.
2. **`--pnl` at the live `late_entry_min_volume_ratio`.** With the guard on there are no
   trades to price. With the guard off it is **+0.01% forward-60 (6 wins in 14) and −4.7%
   modelled after friction**. State that removing the guard would not release an edge.
