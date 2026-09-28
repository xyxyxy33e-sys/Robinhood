import numpy as np, pandas as pd
import buyback_bt as B   # reuses signals (prints its own output; ignore)
from backtest import month_end_dates, simulate_equal_weight, perf_stats

close, adj, div, all_dates, mes, bb, dy = B.close, B.adj, B.div, B.all_dates, B.mes, B.bb, B.dy
ttm = div.fillna(0).rolling("365D").sum(); ttm_prior = ttm.shift(252)
mom6 = close.pct_change(126); mom12 = close.pct_change(252)
yld = (ttm / close).replace([np.inf, -np.inf], np.nan)

def build(mode):
    h = {}
    for dt in mes:
        if dt < pd.Timestamp("2016-11-01"): continue
        row = yld.loc[dt].dropna(); row = row[close.loc[dt, row.index].notna()]
        hy = row.copy()
        cut = (ttm.loc[dt] < ttm_prior.loc[dt]) & ttm_prior.loc[dt].notna() & (ttm_prior.loc[dt] > 0)
        hy = hy.drop(index=[t for t in cut[cut].index if t in hy.index])
        hy = hy.drop(index=[t for t in mom6.loc[dt][mom6.loc[dt] < -0.25].index if t in hy.index])
        b = bb.loc[dt].reindex(hy.index)
        if mode == "filter":          # require not diluting (net share count flat/shrinking)
            hy = hy[b.fillna(-1) >= 0]
            score = hy
        elif mode == "shy":           # rank by dividend + buyback yield
            score = (hy + b.fillna(0).clip(lower=0))
        else:
            score = hy
        top = list(score.sort_values(ascending=False).head(10).index)
        zy = row[row <= 1e-9].index
        m12 = mom12.loc[dt].reindex(zy).dropna(); m12 = m12[m12 > 0]
        bot = list(m12.sort_values(ascending=False).head(20).index)
        if len(top) == 10 and len(bot) == 20: h[dt] = top + bot
    return h

for tag, mode in [("Barbell v2 (baseline)", "base"), ("Barbell + HY leg no-dilution filter", "filter"), ("Barbell + HY leg ranked by div+buyback yield", "shy")]:
    h = build(mode)
    for w, st in B.WINDOWS.items():
        bt = month_end_dates(all_dates, st, B.END)
        perf_stats(simulate_equal_weight(adj, h, bt), f"[{w}] {tag}")
