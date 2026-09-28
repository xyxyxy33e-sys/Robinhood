import numpy as np, pandas as pd
from backtest import load_data, month_end_dates, simulate_equal_weight, perf_stats, ttm_dividends

END = "2026-09-23"
WINDOWS = {"5y": "2021-09-23", "10y": "2016-09-23"}
close, adj, div, spy_adj = load_data()
shares = pd.read_parquet("shares.parquet")
all_dates = close.index
mes = month_end_dates(all_dates, all_dates.min(), END)

def asof(df, dates):
    return df.reindex(df.index.union(dates)).ffill().reindex(dates)

sh_now = asof(shares, mes)
sh_lag = asof(shares, mes - pd.DateOffset(years=1))
sh_lag.index = mes
# staleness guard: require an observation within 100 days of each date
last_obs = shares.notna().apply(lambda c: pd.Series(c.index.where(c.values), index=c.index)).ffill()
def fresh(dates):
    lo = last_obs.reindex(last_obs.index.union(dates)).ffill().reindex(dates)
    return (pd.DataFrame(dates.values[:, None] - lo.values, index=dates, columns=lo.columns) / np.timedelta64(1, "D")) < 100
f_now, f_lag = fresh(mes), fresh(mes - pd.DateOffset(years=1))
f_lag.index = mes

chg = sh_now / sh_lag - 1
chg = chg.where(f_now & f_lag)
chg = chg.where(chg.abs() < 0.30)            # drop split/M&A artifacts
bb = -chg                                     # positive = net shrink
ttm = ttm_dividends(div, mes)
dy = (ttm / close.reindex(mes)).replace([np.inf, -np.inf], np.nan)

def build(score, n):
    h = {}
    for dt in mes:
        s = score.loc[dt].dropna()
        s = s[s > 0]
        if len(s) >= n: h[dt] = list(s.sort_values(ascending=False).head(n).index)
    return h

def run(tag, h):
    for w, st in WINDOWS.items():
        bt = month_end_dates(all_dates, st, END)
        r = simulate_equal_weight(adj, h, bt)
        perf_stats(r, f"[{w}] {tag}")

print("avg names with valid buyback signal / month:", int(bb.loc[mes[mes >= '2016-11-01']].notna().sum(axis=1).mean()))
for n in (20, 30, 50):
    run(f"Net buyback top {n} (share shrink)", build(bb, n))
sy = bb.fillna(0) + dy.fillna(0)
sy = sy.where(bb.notna())
for n in (20, 30, 50):
    run(f"Shareholder yield top {n} (div+buyback)", build(sy, n))
for w, st in WINDOWS.items():
    bt = month_end_dates(all_dates, st, END)
    perf_stats(spy_adj.reindex(bt).pct_change().dropna(), f"[{w}] SPY")
