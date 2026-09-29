import numpy as np, pandas as pd
import edgar_quarterly_bt as E
from backtest import ttm_dividends, simulate_equal_weight, month_end_dates

if __name__ == "__main__":
    q0, q1, q2, q3, cap = E.build_panels()
    sc = E.make_scores(q0, q1, q2, q3, cap)
    bbs = sc["blend"].where(sc["ttm"].notna())            # blend, restricted to valid buyback names
    mes = E.mes
    dy = (ttm_dividends(E.div, mes) / E.close.reindex(mes)).replace([np.inf, -np.inf], np.nan)
    dy = dy.where(dy > 0)
    valid = bbs.notna().sum(axis=1); first = valid.index[valid >= 50].min()
    idx = [d for d in mes if d >= first]

    print("=== Overlap of top-N buyback (rank blend) vs top-N dividend yield, monthly, since", first.date(), "===")
    for n in (20, 30, 50):
        ov = []
        for d in idx:
            a = set(bbs.loc[d].dropna().nlargest(n).index); b = set(dy.loc[d].dropna().nlargest(n).index)
            ov.append(len(a & b))
        ov = pd.Series(ov, index=idx)
        print(f"N={n}: avg overlap {ov.mean():.1f} names ({ov.mean()/n*100:.0f}%), median {ov.median():.0f}, max {ov.max()}, months with zero overlap {(ov==0).mean()*100:.0f}%")

    rc = []
    for d in idx:
        x = pd.concat([bbs.loc[d], dy.loc[d]], axis=1).dropna()
        if len(x) > 30: rc.append(x.corr(method="spearman").iloc[0, 1])
    print(f"\nAvg cross-sectional rank correlation (buyback vs dividend yield): {np.mean(rc):.2f}")

    # share of top-30 buyback names paying no dividend
    zero = [ (dy.loc[d].reindex(bbs.loc[d].dropna().nlargest(30).index).isna()).mean() for d in idx]
    print(f"Avg share of top-30 buyback names paying no dividend: {np.mean(zero)*100:.0f}%")

    # return correlation of the two top-30 portfolios
    hb = E.holdings(bbs, 30, first)
    hd = {d: list(dy.loc[d].dropna().nlargest(30).index) for d in idx}
    bt = month_end_dates(E.all_dates, str(first.date()), E.END)
    rb, rd = simulate_equal_weight(E.adj, hb, bt), simulate_equal_weight(E.adj, hd, bt)
    j = pd.concat([rb, rd], axis=1).dropna(); j.columns = ["buyback", "dividend"]
    print(f"\nMonthly return correlation, top-30 buyback vs top-30 dividend: {j.corr().iloc[0,1]:.2f}")
    for name, r in (("buyback top30", rb), ("dividend top30", rd), ("50/50 mix", 0.5*rb.reindex(j.index)+0.5*rd.reindex(j.index))):
        cagr, vol, sh, dd = E.stats(r.dropna()); print(f"  {name:15s} CAGR {cagr*100:5.1f}%  vol {vol*100:4.1f}%  Sharpe {sh:.2f}  MaxDD {dd*100:.1f}%")

    d = [x for x in idx if E.close.reindex(mes).loc[x].notna().sum() > 400][-1]
    print(f"\n=== Latest ({d.date()}) ===")
    for n in (20, 30):
        a = list(bbs.loc[d].dropna().nlargest(n).index); b = list(dy.loc[d].dropna().nlargest(n).index)
        print(f"top-{n} buyback: {a}\ntop-{n} dividend: {b}\noverlap: {sorted(set(a)&set(b))}\n")
