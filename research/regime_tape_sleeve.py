"""Swap what sits in the BOXX slot of the live "Regime Tape" design (23 Sep 2026).

Daily weights come from the Regime Tape artifact (research/data/regime_tape_weights.csv:
wc = SPMO, wt = TQQQ, wq = QLD, all in %; BOXX = the remainder). Those weights already
include every overlay (vol target, extension trim, D gate, fast re-entry, drift band), so
this changes nothing about the risk decisions -- only what the idle money holds.

Price-only returns like the page, BOXX at the 13-week T-bill, weights set at a close earn
the next session, 4 bp one-way cost on every weight change (including the swapped sleeve).

    python -m research.regime_tape_sleeve
"""
import math
import os
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

from research.vix_improve import load as load_vol, run as run_vol

warnings.simplefilter("ignore")
HERE = os.path.dirname(__file__)
COST = 0.0004


def load():
    d = pd.read_csv(os.path.join(HERE, "data", "regime_tape_weights.csv"), index_col=0, parse_dates=True)
    for c in ["wc", "wt", "wq"]:
        d[c] = d[c] / 100
    d["wbox"] = (1 - d.wc - d.wt - d.wq).clip(lower=0)
    px = yf.download(["SPMO", "TQQQ", "QLD", "IAU", "IEF", "VIXM", "^IRX"], start="2016-06-01", end="2026-08-28",
                     progress=False, auto_adjust=False)["Close"]
    r = px.drop(columns="^IRX").pct_change().reindex(d.index)
    r["BOXX"] = (px["^IRX"].ffill() / 100 / 252).reindex(d.index).fillna(0)
    vol = load_vol()
    r["VIXSW"] = run_vol(vol, long_mode="confirm2", side="cash")[0].reindex(d.index).fillna(r.BOXX)
    return d, r.fillna(0)


def replay(d, r, sleeve, by_state=None):
    """sleeve: {asset: share of the BOXX slot}. by_state: {state: sleeve} overrides."""
    w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq})
    assets = sorted({a for s in [sleeve, *(by_state or {}).values()] for a in s})
    for a in assets:
        w[a] = 0.0
    for st in d.s.unique():
        sl = (by_state or {}).get(st, sleeve)
        m = d.s == st
        for a, x in sl.items():
            w.loc[m, a] += d.wbox[m] * x
    held = w.shift(1).fillna(0)
    gross = (held * r[held.columns]).sum(axis=1)
    return gross - held.diff().abs().sum(axis=1).fillna(0) * COST


def stats(x, rf):
    eq = (1 + x).cumprod()
    yr = x.resample("YE").apply(lambda s: (1 + s).prod() - 1)
    return {"CAGR": eq.iloc[-1] ** (252 / len(x)) - 1, "MaxDD": (eq / eq.cummax() - 1).min(),
            "Sharpe": (x - rf).mean() / x.std() * math.sqrt(252), "Worst 12m": (eq / eq.shift(252) - 1).min(),
            **{str(y): yr.get(pd.Timestamp(f"{y}-12-31"), np.nan) for y in (2018, 2020, 2022, 2025)}}


def fmt(t):
    t = t.copy()
    for c in t.columns:
        t[c] = t[c].map(lambda x: f"{x:.2f}" if "Sharpe" in c else f"{x:+.1%}")
    return t


def main():
    d, r = load()
    rf = r.BOXX
    print(f"{d.index[0].date()} -> {d.index[-1].date()}; BOXX slot averages {d.wbox.mean():.0%} of the book "
          f"(A {d.wbox[d.s == 'A'].mean():.0%}, D {d.wbox[d.s == 'D'].mean():.0%}, E {d.wbox[d.s == 'E'].mean():.0%}, F {d.wbox[d.s == 'F'].mean():.0%})\n")
    base = replay(d, r, {"BOXX": 1})
    page = d.strat.pct_change().fillna(0)
    print(f"replay vs page: daily corr {base.corr(page):.4f}, CAGR {stats(base, rf)['CAGR']:+.1%} vs page {stats(page, rf)['CAGR']:+.1%}\n")

    weak = {"E": {"IAU": 1}, "F": {"IAU": 1}}
    cands = {
        "BOXX (live)": ({"BOXX": 1}, None),
        "Gold (IAU)": ({"IAU": 1}, None),
        "50 BOXX / 50 gold": ({"BOXX": .5, "IAU": .5}, None),
        "Gold only in E/F, BOXX elsewhere": ({"BOXX": 1}, weak),
        "50/50 gold in E/F, BOXX elsewhere": ({"BOXX": 1}, {"E": {"BOXX": .5, "IAU": .5}, "F": {"BOXX": .5, "IAU": .5}}),
        "7-10y Treasuries (IEF)": ({"IEF": 1}, None),
        "Improved VIX switch": ({"VIXSW": 1}, None),
        "70 BOXX / 30 VIX switch": ({"BOXX": .7, "VIXSW": .3}, None),
        "VIX switch only in E/F": ({"BOXX": 1}, {"E": {"VIXSW": 1}, "F": {"VIXSW": 1}}),
        "80 BOXX / 20 VIXM": ({"BOXX": .8, "VIXM": .2}, None),
    }
    out, runs = {}, {}
    for n, (sl, bs) in cands.items():
        runs[n] = replay(d, r, sl, bs)
        out[n] = stats(runs[n], rf)
    print("Full window (2016-08 -> 2026-08):")
    print(fmt(pd.DataFrame(out).T).to_string())

    print("\nEach half:")
    h = {}
    for n, x in runs.items():
        h[n] = {f"{a[:4]}-{b[:4]} {k}": v for a, b in [("2016-08-29", "2021-06-30"), ("2021-07-01", "2026-08-27")]
                for k, v in stats(x.loc[a:b], rf.loc[a:b]).items() if k in ("CAGR", "MaxDD", "Sharpe")}
    print(fmt(pd.DataFrame(h).T).to_string())

    print("\nWhat the BOXX slot itself earned while held, by state (annualised, weighted by slot size):")
    for n in ["Gold (IAU)", "Improved VIX switch", "7-10y Treasuries (IEF)"]:
        a = {"Gold (IAU)": "IAU", "Improved VIX switch": "VIXSW", "7-10y Treasuries (IEF)": "IEF"}[n]
        row = []
        for st in "ADEF":
            m = (d.s.shift(1) == st) & (d.wbox.shift(1) > 0)
            ex = (r[a] - r.BOXX)[m]
            row.append(f"{st} {ex.mean() * 252:+.1%}")
        print(f"   {a:6s} excess over BOXX: " + "  ".join(row))


if __name__ == "__main__":
    main()
