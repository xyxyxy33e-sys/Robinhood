# Final Strategy: 30-Stock Dividend-Yield Barbell

Follow-on research from the quintile backtest (see `README.md`). Starting
from the "second quintile" idea, testing showed the real, robust signal in
this dataset is a **barbell of the highest-yield names against the
lowest/zero-yield names** — not the middle quintile. This document covers
that research path and the resulting concrete portfolio.

## Research path (summary)

1. **Quintile backtest** (`backtest.py`): ranked all S&P 500 names monthly
   by trailing-12-month (TTM) dividend yield into 5 quintiles. The 2nd
   quintile beat SPY over 20 years, but **lagged SPY over the trailing 10
   and 5 years** — the "second quintile beats the market" effect from the
   historical (1930-2023) Hartford Funds/WSJ study did not hold up in more
   recent, growth-dominated windows using today's constituent list.
2. **Barbell test (Q1 + Q5)**: combining the highest-yield quintile and the
   lowest/zero-yield quintile 50/50 beat SPY and Q2 in every window, with a
   better Sharpe ratio than either leg alone in most windows.
3. **Leg-size sweep (20/30/50/100 stocks)**: return and Sharpe generally
   improved with concentration down to 20-30 names, though the exact
   picture changes once quality filters are added (see next point).
4. **Data-integrity finding**: ~99 of 503 S&P 500 names pay **exactly $0**
   in dividends, so "rank by lowest yield" is an unbroken tie among that
   cluster — the specific names selected from it are otherwise arbitrary
   (dependent on sort implementation, not signal). Fixed with a
   deterministic secondary sort inside the zero-yield cluster.
5. **Quality filters added**:
   - High-yield leg: excludes dividend cutters (TTM dividends below TTM
     dividends 12 months prior) and 6-month price crashers (down >25%
     over trailing 6 months) -- both are "yield trap" proxies.
   - Growth leg: zero-yield names tie-broken by a blended percentile rank
     of trailing 12-month AND trailing 1-month momentum (50/50), which
     tempers reliance on any single extreme (e.g., a spinoff-driven price
     distortion) relative to using 12-month momentum alone.
6. **Per-leg breakdown**: isolating each leg showed the high-yield leg is
   already diversified enough at just 10 names (10 vs 25 names performs
   almost identically), while the growth leg's risk-adjusted return
   (Sharpe) is meaningfully better with more names (20-25) than with just
   10 -- arguing for an **asymmetric** barbell rather than equal leg sizes.
7. **Asymmetric sweep**: 10 high-yield + 20 growth (30 names total) had the
   best or tied-best Sharpe ratio across the 5/10/20-year windows of every
   combination tested (10+10, 25+25, 10+25, 10+20).
8. **Sanity check vs. off-the-shelf ETFs**: a 50/50 blend of Vanguard
   Value/Growth ETFs (VTV+VUG) or SPDR Value/Growth ETFs (SPYV+SPYG),
   monthly rebalanced, performs **essentially identically to SPY** in every
   window (CAGR/Sharpe within ~0.3pp). This confirms the barbell's edge is
   not just "value + growth" in disguise -- it comes from (a) selecting the
   *extreme* yield tails rather than a broad half-market style split, (b)
   equal-weighting vs. cap-weighting, and (c) the quality/momentum overlays.

## Backtest results by leg-size combination (Sharpe ratio, all with quality filters)

| Window | 20 (10+10) | 50 (25+25) | 35 (10 HY+25 gr) | **30 (10 HY+20 gr)** |
|---|---:|---:|---:|---:|
| 5y  | 1.41 | 1.38 | 1.36 | **1.44** |
| 10y | 1.27 | 1.27 | 1.35 | **1.38** |
| 20y | 1.17 | 1.20 | 1.21 | **1.21** |

**Caveat**: this is the result of a fairly extensive leg-size/weighting
search over the same 20-year sample. Treat "roughly 10 high-yield + 20-25
growth, equal-weighted" as the robust conclusion, not "exactly 20 growth
names" as a precisely optimal number -- the margins between nearby
configurations (e.g. 30 vs 35) are well within backtest noise.

## The strategy

- **High-Yield leg (10 names)**: top-10 TTM dividend yield among S&P 500
  names, excluding dividend cutters and 6-month crashers.
- **Growth leg (20 names)**: 20 zero/near-zero-yield names, ranked by a
  blended 12-month + 1-month price momentum percentile.
- **Weighting**: pooled equal-weight, ~3.33% per name (33% aggregate to
  the HY leg, 67% to the growth leg).
- **Rebalance**: monthly.
- **Returns**: total return via adjusted close (dividends reinvested).

Regenerate the current holdings list any time with:
```
python3 barbell_30.py
```

## Holdings as of 2026-09-21

**High-Yield leg (10)**

| Ticker | TTM Yield |
|---|---:|
| VICI | 7.53% |
| HST | 7.49% |
| UPS | 6.92% |
| GIS | 6.89% |
| KHC | 6.57% |
| PGR | 6.55% |
| EIX | 6.30% |
| MO | 6.26% |
| PFE | 6.20% |
| AMCR | 6.17% |

**Growth leg (20)**

| Ticker | 12mo Return | 1mo Return |
|---|---:|---:|
| MRNA | 579.5% | 29.7% |
| INTC | 298.4% | 32.2% |
| BE | 237.0% | 34.8% |
| AMD | 289.8% | 31.1% |
| SNDK | 1686.8% | 10.4% |
| CRWD | 98.4% | 31.0% |
| FTNT | 116.4% | 16.2% |
| COHR | 197.6% | 10.9% |
| LITE | 456.6% | 8.6% |
| ILMN | 131.8% | 12.0% |
| KEYS | 93.0% | 8.1% |
| WBD | 64.7% | 9.1% |
| PANW | 80.7% | 6.4% |
| DDOG | 79.1% | 5.4% |
| AKAM | 52.3% | 6.6% |
| ANET | 40.1% | 11.8% |
| FFIV | 35.7% | 19.1% |
| IQV | 41.9% | 5.4% |
| CNC | 102.0% | 1.3% |
| ECHO | 33.9% | 9.7% |

## Known limitations / before deploying real money

1. **Survivorship bias**: universe is today's S&P 500 members applied
   retroactively; delisted/removed constituents are excluded from the
   whole backtest history.
2. **Sector concentration**: the growth leg is heavily weighted toward
   semiconductors/tech-hardware and biotech/healthcare -- the momentum
   ranking doesn't control for sector diversification at all. A sector cap
   (e.g., max 3-4 names per GICS sector) would be a reasonable addition.
3. **Extreme momentum outliers**: a few growth-leg names (SNDK's 1687%
   12-month return in particular) are large enough that they may reflect a
   corporate action (e.g., a 2025 spinoff) rather than organic price
   appreciation. Worth manually verifying before trading.
4. **No fundamental quality screen**: no payout-ratio, profitability, or
   leverage filter is applied (would require a separate fundamentals data
   source; not currently in this backtest).
5. **No transaction costs, taxes, or slippage** are modeled. Monthly
   rebalancing of a momentum-driven growth leg implies real turnover and
   tax drag (short-term gains) that would meaningfully cut into the
   backtested returns above in a taxable account.
6. **Backtested Sharpe ratios (1.2-1.4) and CAGRs (20%+) are far above
   what should be expected going forward** -- this sample backtest spans
   the entire 2005-2026 mega-cap tech bull run; equal-weight + momentum +
   concentrated-tail selection strategies are well-documented for
   historically inflating backtest performance relative to realistic
   forward expectations.
