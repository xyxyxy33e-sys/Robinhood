# Backtest: Dogs of the Dow vs Seeking Alpha Top 10 vs SPY

Compares two well-known "top picks" strategies against a SPY buy-and-hold
benchmark, using daily adjusted-close data from Yahoo Finance (`yfinance`).

## Strategies

**Dogs of the Dow** (2015 – present, annual rebalance on ~Jan 2)
The 10 highest-dividend-yield stocks in the Dow Jones Industrial Average,
selected as of the prior year-end close. Rather than scraping a
paywalled/CAPTCHA-gated list site, the list is *computed directly* from data:
- `djia_constituents.py` reconstructs Dow-30 membership at each year-end from
  the documented history of index changes (additions/removals with dates).
- `compute_dogs.py` pulls trailing-12-month dividends and year-end close
  price for each member and ranks by trailing yield, producing
  `dogs_of_the_dow.json`.

This was cross-checked against independent secondary sources (CNBC, Fool,
Nasdaq, dividendpower.org, Kiplinger) for each year 2015–2026 and matches
in the large majority of names each year; a small number of borderline
10th-place names can differ by methodology (trailing paid dividends vs.
announced forward rate), which is a known, disclosed source of noise for
this strategy.

**Seeking Alpha Top 10** (2023 – present, annual rebalance each January)
Steven Cress / Seeking Alpha Quant team's "Top Stocks for `<year>`" picks,
in `seeking_alpha_top10.json`.

Important data limitation: Seeking Alpha's branded "Top Stocks" event
appears to have started around 2022, and full, reliably-corroborated
10-ticker rosters (2+ independent sources) could only be confirmed for
**January 2023, 2024, 2025, and 2026**. The semi-annual "H2" mid-year
refresh mentioned in the prompt exists as an event from ~H2 2023 onward,
but its article is paywalled on seekingalpha.com and no complete ticker
list could be independently verified for any H2 period, so **this backtest
only reflects the annual January releases, not the semi-annual cadence**.
If you have access to the original SA articles (or an SA subscription),
supply the exact ticker lists and I'll extend `seeking_alpha_top10.json`
and rerun.

**SPY** buy-and-hold, shown both over the full 2015–present window and
re-based to match each strategy's own start date for a fair side-by-side
comparison.

## Methodology

- Equal-weight basket, reset to 1/N at each rebalance date.
- Prices are `auto_adjust=True` (split- and dividend-adjusted), so dividend
  income is included in returns.
- Delisted/no-data tickers (e.g. VRNA, acquired by Merck in 2025) are
  dropped from that period's basket and the remaining names re-weighted.

## Results (as of 2026-09-17)

| strategy                | start      | end        | total return % | CAGR % | ann. vol % | Sharpe | max drawdown % |
|:------------------------|:-----------|:-----------|----------------:|-------:|-----------:|-------:|----------------:|
| Dogs of the Dow          | 2015-01-02 | 2026-09-17 | 270.93 | 11.85 | 16.01 | 0.78 | -35.21 |
| SPY (Dogs period)        | 2015-01-02 | 2026-09-17 | 348.52 | 13.68 | 17.55 | 0.82 | -33.72 |
| Seeking Alpha Top 10     | 2023-01-03 | 2026-09-17 | 817.63 | 81.92 | 37.03 | 1.81 | -33.92 |
| SPY (SA period)          | 2023-01-03 | 2026-09-17 | 109.01 | 22.02 | 14.97 | 1.41 | -18.76 |
| SPY (full 2015-present)  | 2015-01-02 | 2026-09-17 | 348.52 | 13.68 | 17.55 | 0.82 | -33.72 |

**Dogs of the Dow underperformed SPY** on both total return and
risk-adjusted (Sharpe) basis over 2015–2026 — consistent with a lot of
recent academic/practitioner research showing the strategy has lagged the
S&P 500 in the post-2015 era, largely because it's overweight energy,
telecom and legacy pharma/industrials that lagged mega-cap tech.

**Seeking Alpha Top 10 dramatically outperformed SPY** since 2023, driven
heavily by SMCI (+239% in 2023) and MOD (+197% in 2023) in the first
cohort, and continued strength from AI/semiconductor names (APP, CLS, MU,
AMD) in later cohorts. Note the much higher volatility (37% vs 15%
annualized) and only 4 rebalance points (~3.7 years) — this is a small,
concentrated, short sample and should not be read as a durable edge.

## Running it

```
pip install -r requirements.txt
python3 run_backtest.py
```

Outputs `nav.csv` (daily NAV series), `chart.png` (equity curves), and
`report.md` (stats table). Price data is cached per-ticker in `data/`.
