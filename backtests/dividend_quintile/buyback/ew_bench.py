import numpy as np, pandas as pd
import edgar_quarterly_bt as E
from backtest import simulate_equal_weight, month_end_dates

if __name__ == "__main__":
    q0, q1, q2, q3, cap = E.build_panels()
    sc = E.make_scores(q0, q1, q2, q3, cap)
    bbs = sc["blend"].where(sc["ttm"].notna())
    mes = E.mes
    valid = bbs.notna().sum(axis=1); first = valid.index[valid >= 50].min()
    WINDOWS = {"all data": str(first.date()), "10y": "2016-09-23", "5y": "2021-09-23"}
    px = E.close.reindex(mes)

    H = {}
    H["Equal-weight all S&P 500 names"] = {d: list(px.loc[d].dropna().index) for d in mes if d >= first}
    H["Equal-weight valid-signal universe"] = {d: list(bbs.loc[d].dropna().index) for d in mes if d >= first and bbs.loc[d].notna().sum() >= 50}
    for n in (20, 30):
        H[f"Buyback top {n}"] = E.holdings(bbs, n, first)
    for k in range(5):                                          # quintiles of the blend score (Q1 = highest)
        h = {}
        for d in mes:
            if d < first: continue
            s = bbs.loc[d].dropna()
            if len(s) < 50: continue
            r = s.rank(pct=True, ascending=False)
            h[d] = list(r[(r > k/5) & (r <= (k+1)/5)].index)
        H[f"Blend quintile {k+1}" + (" (top)" if k == 0 else " (bottom)" if k == 4 else "")] = h

    rows = []
    for w, st in WINDOWS.items():
        bt = month_end_dates(E.all_dates, st, E.END)
        for name, h in H.items():
            r = simulate_equal_weight(E.adj, h, bt); r = r[r.index >= pd.Timestamp(st)]
            rows.append((w, name, *E.stats(r)))
        r = E.spy_adj.reindex(bt).pct_change().dropna(); r = r[r.index >= pd.Timestamp(st)]
        rows.append((w, "SPY (cap-weighted)", *E.stats(r)))
    df = pd.DataFrame(rows, columns=["window", "portfolio", "cagr", "vol", "sharpe", "maxdd"])
    df.to_csv("ew_bench_results.csv", index=False)
    for w in WINDOWS:
        d = df[df.window == w].drop(columns="window").copy()
        d["cagr"] = (d.cagr*100).round(1); d["vol"] = (d.vol*100).round(1)
        d["sharpe"] = d.sharpe.round(2); d["maxdd"] = (d.maxdd*100).round(1)
        print(f"\n=== {w} ==="); print(d.to_string(index=False))
