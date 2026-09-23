"""
Final recommended construction from this research: a 30-name yield barbell.

  - 10 "High-Yield" leg: top-10 TTM dividend yield among S&P 500 names,
    EXCLUDING dividend cutters (TTM dividends below TTM dividends 12 months
    ago) and 6-month price crashers (down >25% over trailing 6 months) --
    both proxies for "yield trap" risk.
  - 20 "Growth" leg: Dual Momentum selection among the zero/near-zero-yield
    names. Absolute momentum filter: only names with POSITIVE trailing
    12-month price return qualify. Relative momentum: rank qualifying names
    by trailing 12-month return, take the top 20. (Superseded an earlier
    version that tie-broke the zero-yield cluster by blended 12mo+1mo
    momentum with no positive-return requirement -- backtesting showed the
    absolute-momentum filter meaningfully improves drawdown, since it lets
    the growth leg naturally shrink/de-risk in downturns instead of always
    forcing 20 holdings, including "least-bad" negative-momentum names,
    during broad selloffs.)

Rebalanced monthly, dividends reinvested via adjusted-close total returns,
pooled equal-weight across all 30 names (~3.33% each).

See README.md for full methodology, backtest results across 5/10/20-year
windows, and the comparison against a naive 50/50 Value+Growth ETF blend
(VTV+VUG), which performs essentially identically to SPY and does NOT
reproduce this strategy's historical edge.
"""
import numpy as np
import pandas as pd
from backtest import load_data, ttm_dividends

HY_N = 10
GROWTH_N = 20


def build_current_portfolio():
    close, adj, div, spy_adj = load_data()

    # use the most recent trading day with near-complete data coverage,
    # since a same-day pull can have a partial/incomplete final row
    counts = close.notna().sum(axis=1)
    dt = counts[counts > 480].index.max()

    px = close
    mom6 = px.pct_change(126)
    mom12 = px.pct_change(252)
    mom1m = px.pct_change(21)
    ttm = div.fillna(0.0).rolling("365D").sum()
    ttm_prior = ttm.shift(252)

    row = (ttm.loc[dt] / px.loc[dt]).replace([np.inf, -np.inf], np.nan).dropna()
    px_ok = px.loc[dt, row.index].notna()
    row = row[px_ok]

    # --- High-Yield leg ---
    hy = row.copy()
    prior = ttm_prior.loc[dt]
    cur = ttm.loc[dt]
    cut = (cur < prior) & prior.notna() & (prior > 0)
    hy = hy.drop(index=[t for t in cut[cut].index if t in hy.index])
    m6 = mom6.loc[dt]
    crashed = m6[m6 < -0.25].index
    hy = hy.drop(index=[t for t in crashed if t in hy.index])
    hy_leg = hy.sort_values(ascending=False).head(HY_N)

    # --- Growth leg: Dual Momentum ---
    zero_yield = row[row <= 1e-9].index
    m12 = mom12.loc[dt].reindex(zero_yield).dropna()
    qualifying = m12[m12 > 0]  # absolute momentum filter
    growth_leg = qualifying.sort_values(ascending=False).head(GROWTH_N)  # relative momentum

    return dt, hy_leg, growth_leg


if __name__ == "__main__":
    dt, hy_leg, growth_leg = build_current_portfolio()
    print(f"As-of date: {dt.date()}\n")
    print(f"=== HIGH-YIELD LEG ({HY_N}) ===")
    for t, y in hy_leg.items():
        print(f"{t:6s} TTM yield: {y*100:.2f}%")
    print(f"\n=== GROWTH LEG ({GROWTH_N}, Dual Momentum) ===")
    for t, r in growth_leg.items():
        print(f"{t:6s} 12mo return: {r*100:6.1f}%")
