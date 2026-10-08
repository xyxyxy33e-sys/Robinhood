"""VIX futures curve, M1..M7: shape, roll decay, crash payoff by tenor, and the ETPs on it.

Data: CBOE per-contract VX settlement files (monthly expiries, 2013+), cached in
research/.cache/. From them we build constant-maturity (CM) points at 30, 60, ... 210
days and a daily-rebalanced CM futures position for each tenor, i.e. what an
unlevered 1x ETN tracking that maturity would earn before fees and T-bill interest.

    python -m research.vix_curve
"""
import datetime as dt
import math
import os
import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests
import yfinance as yf

CACHE = os.path.join(os.path.dirname(__file__), ".cache", "vx")
URL = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{}.csv"
TENORS = range(1, 8)
warnings.simplefilter("ignore", FutureWarning)
EPISODES = [
    ("Aug 2015 China deval", "2015-08-17", "2015-08-25"),
    ("Feb 2018 Volmageddon", "2018-02-01", "2018-02-09"),
    ("Dec 2018 selloff", "2018-12-01", "2018-12-24"),
    ("Mar 2020 Covid", "2020-02-21", "2020-03-18"),
    ("Aug 2024 yen unwind", "2024-07-31", "2024-08-05"),
    ("Apr 2025 tariffs", "2025-04-02", "2025-04-08"),
    ("Mar 2026 spike", "2026-03-02", "2026-03-27"),
]


def expiry(y: int, m: int) -> dt.date:
    """Standard monthly VX expiry: the Wednesday 30 days before the next month's 3rd Friday."""
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    d = dt.date(ny, nm, 15)
    d += dt.timedelta((4 - d.weekday()) % 7)
    return d - dt.timedelta(30)


def fetch_one(y: int, m: int):
    os.makedirs(CACHE, exist_ok=True)
    e = expiry(y, m)
    for back in range(3):  # holiday -> previous business day
        d = e - dt.timedelta(back)
        path = os.path.join(CACHE, f"VX_{d}.csv")
        if os.path.exists(path):
            return d, pd.read_csv(path)
        r = requests.get(URL.format(d), timeout=30)
        if r.ok and r.text.startswith("Trade Date"):
            with open(path, "w") as f:
                f.write(r.text)
            return d, pd.read_csv(path)
    return None


def load_futures(start=2013) -> pd.DataFrame:
    """Settle prices: index = trade date, columns = expiry date."""
    today = dt.date.today()
    months = [(y, m) for y in range(start, today.year + 2) for m in range(1, 13)]
    with ThreadPoolExecutor(16) as ex:
        got = [g for g in ex.map(lambda ym: fetch_one(*ym), months) if g]
    cols = {}
    for exp, df in got:
        s = df.set_index(pd.to_datetime(df["Trade Date"]))["Settle"].astype(float)
        cols[pd.Timestamp(exp)] = s[s > 0]
    return pd.DataFrame(cols).sort_index().sort_index(axis=1)


def bracket(row: pd.Series, date, days: int):
    """Two listed contracts around `date + days`, with linear weights by days to expiry."""
    live = row.dropna()
    dte = pd.Series((live.index - date).days, index=live.index)
    live, dte = live[dte > 0], dte[dte > 0]
    if len(live) < 2:
        return None
    hi = dte[dte >= days]
    if hi.empty:
        return None
    b = hi.index[0]
    lo = dte[dte < days]
    if lo.empty:
        return {b: 1.0}
    a = lo.index[-1]
    w = (dte[b] - days) / (dte[b] - dte[a])
    return {a: w, b: 1 - w}


def constant_maturity(fut: pd.DataFrame):
    """CM curve levels and daily returns of CM positions, one column per tenor M1..M7."""
    lvl = {k: {} for k in TENORS}
    ret = {k: {} for k in TENORS}
    prev_w = {k: None for k in TENORS}
    prev_row = None
    for date, row in fut.iterrows():
        for k in TENORS:
            w = bracket(row, date, 30 * k)
            if w:
                lvl[k][date] = sum(row[c] * x for c, x in w.items())
            pw = prev_w[k]
            if pw and prev_row is not None and all(pd.notna(row.get(c)) and pd.notna(prev_row.get(c)) for c in pw):
                ret[k][date] = sum(x * row[c] for c, x in pw.items()) / sum(x * prev_row[c] for c, x in pw.items()) - 1
            prev_w[k] = w
        prev_row = row
    name = lambda d: pd.DataFrame(d).rename(columns=lambda k: f"M{k}")
    return name(lvl), name(ret).fillna(0)


def stats(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    return {
        "CAGR": eq.iloc[-1] ** (252 / len(r)) - 1,
        "Vol": r.std() * math.sqrt(252),
        "MaxDD": (eq / eq.cummax() - 1).min(),
        "WorstDay": r.min(),
        "BestDay": r.max(),
    }


def pct(df, cols=None, digits=0):
    f = ("{:+.%df}%%" % digits).replace("%%", "%")
    out = df.copy()
    for c in cols or out.columns:
        out[c] = out[c].map(lambda x: "" if pd.isna(x) else f.format(x * 100).replace("%", "") + "%")
    return out


def main():
    fut = load_futures()
    lvl, ret = constant_maturity(fut)
    mkt = yf.download(["^VIX", "SPY"], start=str(lvl.index[0].date()), progress=False, auto_adjust=True)["Close"]
    mkt.columns = ["spy", "vix"] if list(mkt.columns) == ["SPY", "^VIX"] else [c.lower().strip("^") for c in mkt.columns]
    idx = lvl.dropna().index.intersection(mkt.index)
    lvl, ret, mkt = lvl.loc[idx], ret.reindex(idx).fillna(0), mkt.loc[idx]
    spy, dvix = mkt.spy.pct_change().fillna(0), mkt.vix.pct_change().fillna(0)
    print(f"VX curve {idx[0].date()} -> {idx[-1].date()} ({len(idx)} days, {fut.shape[1]} contracts)\n")

    # 1. shape
    rel = lvl.div(mkt.vix, axis=0)
    shape = pd.DataFrame({
        "avg level": lvl.mean(),
        "vs spot VIX (median)": rel.median() - 1,
        "roll-down /mo (median)": (lvl.shift(-1, axis=1) / lvl - 1).median().shift(1),
    })
    shape["roll-down /mo (median)"] = [(lvl[f"M{k}"] / lvl[f"M{k-1}"] - 1).median() if k > 1 else (lvl.M1 / mkt.vix - 1).median() for k in TENORS]
    contango = pd.Series({f"M{k}>M{k-1}": (lvl[f"M{k}"] > lvl[f"M{k-1}"]).mean() for k in range(2, 8)})
    print("1) Curve shape: futures sit above spot, and the slope is steepest at the front")
    print(pd.concat([shape["avg level"].round(2), pct(shape[["vs spot VIX (median)", "roll-down /mo (median)"]], digits=1)], axis=1).to_string())
    print("\n   share of days each step is upward-sloping (contango):")
    print("   " + "  ".join(f"{k} {v:.0%}" for k, v in contango.items()))
    back = (lvl.M1 > lvl.M2)
    print(f"   front in backwardation (M1>M2): {back.mean():.1%} of days; M4>M7: {(lvl.M4 > lvl.M7).mean():.1%}")

    # 2. long each tenor
    tbl = pd.DataFrame({k: stats(ret[k]) for k in ret}).T
    tbl["Beta to VIX %chg"] = [ret[k].cov(dvix) / dvix.var() for k in ret]
    tbl["Corr SPY"] = [ret[k].corr(spy) for k in ret]
    print("\n2) Long 1x constant-maturity futures by tenor (before fees and T-bill interest)")
    print(pd.concat([pct(tbl[["CAGR", "Vol", "MaxDD", "WorstDay", "BestDay"]]), tbl[["Beta to VIX %chg", "Corr SPY"]].round(2)], axis=1).to_string())

    # 3. crash payoff vs bleed
    ep = pd.DataFrame({name: (1 + ret.loc[a:b]).prod() - 1 for name, a, b in EPISODES}).T
    ep["SPY"] = [(1 + spy.loc[a:b]).prod() - 1 for _, a, b in EPISODES]
    print("\n3) Long-vol payoff in spikes")
    print(pct(ep).to_string())
    bleed = ret.apply(lambda r: (1 + r).prod() ** (252 / len(r)) - 1)
    eff = ep[[c for c in ep.columns if c != "SPY"]].mean() / -bleed
    print("\n   avg spike payoff / annual bleed (higher = cheaper insurance):  " + "  ".join(f"{k} {v:.1f}" for k, v in eff.items()))

    # 4. short side and calendar spreads
    print("\n4) Short side and spreads (daily rebalanced, unlevered collateral)")
    rows = {}
    for k in [1, 2, 4, 5]:
        for lev in [0.5, 1.0]:
            rows[f"short {lev}x M{k}"] = -lev * ret[f"M{k}"]
    beta = {k: (ret[f"M{k}"].cov(ret.M1) / ret.M1.var()) for k in [4, 5, 7]}
    for k, b in beta.items():
        rows[f"short M1 + long {1/b:.2f}x M{k} (beta-neutral)"] = -ret.M1 + ret[f"M{k}"] / b
        rows[f"short 0.5x M1 + long 0.5x M{k} (equal $)"] = 0.5 * (-ret.M1 + ret[f"M{k}"])
    rows["short 0.5x M2 + long 0.5x M5"] = 0.5 * (-ret.M2 + ret.M5)
    s = pd.DataFrame({k: stats(v) for k, v in rows.items()}).T
    s["Corr SPY"] = [v.corr(spy) for v in rows.values()]
    s["Feb 2018"] = [(1 + v.loc["2018-02-01":"2018-02-09"]).prod() - 1 for v in rows.values()]
    s["Mar 2020"] = [(1 + v.loc["2020-02-21":"2020-03-18"]).prod() - 1 for v in rows.values()]
    print(pd.concat([pct(s[["CAGR", "Vol", "MaxDD", "WorstDay", "Feb 2018", "Mar 2020"]]), s[["Corr SPY"]].round(2)], axis=1).to_string())

    # 5. the ETP landscape, checked against the CM indices
    etps = {"VXX": ("M1", 1), "VIXY": ("M1", 1), "UVXY": ("M1", 1.5), "UVIX": ("M1", 2), "SVXY": ("M1", -0.5),
            "SVIX": ("M1", -1), "VYLD": ("M1", -1), "SVOL": ("M2-3", None), "VIXM": ("M5", 1), "VXZ": ("M5", 1), "ZVOL": ("M5", -1)}
    px = yf.download(list(etps), start="2011-01-01", progress=False, auto_adjust=True)["Close"]
    rows = []
    for t, (ten, lev) in etps.items():
        p = px[t].dropna()
        r = p.pct_change().dropna()
        st = stats(r)
        cm = ret.get(ten if ten in ret else "M2")
        both = pd.concat([r, cm], axis=1).dropna()
        track = both.iloc[:, 0].corr(both.iloc[:, 1]) if lev else np.nan
        rows.append({"ETP": t, "tenor": ten, "lev": lev if lev else "dyn", "since": p.index[0].date(), **st,
                     "corr w/ CM tenor": track * (np.sign(lev) if lev else 1)})
    e = pd.DataFrame(rows).set_index("ETP")
    print("\n5) VIX ETPs on the curve (actual prices, after fees)")
    print(pd.concat([e[["tenor", "lev", "since"]], pct(e[["CAGR", "MaxDD", "WorstDay"]]), e[["corr w/ CM tenor"]].round(2)], axis=1).to_string())


if __name__ == "__main__":
    main()
