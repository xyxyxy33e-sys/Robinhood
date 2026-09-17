# January 2027 rebalance — checklist

**User's decision (as of Sept 2026):** do a FULL swap in January — fully
refresh both sleeves to the new annual lists (not a partial/selective
rebalance like the Sept 2026 mid-year swaps) — and keep the portfolio
structured as a 50/50 split between the Dogs of the Dow sleeve and the SA
Top 10 sleeve going forward. Rationale: the two sleeves showed genuine
offsetting behavior for the first time in the 7/15/2026-9/17/2026 window
(Dogs of the Dow +4.0% vs SPY +1.0%, while the SA H2 2026 basket was
-13.3% over the identical window) — the first real evidence that Dogs'
defensive/value tilt and SA's growth/momentum tilt diversify each other
during a growth-stock pullback, rather than just being two flavors of the
same bull-market bet (which is what 2023-2025 looked like, since both
sleeves moved up together every year with no offsetting behavior).

User's 20-position portfolio (see `portfolio_tracker.csv`) is due for review
when both source strategies refresh in January 2027:

1. **Dogs of the Dow 2027** — new annual list drops based on Dec 31, 2026
   dividend yields. Recompute with `compute_dogs.py` (update
   `djia_constituents.py` first if any Dow index changes happened in 2026 —
   check for a repeat of the mid-2026 VZ→GOOGL-style swap). Compare new list
   against the 8 Dogs names currently held (CVX, MRK, KO, JNJ, VZ, AMGN, PG,
   HD — UNH was exited in Sept 2026) and flag which survive the refresh vs.
   drop out.

2. **Seeking Alpha Top 10 for 2027** — new annual pick list (their branded
   January event). Get the confirmed 10 tickers from the user (paywalled,
   can't scrape) and compare against the current SA sleeve (MU, AMD, ALL,
   INCY, ABX, CLS, TTMI, SNDK, AMZN, VICR, STRL, DAVE — 12 names after the
   Sept 2026 WLDN/B/NKE/UNH/COHR/CIEN swaps).

3. **Standing conclusion from the full 2015-2026 backtest** (see
   `README.md`): Dogs of the Dow underperformed SPY on both CAGR and Sharpe
   over the long run. Don't recommend mechanically re-committing to a full
   10-name annual reset without re-checking whether that conclusion still
   holds — re-run `run_backtest.py` with the closed-out 2026 data point
   added before advising.

4. **Re-run the random-momentum baseline** (`random_momentum_baseline.py`)
   with the 2027 SA rebalance date added, to keep checking whether SA's
   picks are beating generic momentum exposure or just riding it.

5. Update `portfolio_tracker.csv` with realized entry/exit prices for
   whatever actually gets swapped, same format as the Sept 2026 rounds.
