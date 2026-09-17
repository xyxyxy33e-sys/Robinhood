"""Simple equal-weight, periodic-rebalance backtest engine."""
from __future__ import annotations

import pandas as pd


def backtest_rebalanced_portfolio(
    prices: pd.DataFrame, holdings: dict[str, list[str]]
) -> pd.Series:
    """Equal-weight portfolio that resets weights to 1/N on each rebalance date.

    holdings: {rebalance_date_str: [tickers]}, sorted chronologically. The
    portfolio holds the given tickers equal-weighted from that date until the
    next rebalance date (or the end of the price history).

    Returns a Series of portfolio value indexed by date, starting at 1.0 on
    the first rebalance date.
    """
    dates = sorted(holdings.keys())
    all_index = prices.index
    value = pd.Series(index=all_index, dtype=float)

    start_date = pd.Timestamp(dates[0])
    all_index = all_index[all_index >= start_date]
    if len(all_index) == 0:
        raise ValueError("No price data on/after first rebalance date")

    nav = 1.0
    out = []
    out_idx = []

    for i, rdate_str in enumerate(dates):
        rdate = pd.Timestamp(rdate_str)
        next_rdate = pd.Timestamp(dates[i + 1]) if i + 1 < len(dates) else None

        tickers = [t for t in holdings[rdate_str] if t in prices.columns]
        seg_index = all_index[all_index >= rdate]
        if next_rdate is not None:
            seg_index = seg_index[seg_index < next_rdate]
        if len(seg_index) == 0:
            continue

        seg_prices = prices.loc[seg_index, tickers].dropna(axis=1, how="all")
        seg_prices = seg_prices.ffill()
        first_valid = seg_prices.iloc[0]
        weights = pd.Series(1.0 / len(first_valid.dropna()), index=first_valid.dropna().index)

        rel = seg_prices[weights.index].div(first_valid[weights.index])
        seg_nav = rel.mul(weights).sum(axis=1) * nav

        out.append(seg_nav)
        out_idx.extend(seg_index.tolist())
        nav = seg_nav.iloc[-1]

    result = pd.concat(out)
    result = result[~result.index.duplicated(keep="last")].sort_index()
    return result


def buy_and_hold(prices: pd.Series) -> pd.Series:
    """Normalized buy-and-hold NAV series starting at 1.0."""
    s = prices.dropna()
    return s / s.iloc[0]


def perf_stats(nav: pd.Series, label: str) -> dict:
    nav = nav.dropna()
    daily_ret = nav.pct_change().dropna()
    n_years = (nav.index[-1] - nav.index[0]).days / 365.25
    total_return = nav.iloc[-1] / nav.iloc[0] - 1
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / n_years) - 1 if n_years > 0 else float("nan")
    vol = daily_ret.std() * (252 ** 0.5)
    sharpe = (daily_ret.mean() * 252) / vol if vol else float("nan")
    running_max = nav.cummax()
    drawdown = nav / running_max - 1
    max_dd = drawdown.min()
    return {
        "strategy": label,
        "start": nav.index[0].date().isoformat(),
        "end": nav.index[-1].date().isoformat(),
        "total_return_%": round(total_return * 100, 2),
        "cagr_%": round(cagr * 100, 2),
        "ann_vol_%": round(vol * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_%": round(max_dd * 100, 2),
    }
