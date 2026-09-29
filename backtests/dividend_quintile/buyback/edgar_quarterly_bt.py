"""
Buyback signal compositions, point-in-time from SEC EDGAR, rebalanced monthly.

Discrete quarterly repurchases are derived from cumulative (YTD) cash-flow facts:
Q1=3m, Q2=6m-3m, Q3=9m-6m, Q4=FY-9m. A quarter becomes known on the filing
date of the later fact. At each month-end, the latest 4 known quarters
(q0 newest ... q3) give the signals, all divided by market cap (price x
latest filed share count):

  ttm        : (q0+q1+q2+q3) / cap                     (baseline)
  recent1    : 4*q0 / cap                              (latest quarter annualized)
  recent2    : 2*(q0+q1) / cap                         (last two quarters)
  weighted   : 4*(.5*q0+.25*q1+.15*q2+.10*q3) / cap    (recency-decayed)
  blend      : 0.5*pct-rank(recent1) + 0.5*pct-rank(ttm)
  ttm_cons   : ttm, but require buybacks in >=3 of last 4 quarters
  weighted_cons : weighted + same consistency requirement
  accel      : weighted, but only names where q0 >= mean(q1..q3) (spending not fading)
"""
import json
import numpy as np, pandas as pd
from backtest import load_data, month_end_dates, simulate_equal_weight

END = "2026-09-23"
close, adj, div, spy_adj = load_data()
all_dates = close.index
mes = month_end_dates(all_dates, all_dates.min(), END)
facts = json.load(open("edgar_facts.json"))


def discrete_quarters(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["end", "filed", "q"])
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c])
    df["dur"] = (df["end"] - df["start"]).dt.days
    df = df[(df["dur"] > 60) & (df["dur"] < 380)]
    df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="first")
    out = []
    for _, g in df.groupby("start"):
        g = g.sort_values("end")
        prev_end, prev_val = None, 0.0
        for _, r in g.iterrows():
            gap = (r["end"] - (prev_end if prev_end is not None else r["start"])).days
            if 75 <= gap <= 105:
                out.append((r["end"], r["filed"], r["val"] - prev_val))
            prev_end, prev_val = r["end"], r["val"]
    q = pd.DataFrame(out, columns=["end", "filed", "q"]).sort_values("end")
    return q.drop_duplicates("end", keep="first").reset_index(drop=True)


def signals_for(t):
    d = facts[t]
    n = len(mes)
    Q = np.full((n, 4), np.nan)                 # q0..q3 at each month-end
    SH = np.full(n, np.nan)
    if not d["rep"] or not d["shares"] or t not in close.columns:
        return t, Q, SH
    q = discrete_quarters(d["rep"])
    if len(q) < 4:
        return t, Q, SH
    q_end = q["end"].values
    q_val = q["q"].values
    q_filed_cum = np.maximum.accumulate(q["filed"].values)
    sh = pd.DataFrame(d["shares"])
    for c in ("end", "filed"):
        sh[c] = pd.to_datetime(sh[c])
    sh = sh.sort_values("filed")
    sh_filed = sh["filed"].values
    sh_end_cum = np.maximum.accumulate(sh["end"].values)
    sh_val = sh["val"].values
    mes_v = mes.values
    k = np.searchsorted(q_filed_cum, mes_v, side="right")        # quarters known at dt
    ks = np.searchsorted(sh_filed, mes_v, side="right")
    for i in range(n):
        if k[i] >= 4:
            ends = q_end[k[i] - 4:k[i]]
            gaps = np.diff(ends).astype("timedelta64[D]").astype(int)
            fresh = (mes_v[i] - ends[-1]).astype("timedelta64[D]").astype(int) <= 200
            if fresh and np.all((gaps > 75) & (gaps < 105)):
                Q[i] = q_val[k[i] - 4:k[i]][::-1]                # q0 newest first
        if ks[i] > 0 and (mes_v[i] - sh_end_cum[ks[i] - 1]).astype("timedelta64[D]").astype(int) <= 200:
            SH[i] = sh_val[ks[i] - 1]
    return t, Q, SH


def build_panels():
    from multiprocessing import Pool
    with Pool(4) as p:
        res = p.map(signals_for, list(facts.keys()))
    tick = [r[0] for r in res]
    Q = np.stack([r[1] for r in res], axis=2)                     # (months, 4, tickers)
    SH = np.stack([r[2] for r in res], axis=1)                    # (months, tickers)
    px = close.reindex(mes)[tick].values
    cap = px * SH
    cols = lambda a: pd.DataFrame(a, index=mes, columns=tick)
    q0, q1, q2, q3 = (cols(Q[:, j, :]) for j in range(4))
    cap = cols(cap)
    return q0, q1, q2, q3, cap


def make_scores(q0, q1, q2, q3, cap):
    ttm = (q0 + q1 + q2 + q3) / cap
    recent1 = 4 * q0 / cap
    recent2 = 2 * (q0 + q1) / cap
    weighted = 4 * (0.5 * q0 + 0.25 * q1 + 0.15 * q2 + 0.10 * q3) / cap
    blend = 0.5 * recent1.rank(axis=1, pct=True) + 0.5 * ttm.rank(axis=1, pct=True)
    cons = ((q0 > 0).astype(int) + (q1 > 0) + (q2 > 0) + (q3 > 0)) >= 3
    accel = q0 >= (q1 + q2 + q3) / 3
    sc = {
        "ttm": ttm, "recent1": recent1, "recent2": recent2, "weighted": weighted,
        "blend": blend, "ttm_cons": ttm.where(cons), "weighted_cons": weighted.where(cons),
        "accel": weighted.where(accel & (q0 > 0)),
    }
    for k in ("ttm", "recent1", "recent2", "weighted", "ttm_cons", "weighted_cons", "accel"):
        s = sc[k]
        sc[k] = s.where((s > 0) & (s < 0.5))                       # drop non-positive and >50% (data errors)
    return sc


def stats(r):
    n_years = (r.index[-1] - r.index[0]).days / 365.25
    cum = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (1 / n_years) - 1
    vol = r.std() * np.sqrt(len(r) / n_years)
    sharpe = r.mean() * (len(r) / n_years) / vol
    return cagr, vol, sharpe, (cum / cum.cummax() - 1).min()


def holdings(score, n, start):
    h = {}
    for dt in mes:
        if dt < start:
            continue
        s = score.loc[dt].dropna()
        if len(s) >= max(n, 50):
            h[dt] = list(s.sort_values(ascending=False).head(n).index)
    return h


if __name__ == "__main__":
    q0, q1, q2, q3, cap = build_panels()
    sc = make_scores(q0, q1, q2, q3, cap)
    valid = sc["ttm"].notna().sum(axis=1)
    first = valid.index[valid >= 50].min()
    print("names with valid signal per year:", valid.groupby(valid.index.year).mean().round(0).to_dict())
    print("first month with >=50 valid names:", first.date())
    WINDOWS = {"all data": str(first.date()), "10y": "2016-09-23", "5y": "2021-09-23"}
    rows = []
    for name, s in sc.items():
        for n in (20, 30, 50):
            h = holdings(s, n, first)
            for w, st in WINDOWS.items():
                r = simulate_equal_weight(adj, h, month_end_dates(all_dates, st, END))
                r = r[r.index >= pd.Timestamp(st)]
                if len(r) > 12:
                    rows.append((name, n, w, *stats(r)))
    for w, st in WINDOWS.items():
        r = spy_adj.reindex(month_end_dates(all_dates, st, END)).pct_change().dropna()
        r = r[r.index >= pd.Timestamp(st)]
        rows.append(("SPY", 0, w, *stats(r)))
    df = pd.DataFrame(rows, columns=["signal", "n", "window", "cagr", "vol", "sharpe", "maxdd"])
    df.to_csv("edgar_quarterly_results.csv", index=False)
    pd.options.display.float_format = "{:.3f}".format
    for w in WINDOWS:
        d = df[df.window == w]
        print(f"\n=== {w} ===")
        print(d.pivot(index="signal", columns="n", values="sharpe").round(2).to_string())
    print("\n--- N=30 detail ---")
    print(df[df.n.isin([30, 0])].sort_values(["window", "sharpe"], ascending=[True, False]).to_string(index=False))
