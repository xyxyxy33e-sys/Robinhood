"""Fixing the VIXM rule's weak spot: big BOXX slots in calm, extended markets (mid-2023, mid-2026).

Base rule: VIX < 18 turns the signal ON, VIX > VIX3M turns it OFF; while ON, 50% of the BOXX
slot holds VIXM. Fixes tested:
  cap      VIXM never more than X% of the whole book
  trim     no VIXM on days the BOXX slot looks like the extension trim (state A/B with TQQQ
           well below its normal ratio to SPMO -- the trim pulls TQQQ, the vol target cuts both)
  calm     no VIXM when QQQ's 30-day realized vol is below a threshold (BOXX not there from stress)

    python -m research.regime_tape_vixm_cap
"""
import math

import numpy as np
import pandas as pd
import yfinance as yf

from research.regime_tape_gates import signals
from research.regime_tape_sleeve import fmt, load
from research.regime_tape_vixm import run, summary

SHARE = 0.5


def trim_proxy(d):
    a = (d.s == "A") & (d.wc > 0) & (d.wt < 0.6 * d.wc)      # A is 50/50 SPMO/TQQQ before any trim
    b = (d.s == "B") & (d.wc > 0) & (d.wt < 0.2 * d.wc)      # B is 75/25
    return a | b


def build(d, on, cap=None, block=None):
    w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})
    m = on & ~(block if block is not None else False)
    mv = w.BOXX * SHARE * m
    if cap is not None:
        mv = mv.clip(upper=cap)
    w["VIXM"] += mv
    w["BOXX"] -= mv
    return w


def main():
    d, r = load()
    rf = r.BOXX
    on = signals(d.index)[18]
    q = yf.download("QQQ", start="2016-01-01", end="2026-08-28", progress=False, auto_adjust=True)["Close"].squeeze()
    rv = (q.pct_change().rolling(30).std() * math.sqrt(252)).reindex(d.index).ffill().shift(1)
    trim = trim_proxy(d).shift(1).fillna(False).astype(bool)
    print(f"trim-proxy days: {trim.mean():.0%} of all days; BOXX slot on those days averages {d.wbox[trim].mean():.0%}")
    print(f"share of VIXM-eligible BOXX that is trim-proxy: {(d.wbox * on * trim).sum() / (d.wbox * on).sum():.0%}\n")

    live = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})
    cases = {"Live (all BOXX)": live, "VIXM rule (50% of slot)": build(d, on)}
    for c in (0.10, 0.15, 0.20, 0.25):
        cases[f"cap {int(c * 100)}% of book"] = build(d, on, cap=c)
    cases["skip on trim-proxy days"] = build(d, on, block=trim)
    for th in (0.12, 0.15, 0.20):
        cases[f"skip when QQQ 30d vol < {int(th * 100)}%"] = build(d, on, block=rv < th)
    cases["trim skip + cap 15%"] = build(d, on, cap=0.15, block=trim)
    cases["trim skip + cap 20%"] = build(d, on, cap=0.20, block=trim)

    rows, rets = {}, {}
    for n, w in cases.items():
        x = run(w, r)
        rets[n] = x
        s = summary(x, rf)
        yr = x.resample("YE").apply(lambda z: (1 + z).prod() - 1)
        mo = x.resample("ME").apply(lambda z: (1 + z).prod() - 1)
        s.update({"2023": yr.loc["2023"].iloc[0], "2024": yr.loc["2024"].iloc[0],
                  "Jun 2023": mo.loc["2023-06"].iloc[0], "Aug 2024": mo.loc["2024-08"].iloc[0],
                  "avg VIXM": w.VIXM.mean(), "max VIXM": w.VIXM.max()})
        rows[n] = s
    t = pd.DataFrame(rows).T
    print(fmt(t).to_string())

    base = rows["VIXM rule (50% of slot)"]
    print("\nvs uncapped rule, Sharpe change by half:")
    for n in list(cases)[2:]:
        print(f"   {n:30s} h1 {rows[n]['h1 Sharpe'] - base['h1 Sharpe']:+.3f}  h2 {rows[n]['h2 Sharpe'] - base['h2 Sharpe']:+.3f}")

    m = lambda x: x.loc["2019":].resample("YE").apply(lambda z: (1 + z).prod() - 1)
    yrs = pd.DataFrame({n: m(rets[n]) for n in ["Live (all BOXX)", "VIXM rule (50% of slot)", "skip on trim-proxy days",
                                                "cap 15% of book", "trim skip + cap 20%"]})
    yrs.index = yrs.index.year
    print("\nBy year since 2019:")
    print(yrs.map(lambda v: f"{v:+.1%}").to_string())


if __name__ == "__main__":
    main()
