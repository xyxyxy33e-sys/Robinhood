import numpy as np, pandas as pd
import edgar_quarterly_bt as E
from backtest import ttm_dividends, simulate_equal_weight, month_end_dates

if __name__ == "__main__":
    q0, q1, q2, q3, cap = E.build_panels()
    sc = E.make_scores(q0, q1, q2, q3, cap)
    bbs = sc["blend"].where(sc["ttm"].notna())
    mes = E.mes
    px = E.close.reindex(mes)
    ttm = ttm_dividends(E.div, mes)
    dy = (ttm / px).replace([np.inf, -np.inf], np.nan).where(lambda x: x > 0)
    cut = (ttm < ttm.shift(12)) & (ttm.shift(12) > 0)
    crash = px.pct_change(6) < -0.25
    dy_q = dy.mask(cut | crash)                       # quality-screened dividend yield
    valid = bbs.notna().sum(axis=1); first = valid.index[valid >= 50].min()
    WINDOWS = {"all data": str(first.date()), "10y": "2016-09-23", "5y": "2021-09-23"}

    def top(score, d, n, exclude=()):
        s = score.loc[d].dropna()
        return [t for t in s.sort_values(ascending=False).index if t not in exclude][:n]

    rows = []
    for n in (10, 15):
        hb, hd, hc = {}, {}, {}
        for d in mes:
            if d < first: continue
            b = top(bbs, d, n); dd = top(dy_q, d, n)
            if len(b) < n or len(dd) < n: continue
            b = top(bbs, d, n, exclude=set(dd))       # dedupe: dividend leg keeps shared names
            hb[d], hd[d], hc[d] = b, dd, b + dd
        for w, st in WINDOWS.items():
            bt = month_end_dates(E.all_dates, st, E.END)
            for name, h in ((f"Buyback {n}", hb), (f"Dividend (quality) {n}", hd), (f"{n}+{n} combined ({2*n} names)", hc)):
                r = simulate_equal_weight(E.adj, h, bt); r = r[r.index >= pd.Timestamp(st)]
                rows.append((w, name, *E.stats(r)))
    for w, st in WINDOWS.items():
        r = E.spy_adj.reindex(month_end_dates(E.all_dates, st, E.END)).pct_change().dropna()
        r = r[r.index >= pd.Timestamp(st)]
        rows.append((w, "SPY", *E.stats(r)))
    df = pd.DataFrame(rows, columns=["window", "portfolio", "cagr", "vol", "sharpe", "maxdd"])
    df.to_csv("two_sleeve_results.csv", index=False)
    for w in WINDOWS:
        print(f"\n=== {w} ===")
        d = df[df.window == w].drop(columns="window").copy()
        d["cagr"] = (d.cagr*100).round(1); d["vol"] = (d.vol*100).round(1)
        d["sharpe"] = d.sharpe.round(2); d["maxdd"] = (d.maxdd*100).round(1)
        print(d.to_string(index=False))
