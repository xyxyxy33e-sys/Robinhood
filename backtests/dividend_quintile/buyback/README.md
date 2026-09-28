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
