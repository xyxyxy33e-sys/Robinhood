"""Market trend filter: hold the strategy only when SPY's trend is positive, else SHY (1-3y Treasuries)."""
import numpy as np, pandas as pd, yfinance as yf
from engine import Engine, stats
import buyback_signal as BS

if __name__ == "__main__":
    E = Engine()
    shy = yf.download("SHY", start="2005-09-01", end="2026-09-30", auto_adjust=False, progress=False)["Adj Close"].squeeze()
    shy_r = shy.reindex(E.mes, method="ffill").pct_change()
    spy_px = E.spy.reindex(E.mes, method="ffill")
    sig = {"12m return > 0": spy_px.pct_change(12) > 0, "price > 10m SMA": spy_px > spy_px.rolling(10).mean()}
    q0, q1, q2, q3, cap = BS.panels(E.close, E.mes)
    sc = BS.scores(q0, q1, q2, q3, cap)
    mom_ok = (E.mom[252] > 0).reindex(columns=cap.columns).fillna(False)
    hyr, grr = E.hy_ranked(True), E.growth_ranked(True, 252)
    base = {"Barbell v2": (E.port_returns(E.barbell(10, 20, hyr, grr, start='2006-10-01')), "2006-10-01")}
    s = sc["blend"].where(mom_ok); h = {}
    for d in E.mes:
        v = s.loc[d].dropna()
        if len(v) >= 30: h[d] = list(v.sort_values(ascending=False).head(30).index)
    base["Buyback blend+mom top30"] = (E.port_returns(h), "2010-06-01")
    base["SPY"] = (E.spy_ret.dropna(), "2006-10-01")
    cal = lambda r, y: ((1 + r[r.index.year == y]).prod() - 1) * 100 if (r.index.year == y).sum() > 6 else np.nan
    rows = []
    for name, (r, start) in base.items():
        r = r[r.index >= start]
        variants = [("no filter", r, 0.0, 0)]
        for sn, on in sig.items():
            on_prev = on.shift(1).reindex(r.index)              # signal known at t-1 decides month t
            valid = on_prev.notna()
            fr = pd.Series(np.where(on_prev[valid], r[valid], shy_r.reindex(r.index)[valid]), index=r.index[valid])
            variants.append((sn, fr, 1 - on_prev[valid].mean(), int((on_prev[valid] != on_prev[valid].shift()).sum() - 1)))
        for vn, x, off, sw in variants:
            c, v, sh, dd = stats(x)
            rows.append((name, vn, c * 100, v * 100, sh, dd * 100, cal(x, 2008), cal(x, 2020), cal(x, 2022), off * 100, sw))
    df = pd.DataFrame(rows, columns=["strategy", "filter", "CAGR", "vol", "Sharpe", "MaxDD", "2008", "2020", "2022", "% months out", "switches"])
    df.to_csv("trend_filter_results.csv", index=False)
    pd.options.display.float_format = "{:.1f}".format
    print(df.to_string(index=False))
