import numpy as np, pandas as pd, yfinance as yf
import edgar_quarterly_bt as E
import rebalance_freq as RF
from backtest import simulate_equal_weight, month_end_dates

if __name__ == "__main__":
    mes = E.mes
    etf = yf.download(["IEF", "TLT", "GLD", "SHY"], start="2005-09-01", end="2026-09-23",
                      auto_adjust=False, progress=False)["Adj Close"]
    etf_me = etf.reindex(mes, method="ffill")
    etf_ret = etf_me.pct_change()

    q0, q1, q2, q3, cap = E.build_panels()
    sc = E.make_scores(q0, q1, q2, q3, cap)
    bbs = sc["blend"].where(sc["ttm"].notna())
    valid = bbs.notna().sum(axis=1); first = valid.index[valid >= 50].min()
    bt = month_end_dates(E.all_dates, str(first.date()), E.END)

    # bases
    base = {}
    base["Buyback top 30"] = simulate_equal_weight(E.adj, E.holdings(bbs, 30, first), bt)
    base["Barbell v2 (10 HY + 20 DM)"] = simulate_equal_weight(E.adj, RF.build_holdings(E.close, E.div, mes[mes >= first]), bt)

    # low-vol stock leg: 30 lowest trailing-252d realized vol
    vol = E.adj.pct_change().rolling(252).std().reindex(mes)
    lv = {d: list(vol.loc[d].dropna().nsmallest(30).index) for d in mes if d >= first}
    hedges = {"Low-vol stocks (30)": simulate_equal_weight(E.adj, lv, bt)}
    for t, nm in (("IEF", "Treasuries 7-10y (IEF)"), ("TLT", "Treasuries 20y+ (TLT)"), ("GLD", "Gold (GLD)"), ("SHY", "Cash-like 1-3y (SHY)")):
        hedges[nm] = etf_ret[t].reindex(bt).dropna()
    spy = E.spy_adj.reindex(mes).pct_change().reindex(bt).dropna()

    def cal(r, y):
        x = r[r.index.year == y]
        return ((1 + x).prod() - 1) * 100 if len(x) > 6 else np.nan

    rows = []
    for bn, b in base.items():
        for hn, h in [("(none)", None)] + list(hedges.items()):
            for w in ([0.0] if h is None else [0.2, 0.35]):
                if h is None: r = b
                else:
                    j = pd.concat([b, h], axis=1).dropna(); r = (1 - w) * j.iloc[:, 0] + w * j.iloc[:, 1]
                cagr, v, sh, dd = E.stats(r)
                corr = np.nan if h is None else pd.concat([b, h], axis=1).dropna().corr().iloc[0, 1]
                rows.append((bn, hn, int(w * 100), cagr * 100, v * 100, sh, dd * 100, corr, cal(r, 2018), cal(r, 2022)))
    df = pd.DataFrame(rows, columns=["base", "hedge leg", "hedge%", "CAGR", "vol", "Sharpe", "MaxDD", "corr", "2018", "2022"])
    df.to_csv("vol_leg_results.csv", index=False)
    r = spy; cagr, v, sh, dd = E.stats(r)
    print(f"window starts {first.date()}; SPY: CAGR {cagr*100:.1f} vol {v*100:.1f} Sharpe {sh:.2f} MaxDD {dd*100:.1f} 2018 {cal(spy,2018):.1f} 2022 {cal(spy,2022):.1f}")
    pd.options.display.float_format = "{:.1f}".format
    for bn in base:
        d = df[df.base == bn].drop(columns="base"); d["Sharpe"] = d["Sharpe"].map("{:.2f}".format); d["corr"] = d["corr"].map("{:.2f}".format)
        print(f"\n=== {bn} ==="); print(d.to_string(index=False))
