import numpy as np, pandas as pd
import edgar_quarterly_bt as E
import rebalance_freq as RF
from backtest import simulate_equal_weight, month_end_dates

if __name__ == "__main__":
    mes = E.mes
    q0, q1, q2, q3, cap = E.build_panels()
    sc = E.make_scores(q0, q1, q2, q3, cap)
    bbs = sc["blend"].where(sc["ttm"].notna())
    px = E.close.reindex(mes)[bbs.columns]
    mom = px.pct_change(12) > 0
    bbm = bbs.where(mom.fillna(False))                      # momentum-filtered buyback candidates
    valid = bbs.notna().sum(axis=1); first = valid.index[valid >= 50].min()
    bt = month_end_dates(E.all_dates, str(first.date()), E.END)

    bh = RF.build_holdings(E.close, E.div, mes[mes >= first])   # first 10 = high-yield, last 20 = growth (dual momentum)
    base = simulate_equal_weight(E.adj, bh, bt)
    legs = {}
    for n in (20, 30):
        h = E.holdings(bbm, n, first)
        legs[n] = (h, simulate_equal_weight(E.adj, h, bt))

    # name overlap and correlation with barbell growth leg / HY leg
    for n, (h, r) in legs.items():
        og = [len(set(h[d]) & set(bh[d][10:])) for d in h if d in bh]
        oh = [len(set(h[d]) & set(bh[d][:10])) for d in h if d in bh]
        j = pd.concat([base, r], axis=1).dropna()
        print(f"buyback+mom top {n}: avg overlap with barbell growth leg {np.mean(og):.1f}/20, with HY leg {np.mean(oh):.1f}/10; return corr with barbell {j.corr().iloc[0,1]:.2f}")

    def cal(r, y):
        x = r[r.index.year == y]; return ((1 + x).prod() - 1) * 100 if len(x) > 6 else np.nan
    def row(name, r):
        a = E.stats(r); s = {}
        for w, st in (("10y", "2016-09-23"), ("5y", "2021-09-23")):
            x = r[r.index >= pd.Timestamp(st)]; s[w] = E.stats(x)[2]
        return (name, a[0]*100, a[1]*100, a[2], a[3]*100, cal(r, 2018), cal(r, 2022), s["10y"], s["5y"])
    rows = [row("Barbell v2 alone", base)]
    for n, (h, r) in legs.items():
        rows.append(row(f"Buyback+mom top {n} alone", r))
        for w in (0.2, 0.35, 0.5):
            j = pd.concat([base, r], axis=1).dropna()
            rows.append(row(f"Barbell + {int(w*100)}% buyback leg (top {n})", (1 - w) * j.iloc[:, 0] + w * j.iloc[:, 1]))
    df = pd.DataFrame(rows, columns=["portfolio", "CAGR", "vol", "Sharpe", "MaxDD", "2018", "2022", "Sh10y", "Sh5y"])
    df.to_csv("barbell_plus_bb_results.csv", index=False)
    pd.options.display.float_format = "{:.2f}".format
    print(df.to_string(index=False))
