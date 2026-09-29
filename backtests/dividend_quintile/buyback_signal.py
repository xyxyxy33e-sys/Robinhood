"""
Point-in-time buyback signals from SEC EDGAR facts (see buyback/edgar_quarterly_bt.py
for the original research version). Used by the research scripts and the live
shadow portfolio.

Signals per stock at a date (latest 4 known quarterly repurchase amounts q0..q3
divided by market cap = price x latest filed share count):
  ttm      = (q0+q1+q2+q3)/cap
  recent1  = 4*q0/cap
  weighted = 4*(.5q0+.25q1+.15q2+.10q3)/cap
  blend    = 0.5*pct-rank(recent1) + 0.5*pct-rank(ttm), restricted to names with valid ttm
Valid ttm means 0 < ttm < 0.5 (drops non-positive and >50% as data errors).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent / ".cache"
FACTS = CACHE / "edgar_facts.json"


def load_facts(path=FACTS):
    return json.load(open(path))


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


def _one(args):
    t, d, dates_v = args
    n = len(dates_v)
    Q, SH = np.full((n, 4), np.nan), np.full(n, np.nan)
    if not d.get("rep") or not d.get("shares"):
        return t, Q, SH
    q = discrete_quarters(d["rep"])
    if len(q) < 4:
        return t, Q, SH
    q_end, q_val = q["end"].values, q["q"].values
    q_filed = np.maximum.accumulate(q["filed"].values)
    sh = pd.DataFrame(d["shares"])
    for c in ("end", "filed"):
        sh[c] = pd.to_datetime(sh[c])
    sh = sh.sort_values("filed")
    sh_filed, sh_val = sh["filed"].values, sh["val"].values
    sh_end = np.maximum.accumulate(sh["end"].values)
    k = np.searchsorted(q_filed, dates_v, side="right")
    ks = np.searchsorted(sh_filed, dates_v, side="right")
    days = lambda a, b: (a - b).astype("timedelta64[D]").astype(int)
    for i in range(n):
        if k[i] >= 4:
            ends = q_end[k[i] - 4:k[i]]
            gaps = np.diff(ends).astype("timedelta64[D]").astype(int)
            if days(dates_v[i], ends[-1]) <= 200 and np.all((gaps > 75) & (gaps < 105)):
                Q[i] = q_val[k[i] - 4:k[i]][::-1]
        if ks[i] > 0 and days(dates_v[i], sh_end[ks[i] - 1]) <= 200:
            SH[i] = sh_val[ks[i] - 1]
    return t, Q, SH


def panels(close, dates, facts=None, procs=4):
    """q0..q3 and market-cap panels (dates x tickers) for the given dates."""
    from multiprocessing import Pool
    facts = facts or load_facts()
    dates = pd.DatetimeIndex(dates)
    tick = [t for t in facts if t in close.columns]
    with Pool(procs) as p:
        res = p.map(_one, [(t, facts[t], dates.values) for t in tick])
    Q = np.stack([r[1] for r in res], axis=2)
    SH = np.stack([r[2] for r in res], axis=1)
    px = close.reindex(dates, method="ffill")[tick].values
    mk = lambda a: pd.DataFrame(a, index=dates, columns=tick)
    return [mk(Q[:, j, :]) for j in range(4)] + [mk(px * SH)]


def scores(q0, q1, q2, q3, cap):
    ttm = (q0 + q1 + q2 + q3) / cap
    recent1 = 4 * q0 / cap
    weighted = 4 * (0.5 * q0 + 0.25 * q1 + 0.15 * q2 + 0.10 * q3) / cap
    blend = 0.5 * recent1.rank(axis=1, pct=True) + 0.5 * ttm.rank(axis=1, pct=True)
    ok = ttm.where((ttm > 0) & (ttm < 0.5)).notna()
    out = {"ttm": ttm, "recent1": recent1, "weighted": weighted, "blend": blend}
    out = {k: v.where(ok) for k, v in out.items()}
    out["cap"] = cap
    return out
