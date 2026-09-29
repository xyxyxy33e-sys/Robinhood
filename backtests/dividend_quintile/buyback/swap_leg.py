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
    bbm = bbs.where((px.pct_change(12) > 0).fillna(False))
    valid = bbs.notna().sum(axis=1); first = valid.index[valid >= 50].min()
    bt = month_end_dates(E.all_dates, str(first.date()), E.END)
    bh = RF.build_holdings(E.close, E.div, mes[mes >= first])
    HY = {d: v[:10] for d, v in bh.items()}; GR = {d: v[10:] for d, v in bh.items()}

    def top(score, d, n, excl):
        s = score.loc[d].dropna().sort_values(ascending=False)
        return [t for t in s.index if t not in excl][:n]

    def combine(fixed, score, n_bb, fixed_first=True):
        h = {}
        for d in fixed:
            b = top(score, d, n_bb, set(fixed[d]))
            if len(b) == n_bb: h[d] = fixed[d] + b
        return h

    H = {
        "Barbell v2 (10 HY + 20 DM growth)": bh,
        "Buyback+mom top 30 alone": E.holdings(bbm, 30, first),
        "Swap growth leg: 10 HY + 20 buyback+mom": combine(HY, bbm, 20),
        "Swap growth leg: 10 HY + 20 buyback (no mom filter)": combine(HY, bbs, 20),
        "Swap HY leg: 10 buyback+mom + 20 DM growth": combine(GR, bbm, 10),
        "Swap HY leg: 10 buyback (no mom filter) + 20 DM growth": combine(GR, bbs, 10),
        "Swap HY leg: 15 buyback+mom + 15 DM growth": {d: top(bbm, d, 15, set(GR[d][:15])) + GR[d][:15] for d in GR if len(top(bbm, d, 15, set(GR[d][:15]))) == 15},
    }
    def cal(r, y):
        x = r[r.index.year == y]; return ((1 + x).prod() - 1) * 100 if len(x) > 6 else np.nan
    rows = []
    for name, h in H.items():
        r = simulate_equal_weight(E.adj, h, bt); a = E.stats(r)
        s10 = E.stats(r[r.index >= pd.Timestamp("2016-09-23")])[2]; s5 = E.stats(r[r.index >= pd.Timestamp("2021-09-23")])[2]
        rows.append((name, a[0]*100, a[1]*100, a[2], a[3]*100, cal(r, 2018), cal(r, 2022), s10, s5))
    df = pd.DataFrame(rows, columns=["portfolio", "CAGR", "vol", "Sharpe", "MaxDD", "2018", "2022", "Sh10y", "Sh5y"])
    df.to_csv("swap_leg_results.csv", index=False)
    pd.options.display.float_format = "{:.2f}".format
    print(df.to_string(index=False))
