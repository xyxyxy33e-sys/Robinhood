import io, json, contextlib
import numpy as np, pandas as pd
with contextlib.redirect_stdout(io.StringIO()):
    import buyback_bt as B
    import barbell_bb as BB
from backtest import month_end_dates, simulate_equal_weight, perf_stats

close, adj, mes, all_dates = B.close, B.adj, B.mes, B.all_dates
bbk = json.load(open("buybacks.json"))
LAG = pd.Timedelta(days=120)
shares = B.shares

def annual_yield(kind):
    key = "a_rep" if kind == "gross" else None
    out = pd.DataFrame(np.nan, index=mes, columns=close.columns)
    for t in close.columns:
        d = bbk.get(t, {})
        rep = d.get("a_rep") or {}
        net = d.get("a_net") or {}
        src = rep if kind == "gross" else net
        if not src: continue
        s = pd.Series({pd.Timestamp(k): -v for k, v in src.items()}).sort_index()
        if t not in shares.columns: continue
        sh = shares[t].dropna()
        for dt in mes:
            avail = s[s.index + LAG <= dt]
            if avail.empty: continue
            fy_end = avail.index[-1]
            if (dt - fy_end).days > 540: continue          # stale
            sh_dt = sh[sh.index <= dt]
            if sh_dt.empty or (dt - sh_dt.index[-1]).days > 100: continue
            px = close.at[dt, t] if dt in close.index else np.nan
            if not np.isfinite(px): continue
            out.at[dt, t] = avail.iloc[-1] / (px * sh_dt.iloc[-1])
    return out

def build(score, n, start):
    h = {}
    for dt in mes:
        if dt < start: continue
        s = score.loc[dt].dropna(); s = s[(s > 0) & (s < 0.5)]     # drop >50% as data errors
        if len(s) >= n: h[dt] = list(s.sort_values(ascending=False).head(n).index)
    return h

START = pd.Timestamp("2022-04-01")
gross, net = annual_yield("gross"), annual_yield("net")
print("avg valid names/month:", int(gross.loc[mes >= START].notna().sum(axis=1).mean()))
bt = month_end_dates(all_dates, "2022-03-01", B.END)
res = {}
for tag, sc in (("gross", gross), ("net", net)):
    for n in (20, 30, 50):
        res[f"Buyback $/mktcap {tag} top {n}"] = simulate_equal_weight(adj, build(sc, n, START), bt)
res["Share-shrink top 30 (prior test)"] = simulate_equal_weight(adj, build(B.bb, 30, START), bt)
res["Barbell v2 baseline"] = simulate_equal_weight(adj, {k: v for k, v in BB.build("base").items() if k >= START}, bt)
res["SPY"] = B.spy_adj.reindex(bt).pct_change().dropna()
idx = None
for k, r in res.items():
    r = r[r.index >= START]
    perf_stats(r, k)
