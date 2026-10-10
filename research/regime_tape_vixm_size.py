"""VIXM share of the BOXX slot, with the stress filter on.

Rule: VIX < 18 turns the signal ON, VIX > VIX3M turns it OFF; VIXM only while QQQ 30-day
realized vol >= 20%. This sweeps the VIXM share of the BOXX slot from 0 to 100%.

    python -m research.regime_tape_vixm_size
"""
import math

import pandas as pd
import yfinance as yf

from research.regime_tape_gates import signals
from research.regime_tape_sleeve import fmt, load
from research.regime_tape_vixm import run, summary

EVENTS = [("Q4 2018", "2018-10-01", "2018-12-24"), ("2022 bear", "2022-01-03", "2022-10-14"),
          ("Aug 2024", "2024-07-10", "2024-08-07"), ("Apr 2025", "2025-02-19", "2025-04-08")]


def main():
    d, r = load()
    rf = r.BOXX
    on = signals(d.index)[18]
    q = yf.download("QQQ", start="2016-01-01", end="2026-08-28", progress=False, auto_adjust=True)["Close"].squeeze()
    rv = (q.pct_change().rolling(30).std() * math.sqrt(252)).reindex(d.index).ffill().shift(1)
    gate = on & (rv >= 0.20)
    rows, yrs, worst_m = {}, {}, {}
    for share in (0, .25, .5, .6, .75, .9, 1.0):
        w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})
        mv = d.wbox * share * gate
        w["VIXM"] = mv
        w["BOXX"] -= mv
        x = run(w, r)
        s = summary(x, rf)
        mo = x.resample("ME").apply(lambda z: (1 + z).prod() - 1)
        s.update({lab: (1 + x.loc[a:b]).prod() - 1 for lab, a, b in EVENTS})
        s["Worst month"] = mo.min()
        s["max VIXM"] = w.VIXM.max()
        name = f"{int(share * 100)}% of slot"
        rows[name] = s
        yrs[name] = x.resample("YE").apply(lambda z: (1 + z).prod() - 1)
        worst_m[name] = mo
    print(fmt(pd.DataFrame(rows).T).to_string())
    y = pd.DataFrame(yrs)
    y.index = y.index.year
    print("\nBy year:")
    print(y.map(lambda v: f"{v:+.1%}").to_string())
    m = pd.DataFrame(worst_m)
    diff = m.sub(m["0% of slot"], axis=0) * 100
    print("\nMonths where 100% differs most from live (pp):")
    print(diff["100% of slot"].abs().nlargest(8).index.strftime("%Y-%m").tolist())
    print(diff.loc[diff["100% of slot"].abs().nlargest(8).index].round(1).rename(lambda i: i.strftime("%Y-%m")).to_string())


if __name__ == "__main__":
    main()
