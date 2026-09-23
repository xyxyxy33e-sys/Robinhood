# S&P 500 Dividend-Yield "Second Quintile" Backtest

Tests the idea (popularized by a Hartford Funds/WSJ study) that the
**second-highest quintile of dividend yielders** outperforms both the
market and the highest-yield ("dividend trap") names.

## Methodology

- **Universe**: current S&P 500 constituents (503 tickers, pulled from
  Wikipedia) plus SPY as the benchmark. This is a static, present-day
  list applied retroactively, so results carry **survivorship bias** —
  names that were dropped from the index (bankruptcies, etc.) are not
  included.
- **Data**: daily close, adjusted close, and dividends per share for
  each ticker, 2005-09 to 2026-09, via Yahoo Finance (`yfinance`).
- **Ranking signal**: trailing-twelve-month (TTM) dividend yield =
  (sum of per-share dividends paid in the prior 365 days) / (month-end
  close price).
- **Rebalance**: monthly, on the last trading day of each month.
  - Rank all names with a valid TTM yield.
  - Split into 5 equal-sized quintiles by yield rank (Q1 = highest
    yield 20%, Q5 = lowest/zero-yield 20%).
  - Hold each quintile **equal-weighted**.
- **Returns**: computed from *adjusted* close (Yahoo's adjustment
  reinvests dividends and adjusts for splits), so monthly returns are
  total returns with dividends reinvested.
- **Backtest window**: 2005-10-31 through 2026-08-31 (~20.9 years).

Scripts:
- `download_data.py` – pulls the S&P 500 list + 20y of price/dividend
  history and caches it to `sp500_data.parquet` (not committed — regenerate
  by running the script; takes ~10-15 min).
- `backtest.py` – builds the monthly quintile portfolios and computes
  performance stats, writing `cumulative_returns.csv` and `summary.csv`.
- `make_chart.py` – renders `backtest_chart.png`.

## Results (20.9 years, monthly rebalance, dividends reinvested)

| Strategy | Total Return | CAGR | Ann. Vol | Sharpe | Max Drawdown | $1,000 → |
|---|---:|---:|---:|---:|---:|---:|
| Quintile 1 (highest yield) | 1,928.7% | 15.48% | 18.14% | 0.89 | -53.7% | $20,287 |
| **Quintile 2 (2nd highest yield)** | **1,138.1%** | **12.78%** | **15.31%** | **0.87** | **-43.6%** | **$12,381** |
| Quintile 3 | 1,138.1% | 12.84% | 16.14% | 0.83 | -45.5% | $12,381 |
| Quintile 4 | 1,727.3% | 14.90% | 17.16% | 0.90 | -46.2% | $18,273 |
| Quintile 5 (lowest/zero yield) | 6,601.0% | 22.46% | 20.16% | 1.11 | -48.7% | $67,010 |
| **SPY (S&P 500)** | **812.7%** | **11.15%** | **15.02%** | **0.78** | **-50.8%** | **$9,127** |

## Takeaways

- The Second Quintile **beat the S&P 500**: 12.78% vs 11.15% CAGR, with
  *lower* volatility and a *better* max drawdown (-43.6% vs -50.8%) — a
  better Sharpe ratio too (0.87 vs 0.78). That's directionally consistent
  with the Hartford Funds/WSJ finding, though the magnitude is much
  smaller here (this is 20 years on today's constituent list, not 93
  years on the full historical universe).
- Unlike the original 1930–2023 study, **Quintile 5 (near-zero-yield
  growth stocks) was the top performer** over this specific 2005–2026
  window — dominated by mega-cap tech (Apple, Amazon, Nvidia, Google,
  Meta, etc., many of which paid no dividend for much of the period).
  This is a strong reminder that 2005–2026 was an unusually good stretch
  for non-dividend-paying growth stocks, and that survivorship bias
  (using today's index membership) further inflates this effect, since
  those exact winners are guaranteed to be in the universe.
- Quintile 1 (highest yield — often "yield trap" stocks near financial
  distress) also outperformed SPY here, but with the worst drawdown of
  any bucket (-53.7%), consistent with the idea that ultra-high yield
  often prices in elevated risk.

## Caveats

- **Survivorship bias**: only today's S&P 500 members are included, so
  historical constituents that were removed (e.g., delisted, acquired,
  bankrupt) are excluded. Real point-in-time index membership would
  likely show weaker results for all buckets, especially Quintile 1.
- **Dividend data quality**: TTM dividends are computed from Yahoo
  Finance's dividend history, which can occasionally miss or misdate
  special dividends.
- **Equal weighting, monthly turnover, and no transaction costs/taxes**
  are assumed — a real implementation would have trading costs and
  tax drag from monthly reinvestment/rebalancing.
