"""
Final recommended construction from this research: a 30-name yield barbell.

  - 10 "High-Yield" leg: top-10 TTM dividend yield among S&P 500 names,
    EXCLUDING dividend cutters (TTM dividends below TTM dividends 12 months
    ago) and 6-month price crashers (down >25% over trailing 6 months) --
    both proxies for "yield trap" risk.
  - 20 "Growth" leg: the 20 zero/near-zero-yield names, tie-broken by a
    blended percentile rank of trailing 12-month AND trailing 1-month price
    momentum (50/50), since ~100 of 503 S&P 500 names pay literally zero
    dividend and are tied -- an unbroken tie makes "lowest yield" selection
    arbitrary and irreproducible. The momentum tie-break makes the choice
    among that zero-yield cluster deterministic and economically motivated,
    while blending two horizons (not just trailing-12mo alone) tempers the
    influence of any single-stock, single-period outlier move (e.g., a
    spinoff-driven price distortion).

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

    # --- Growth leg ---
    lo = row.copy()
    tie = pd.DataFrame({
        "yld": lo,
        "mom12": mom12.loc[dt].reindex(lo.index),
        "mom1m": mom1m.loc[dt].reindex(lo.index),
    }).dropna(subset=["mom12", "mom1m"])
    tie["r12"] = tie["mom12"].rank(pct=True)
    tie["r1m"] = tie["mom1m"].rank(pct=True)
    tie["combo"] = 0.5 * tie["r12"] + 0.5 * tie["r1m"]
    tie = tie.sort_values(["yld", "combo"], ascending=[True, False])
    growth_leg = tie.head(GROWTH_N)

    return dt, hy_leg, growth_leg


if __name__ == "__main__":
    dt, hy_leg, growth_leg = build_current_portfolio()
    print(f"As-of date: {dt.date()}\n")
    print(f"=== HIGH-YIELD LEG ({HY_N}) ===")
    for t, y in hy_leg.items():
        print(f"{t:6s} TTM yield: {y*100:.2f}%")
    print(f"\n=== GROWTH LEG ({GROWTH_N}) ===")
    for t, r in growth_leg.iterrows():
        print(f"{t:6s} 12mo return: {r.mom12*100:6.1f}%   1mo return: {r.mom1m*100:5.1f}%")
