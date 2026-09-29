"""
Test extra filters on the buyback list (blend score, top-N, monthly, equal weight).
Filters are applied BEFORE taking the top N (they restrict the candidate pool):
  shrink : net share count over 12m <= +0.5% (buybacks actually reduce shares)
  mom    : trailing 12-month price return > 0
  size   : point-in-time market cap >= $10B
  pay    : (TTM buybacks + TTM dividends) / TTM operating cash flow <= 100%, OCF > 0
  prof   : TTM net income > 0
Fundamentals (pay, prof) need edgar_facts2.json from fetch_edgar2.py.
"""
import json
import numpy as np, pandas as pd
import edgar_quarterly_bt as E
from backtest import simulate_equal_weight, month_end_dates

facts2 = json.load(open("edgar_facts2.json"))
MES = E.mes


def ttm_series(t, key):
    col = np.full(len(MES), np.nan)
    rows = facts2.get(t, {}).get(key) or []
    if not rows:
        return t, col
    q = E.discrete_quarters(rows)
    if len(q) < 4:
        return t, col
    ends, vals = q["end"].values, q["q"].values
    filed = np.maximum.accumulate(q["filed"].values)
    k = np.searchsorted(filed, MES.values, side="right")
    for i in range(len(MES)):
        if k[i] >= 4:
            e = ends[k[i] - 4:k[i]]
            gaps = np.diff(e).astype("timedelta64[D]").astype(int)
            fresh = (MES.values[i] - e[-1]).astype("timedelta64[D]").astype(int) <= 200
            if fresh and np.all((gaps > 75) & (gaps < 105)):
                col[i] = vals[k[i] - 4:k[i]].sum()
    return t, col


def ttm_panel(key, pool):
    res = pool.starmap(ttm_series, [(t, key) for t in facts2])
    return pd.DataFrame({t: c for t, c in res}, index=MES)


if __name__ == "__main__":
    from multiprocessing import Pool
    q0, q1, q2, q3, cap = E.build_panels()
    with Pool(4) as p:
        ocf, dvp, ni = ttm_panel("ocf", p), ttm_panel("divpaid", p), ttm_panel("ni", p)
    cols = q0.columns
    ocf, dvp, ni = (x.reindex(columns=cols) for x in (ocf, dvp, ni))
    sc = E.make_scores(q0, q1, q2, q3, cap)
    bbs = sc["blend"].where(sc["ttm"].notna())
    px = E.close.reindex(MES)[cols]
    shares = cap / px
    ttm_bb = q0 + q1 + q2 + q3
    F = {
        "shrink": (shares / shares.shift(12) - 1) <= 0.005,
        "mom": px.pct_change(12) > 0,
        "size": cap >= 10e9,
        "pay": ((ttm_bb + dvp.fillna(0)) / ocf <= 1.0) & (ocf > 0),
        "prof": ni > 0,
    }
    combos = [("baseline (no filter)", []), ("+shrink", ["shrink"]), ("+mom", ["mom"]), ("+size>=10B", ["size"]),
              ("+pay<=100% OCF", ["pay"]), ("+profitable", ["prof"]), ("shrink+mom", ["shrink", "mom"]),
              ("shrink+pay+prof", ["shrink", "pay", "prof"]), ("pay+prof", ["pay", "prof"]),
              ("shrink+mom+pay+prof", ["shrink", "mom", "pay", "prof"]), ("mom+pay+prof", ["mom", "pay", "prof"])]
    valid = bbs.notna().sum(axis=1); first = valid.index[valid >= 50].min()
    W = {"all": str(first.date()), "10y": "2016-09-23", "5y": "2021-09-23"}
    rows = []
    for n in (20, 30):
        for name, fl in combos:
            m = bbs.copy()
            for f in fl:
                m = m.where(F[f].reindex(columns=cols).fillna(False))
            h = {}
            for d in MES:
                if d < first: continue
                s = m.loc[d].dropna()
                if len(s) >= n: h[d] = list(s.sort_values(ascending=False).head(n).index)
            usz = m.loc[first:].notna().sum(axis=1).mean()
            out = {}
            for w, st in W.items():
                r = simulate_equal_weight(E.adj, h, month_end_dates(E.all_dates, st, E.END)); r = r[r.index >= pd.Timestamp(st)]
                out[w] = E.stats(r) if len(r) > 12 else (np.nan,) * 4
            rows.append((n, name, usz, len(h), out["all"][0]*100, out["all"][1]*100, out["all"][2], out["all"][3]*100, out["10y"][2], out["5y"][2]))
    df = pd.DataFrame(rows, columns=["N", "filters", "pool", "months", "CAGR", "vol", "Sharpe", "MaxDD", "Sh10y", "Sh5y"])
    df.to_csv("buyback_filters_results.csv", index=False)
    pd.options.display.float_format = "{:.2f}".format
    for n in (20, 30):
        print(f"\n=== top {n} (all data from {first.date()}; pool = avg candidates/month) ==="); print(df[df.N == n].drop(columns="N").to_string(index=False))
