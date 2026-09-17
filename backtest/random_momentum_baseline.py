"""Baseline: random 10-stock baskets drawn from the top-momentum decile of
the S&P 500, rebalanced on the same dates as the Seeking Alpha Top 10
backtest. Used to check whether SA's outperformance is genuine stock-picking
skill or just exposure to a "buy recent winners" (momentum) factor that a
random draw from the same pool would have captured anyway.

Methodology per rebalance date:
  1. Universe = current S&P 500 members with a full 12-month price history.
  2. Rank by trailing 12-month total return as of the day before rebalance.
  3. Momentum pool = top 20% (~100 names) by that ranking.
  4. Run N_SIMS independent simulations; each simulation draws 10 tickers at
     random (without replacement) from the pool at EVERY rebalance date
     independently, forming an equal-weight, annually-rebalanced basket for
     the full period -- same engine as the SA Top 10 / Dogs backtests.
Reports the distribution (mean/median/percentiles) of CAGR & total return
across simulations, and where the actual SA Top 10 result falls in it.
"""
from __future__ import annotations

import json
import random

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data import get_prices
from engine import backtest_rebalanced_portfolio, perf_stats

N_SIMS = 300
POOL_FRACTION = 0.20
SEED = 42

REBALANCE_DATES = ["2023-01-01", "2024-01-01", "2025-01-01", "2026-01-01"]
END = "2026-09-17"


def load_universe_prices() -> pd.DataFrame:
    """Requires sp500_close.csv; run `python3 fetch_sp500_universe.py` first."""
    df = pd.read_csv("sp500_close.csv", index_col=0, parse_dates=True)
    return df


def momentum_pool(prices: pd.DataFrame, asof: pd.Timestamp, lookback_days: int = 365) -> list[str]:
    """Top-quintile tickers by trailing ~12mo return as of `asof`."""
    window = prices.loc[(prices.index >= asof - pd.Timedelta(days=lookback_days + 10)) & (prices.index <= asof)]
    window = window.dropna(axis=1, thresh=int(len(window) * 0.9))
    if window.shape[0] < 200:
        raise ValueError(f"insufficient history as of {asof}")
    start_px = window.iloc[0]
    end_px = window.iloc[-1]
    ret = (end_px / start_px - 1).dropna()
    ret = ret.drop(labels=[c for c in ("SPY",) if c in ret.index], errors="ignore")
    n_pool = max(10, int(len(ret) * POOL_FRACTION))
    pool = ret.sort_values(ascending=False).head(n_pool).index.tolist()
    return pool


def main():
    prices = load_universe_prices()
    prices = prices.loc[prices.index <= END]

    pools = {}
    for d in REBALANCE_DATES:
        asof = pd.Timestamp(d) - pd.Timedelta(days=1)
        pools[d] = momentum_pool(prices, asof)
        print(f"{d}: momentum pool size={len(pools[d])}, top5={pools[d][:5]}")

    rng = random.Random(SEED)
    sim_stats = []
    for sim in range(N_SIMS):
        holdings = {d: rng.sample(pools[d], 10) for d in REBALANCE_DATES}
        nav = backtest_rebalanced_portfolio(prices, holdings)
        stats = perf_stats(nav, f"sim_{sim}")
        sim_stats.append(stats)

    sim_df = pd.DataFrame(sim_stats)
    sim_df.to_csv("random_momentum_sims.csv", index=False)

    with open("seeking_alpha_top10.json") as f:
        sa_holdings = json.load(f)
    sa_holdings = {k: v for k, v in sa_holdings.items() if not k.startswith("_")}
    sa_tickers = sorted({t for tickers in sa_holdings.values() for t in tickers})
    sa_prices = get_prices(sa_tickers, "2022-06-01", END)
    sa_nav = backtest_rebalanced_portfolio(sa_prices, sa_holdings)
    sa_stats = perf_stats(sa_nav, "Seeking Alpha Top 10 (actual)")

    cagr_pctile = (sim_df["cagr_%"] < sa_stats["cagr_%"]).mean() * 100

    print("\n=== Random momentum-basket baseline (N=%d sims) ===" % N_SIMS)
    print(sim_df[["cagr_%", "total_return_%", "ann_vol_%", "sharpe", "max_drawdown_%"]].describe(
        percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]
    ).to_string())

    print("\nSeeking Alpha Top 10 (actual):")
    for k, v in sa_stats.items():
        print(f"  {k}: {v}")
    print(f"\nSA Top 10's CAGR beats {cagr_pctile:.0f}% of random momentum-basket simulations")

    report = {
        "n_sims": N_SIMS,
        "pool_sizes": {d: len(p) for d, p in pools.items()},
        "random_momentum_cagr_pct_summary": sim_df["cagr_%"].describe(
            percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]
        ).to_dict(),
        "sa_top10_actual": sa_stats,
        "sa_cagr_percentile_vs_random_momentum": round(cagr_pctile, 1),
    }
    with open("random_momentum_report.json", "w") as f:
        json.dump(report, f, indent=2, default=float)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(sim_df["cagr_%"], bins=30, alpha=0.75, label=f"Random momentum baskets (N={N_SIMS})")
    ax.axvline(sa_stats["cagr_%"], color="red", linestyle="--", linewidth=2,
               label=f"Seeking Alpha Top 10 (actual): {sa_stats['cagr_%']:.1f}%")
    ax.set_xlabel("CAGR %")
    ax.set_ylabel("Number of simulations")
    ax.set_title("SA Top 10 vs. random 10-stock draws from the same top-momentum pool")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("random_momentum_hist.png", dpi=150)
    print("Saved random_momentum_sims.csv, random_momentum_report.json, random_momentum_hist.png")


if __name__ == "__main__":
    main()
