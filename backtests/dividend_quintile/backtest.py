"""
Second Quintile dividend-yield backtest.

Strategy:
  - Universe: current S&P 500 constituents (static list, survivorship bias noted).
  - At each month-end, compute trailing-twelve-month (TTM) dividend yield per stock
    = sum(dividends over trailing 12 months) / month-end close price.
  - Rank stocks by TTM yield into quintiles (5 equal-sized buckets).
  - Portfolio = equal-weighted holdings of the 2nd quintile (next-highest 20%
    after the top 20% yielders), rebalanced monthly.
  - Returns computed from Adjusted Close (dividends reinvested), so monthly total
    return = adj_close[t+1]/adj_close[t] - 1 for each held name, equal-weighted.
  - Benchmark: SPY total return (adjusted close).

Output: cumulative growth of $1, CAGR, vol, Sharpe, max drawdown, and comparison
to SPY and to quintile 1/3/4/5 for context.
"""
import numpy as np
import pandas as pd

DATA_PATH = "/tmp/claude-0/-home-user-Robinhood/9cd955bf-712e-5400-90f6-198dab301530/scratchpad/sp500_data.parquet"
BACKTEST_START = "2005-09-23"  # 20 years back from 2025-09-23; extra history before this used only for TTM div calc
BACKTEST_END = "2026-09-23"
MIN_HISTORY_DAYS = 380  # require enough trailing data to compute a stable TTM yield


def load_data():
    store = pd.read_parquet(DATA_PATH)
    store.index = pd.to_datetime(store.index)
    store = store.sort_index()
    tickers = sorted(set(store.columns.get_level_values(0)) - {"SPY"})
    close = pd.concat({t: store[t]["Close"] for t in tickers if t in store.columns.get_level_values(0)}, axis=1)
    adj = pd.concat({t: store[t]["Adj Close"] for t in tickers if t in store.columns.get_level_values(0)}, axis=1)
    div = pd.concat({t: store[t]["Dividends"] for t in tickers if t in store.columns.get_level_values(0)}, axis=1)
    spy_adj = store["SPY"]["Adj Close"]
    return close, adj, div, spy_adj


def month_end_dates(index, start, end):
    idx = index[(index >= start) & (index <= end)]
    me = idx.to_series().groupby(idx.to_period("M")).max()
    return pd.DatetimeIndex(me.values)


def ttm_dividends(div, asof_dates):
    """Trailing-12-month dividend sum per ticker as of each month-end date."""
    daily = div.fillna(0.0)
    roll = daily.rolling("365D").sum()
    return roll.reindex(asof_dates, method="ffill")


def build_quintile_portfolios(close, adj, div, all_month_ends):
    ttm = ttm_dividends(div, all_month_ends)
    yld = ttm / close.reindex(all_month_ends)
    yld = yld.replace([np.inf, -np.inf], np.nan)

    quintile_holdings = {q: {} for q in range(1, 6)}
    for dt in all_month_ends:
        row = yld.loc[dt].dropna()
        # require the name to actually have traded (price present) at this date
        px_ok = close.loc[dt, row.index].notna()
        row = row[px_ok]
        row = row[row >= 0]
        if len(row) < 25:
            continue
        ranks = row.rank(pct=True, ascending=True)
        # ascending pct rank: 1.0 = highest yield. Quintile 1 = top 20% (>=0.8), Q2 = next 20% (0.6-0.8), etc.
        for q in range(1, 6):
            hi = 1.0 - (q - 1) * 0.2
            lo = 1.0 - q * 0.2
            if q == 1:
                sel = row.index[(ranks > lo) & (ranks <= hi + 1e-9)]
            else:
                sel = row.index[(ranks > lo - 1e-9) & (ranks <= hi)]
            quintile_holdings[q][dt] = list(sel)
    return quintile_holdings


def simulate_equal_weight(adj, holdings_by_date, month_ends):
    """Equal-weight, monthly-rebalanced portfolio using adjusted-close total returns."""
    rets = []
    dates_used = []
    for i in range(len(month_ends) - 1):
        d0, d1 = month_ends[i], month_ends[i + 1]
        names = holdings_by_date.get(d0, [])
        if not names:
            continue
        p0 = adj.loc[d0, names]
        p1 = adj.loc[d1, names]
        valid = p0.notna() & p1.notna() & (p0 > 0)
        names_v = p0.index[valid]
        if len(names_v) == 0:
            continue
        stock_ret = (p1[names_v] / p0[names_v]) - 1.0
        port_ret = stock_ret.mean()
        rets.append(port_ret)
        dates_used.append(d1)
    return pd.Series(rets, index=pd.DatetimeIndex(dates_used))


def perf_stats(monthly_returns, label):
    cum = (1 + monthly_returns).cumprod()
    n_years = len(monthly_returns) / 12.0
    total_return = cum.iloc[-1] - 1
    cagr = cum.iloc[-1] ** (1 / n_years) - 1
    vol = monthly_returns.std() * np.sqrt(12)
    sharpe = (monthly_returns.mean() * 12) / vol if vol > 0 else np.nan
    running_max = cum.cummax()
    dd = cum / running_max - 1
    max_dd = dd.min()
    growth_of_1000 = 1000 * cum.iloc[-1]
    print(f"\n=== {label} ===")
    print(f"Period: {monthly_returns.index[0].date()} to {monthly_returns.index[-1].date()} ({n_years:.1f} yrs)")
    print(f"Total return: {total_return*100:,.1f}%")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"Annualized Vol: {vol*100:.2f}%")
    print(f"Sharpe (rf=0): {sharpe:.2f}")
    print(f"Max Drawdown: {max_dd*100:.2f}%")
    print(f"$1,000 grew to: ${growth_of_1000:,.0f}")
    return {
        "label": label, "cum": cum, "total_return": total_return, "cagr": cagr,
        "vol": vol, "sharpe": sharpe, "max_dd": max_dd,
    }


def main():
    close, adj, div, spy_adj = load_data()
    all_dates = close.index
    hist_start = all_dates.min()
    print(f"Loaded data: {len(close.columns)} tickers, {hist_start.date()} to {all_dates.max().date()}")

    all_month_ends = month_end_dates(all_dates, hist_start, BACKTEST_END)
    bt_month_ends = month_end_dates(all_dates, BACKTEST_START, BACKTEST_END)

    quintiles = build_quintile_portfolios(close, adj, div, all_month_ends)

    results = {}
    for q in range(1, 6):
        rets = simulate_equal_weight(adj, quintiles[q], bt_month_ends)
        results[q] = perf_stats(rets, f"Quintile {q} (dividend yield rank)")

    # SPY benchmark (monthly total return from adjusted close)
    spy_me = spy_adj.reindex(bt_month_ends)
    spy_ret = spy_me.pct_change().dropna()
    spy_stats = perf_stats(spy_ret, "SPY (S&P 500 benchmark)")

    # Save results for charting
    out = pd.DataFrame({f"Q{q}": results[q]["cum"] for q in range(1, 6)})
    out["SPY"] = spy_stats["cum"]
    out = out.dropna(how="all")
    out.to_csv("/tmp/claude-0/-home-user-Robinhood/9cd955bf-712e-5400-90f6-198dab301530/scratchpad/cumulative_returns.csv")

    summary_rows = []
    for q in range(1, 6):
        r = results[q]
        summary_rows.append([f"Quintile {q}", r["total_return"], r["cagr"], r["vol"], r["sharpe"], r["max_dd"]])
    summary_rows.append(["SPY", spy_stats["total_return"], spy_stats["cagr"], spy_stats["vol"], spy_stats["sharpe"], spy_stats["max_dd"]])
    summary = pd.DataFrame(summary_rows, columns=["Strategy", "TotalReturn", "CAGR", "Vol", "Sharpe", "MaxDD"])
    summary.to_csv("/tmp/claude-0/-home-user-Robinhood/9cd955bf-712e-5400-90f6-198dab301530/scratchpad/summary.csv", index=False)
    print("\n\nSaved cumulative_returns.csv and summary.csv")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
