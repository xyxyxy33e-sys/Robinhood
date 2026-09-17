# January 2027 rebalance — checklist

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
