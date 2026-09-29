# Buyback exploration (S&P 500)

Scripts run from this folder after copying `../backtest.py`, and the cached price data from `../download_data.py`, alongside them; `market_caps.json` comes from a fast_info market-cap pull (see the dual-momentum work).

- `fetch_buybacks.py` -- TTM repurchases from Yahoo quarterly cash flow (only ~5 quarters of history, so snapshot only). Output: `buyback_snapshot.csv` (net buyback yield = (repurchases - issuance) / market cap).
- `fetch_shares.py` -- share-count history (`get_shares_full`); starts ~Nov 2015 for most names, so backtests cover ~10 years, not 20.
- `buyback_bt.py` -- monthly-rebalance, equal-weight tests of top-N net share shrinkage and top-N shareholder yield (dividend + buyback).
- `barbell_bb.py` -- adds the buyback signal to the barbell's high-yield leg.

## Results (10y, Sharpe / max DD; SPY 1.02 / -23.9%)
| Strategy | 5y CAGR | 10y CAGR | 10y Sharpe | 10y Max DD |
|---|---:|---:|---:|---:|
| Net buyback top 20 | 20.8% | 19.0% | 1.06 | -27.6% |
| Net buyback top 30 | 23.7% | 17.9% | 1.04 | -33.4% |
| Shareholder yield top 20 | 20.1% | 21.2% | 1.02 | -30.6% |
| Barbell v2 (baseline) | 35.2% | 32.2% | 1.38 | -24.0% |
| Barbell + no-dilution filter on HY leg | 35.5% | 27.8% | 1.26 | -24.9% |
| Barbell + HY leg ranked by div+buyback | 34.1% | 32.6% | 1.38 | -31.3% |

Conclusion: buyback screens beat SPY on return but not meaningfully on risk-adjusted terms over 10y, and adding them to the barbell did not improve it. Caveats: share counts are noisy (splits, M&A; changes over 30% are dropped), survivorship bias, no costs.

## Buyback dollars / market cap ranking (`buyback_amt_bt.py`)
Signal: latest annual repurchases (120-day filing lag) / point-in-time market cap (price x share count); needs `buybacks.json` from `fetch_buybacks.py`. Yahoo only has ~5 fiscal years of cash flow, so signals start in 2023 and the common window is Apr 2023 - Aug 2026 (~3.3 years, one bull market, no bear market).

| Strategy | CAGR | Vol | Sharpe | Max DD |
|---|---:|---:|---:|---:|
| Buyback $/mktcap gross top 30 | 29.9% | 14.1% | 1.94 | -5.8% |
| Buyback $/mktcap net top 30 | 30.7% | 14.3% | 1.97 | -5.6% |
| Buyback $/mktcap gross top 50 | 30.5% | 13.9% | 2.00 | -6.6% |
| Share-shrink top 30 (same window) | 31.3% | 13.7% | 2.08 | -5.4% |
| Barbell v2 | 53.1% | 23.9% | 1.92 | -13.5% |
| SPY | 22.2% | 12.7% | 1.65 | -8.3% |

Too short a window to draw conclusions; the dollar-based and share-count-based rankings behave almost the same.
