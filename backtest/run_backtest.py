"""Backtest: Dogs of the Dow vs Seeking Alpha Top 10 vs SPY.

Usage: python3 run_backtest.py
Outputs: backtest/report.md, backtest/nav.csv, backtest/chart.png
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from data import get_prices
from engine import backtest_rebalanced_portfolio, buy_and_hold, perf_stats

START = "2015-01-01"
END = "2026-09-17"


def load_holdings(path: str, rebalance_month_day: str = "01-02") -> dict[str, list[str]]:
    with open(path) as f:
        raw = json.load(f)
    holdings = {}
    for key, tickers in raw.items():
        if key.startswith("_"):
            continue
        if len(key) == 4:  # a bare year like "2015" -> Dogs-of-Dow holding year
            date = f"{key}-{rebalance_month_day}"
        else:  # already a full date, e.g. "2023-01-01"
            date = key
        holdings[date] = tickers
    return holdings


def main():
    dogs_holdings = load_holdings("dogs_of_the_dow.json")
    sa_holdings = load_holdings("seeking_alpha_top10.json")

    all_tickers = {"SPY"}
    for h in (dogs_holdings, sa_holdings):
        for tickers in h.values():
            all_tickers.update(tickers)

    print(f"Fetching price history for {len(all_tickers)} tickers...")
    prices = get_prices(sorted(all_tickers), START, END)
    print(f"Got data shape: {prices.shape}")

    missing_cols = [c for c in prices.columns if prices[c].dropna().empty]
    if missing_cols:
        print(f"WARNING: no usable data for {missing_cols}, dropping from baskets")

    dogs_nav = backtest_rebalanced_portfolio(prices, dogs_holdings)
    sa_nav = backtest_rebalanced_portfolio(prices, sa_holdings)
    spy_nav_full = buy_and_hold(prices["SPY"])

    # SPY benchmark aligned to each strategy's own start date, plus a
    # full-period SPY line for reference.
    spy_dogs = buy_and_hold(prices.loc[prices.index >= dogs_nav.index[0], "SPY"])
    spy_sa = buy_and_hold(prices.loc[prices.index >= sa_nav.index[0], "SPY"])

    stats = [
        perf_stats(dogs_nav, "Dogs of the Dow"),
        perf_stats(spy_dogs, "SPY (Dogs period)"),
        perf_stats(sa_nav, "Seeking Alpha Top 10"),
        perf_stats(spy_sa, "SPY (SA period)"),
        perf_stats(spy_nav_full, "SPY (full 2015-present)"),
    ]
    stats_df = pd.DataFrame(stats)
    print(stats_df.to_string(index=False))

    nav_df = pd.DataFrame({
        "dogs_of_the_dow": dogs_nav,
        "spy_dogs_period": spy_dogs,
        "seeking_alpha_top10": sa_nav,
        "spy_sa_period": spy_sa,
        "spy_full": spy_nav_full,
    })
    nav_df.to_csv("nav.csv")

    fig, axes = plt.subplots(2, 1, figsize=(11, 10))
    axes[0].plot(dogs_nav.index, dogs_nav, label="Dogs of the Dow")
    axes[0].plot(spy_dogs.index, spy_dogs, label="SPY", linestyle="--")
    axes[0].set_title("Dogs of the Dow vs SPY (2015-present, annual rebalance)")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(sa_nav.index, sa_nav, label="Seeking Alpha Top 10")
    axes[1].plot(spy_sa.index, spy_sa, label="SPY", linestyle="--")
    axes[1].set_title("Seeking Alpha Top 10 vs SPY (2023-present, annual rebalance)")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig("chart.png", dpi=150)
    print("Saved nav.csv, chart.png")

    with open("report.md", "w") as f:
        f.write("# Backtest: Dogs of the Dow & Seeking Alpha Top 10 vs SPY\n\n")
        f.write(stats_df.to_markdown(index=False))
        f.write("\n\nSee chart.png for equity curves. Raw NAV series in nav.csv.\n")


if __name__ == "__main__":
    main()
