"""VIX vs VXN as the VIXM entry gate (and as the stress filter) in the Regime Tape BOXX slot.

The book is Nasdaq-heavy (SPMO/TQQQ/QLD), so VXN (Nasdaq-100 implied vol) may describe its risk
better than VIX (S&P 500). VXN has no tradable futures and no 3-month index, so it can only
replace the VIX *level* parts of the rule; VIXM stays the instrument and VIX > VIX3M stays the
exit unless noted.

    python -m research.regime_tape_vxn
"""
import math

import pandas as pd
import yfinance as yf

from research.regime_tape_sleeve import fmt, load
from research.regime_tape_vixm import run, summary

SHARE = 0.5


def latch(entry, exit_, idx):
    on, out = False, []
    for e, x in zip(entry, exit_):
        if not on and e and not x:
            on = True
        elif on and x:
            on = False
        out.append(on)
    return pd.Series(out, index=entry.index).reindex(idx).ffill().shift(1).fillna(False).astype(bool)


def main():
    d, r = load()
    rf = r.BOXX
    v = yf.download(["^VIX", "^VIX3M", "^VXN", "QQQ"], start="2015-06-01", end="2026-08-28", progress=False, auto_adjust=True)["Close"].ffill()
    vix, vix3m, vxn = v["^VIX"], v["^VIX3M"], v["^VXN"]
    rv = (v.QQQ.pct_change().rolling(30).std() * math.sqrt(252)).reindex(d.index).ffill().shift(1)
    spread = (vxn - vix)
    print(f"VXN minus VIX: median {spread.median():.1f} pts, 10-90% range {spread.quantile(.1):.1f} to {spread.quantile(.9):.1f}; "
          f"VIX<18 matches VXN<{vxn[vix < 18].quantile(.9):.0f} (90th pct)\n")
    inv = vix > vix3m

    def case(on, stress=None):
        w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})
        m = on & (stress if stress is not None else True)
        mv = w.BOXX * SHARE * m
        w["VIXM"] += mv
        w["BOXX"] -= mv
        return w

    stress_rv = rv >= 0.20
    vxn_l = vxn.reindex(d.index).ffill().shift(1)
    cases = {"Live (all BOXX)": pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})}
    for g in (16, 18, 20):
        cases[f"VIX<{g}"] = case(latch(vix < g, inv, d.index))
    for g in (20, 22, 24, 26):
        cases[f"VXN<{g}"] = case(latch(vxn < g, inv, d.index))
    cases["VIX<18 + QQQ rv>=20% (prev. rec.)"] = case(latch(vix < 18, inv, d.index), stress_rv)
    for g in (22, 24):
        cases[f"VXN<{g} + QQQ rv>=20%"] = case(latch(vxn < g, inv, d.index), stress_rv)
    for s in (20, 22, 24):
        cases[f"VIX<18 + VXN>={s} (implied stress)"] = case(latch(vix < 18, inv, d.index), vxn_l >= s)
    # exit on Nasdaq stress instead of S&P curve inversion
    for k in (1.15, 1.25):
        cases[f"VXN<22, exit VXN>{k}xVIX3M"] = case(latch(vxn < 22, vxn > k * vix3m, d.index))

    rows = {}
    for n, w in cases.items():
        x = run(w, r)
        s = summary(x, rf)
        yr = x.resample("YE").apply(lambda z: (1 + z).prod() - 1)
        mo = x.resample("ME").apply(lambda z: (1 + z).prod() - 1)
        s.update({"2023": yr.loc["2023"].iloc[0], "2024": yr.loc["2024"].iloc[0], "Jun 2023": mo.loc["2023-06"].iloc[0],
                  "Aug 2024": mo.loc["2024-08"].iloc[0], "avg VIXM": w.VIXM.mean()})
        rows[n] = s
    print(fmt(pd.DataFrame(rows).T).to_string())


if __name__ == "__main__":
    main()
