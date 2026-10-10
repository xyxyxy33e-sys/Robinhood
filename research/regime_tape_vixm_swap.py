"""Can VIXM replace anything other than the BOXX slot? Funding the VIXM sleeve from the risky legs.

Base = final live rule (75% of BOXX in VIXM, same-session signal). Each candidate additionally moves a share
of one risky leg (SPMO, TQQQ, QLD, or all of them pro rata) into VIXM while a gate is on. Gates: the live gate
(latch + QQQ vol >= 20% + 25% fade), the latch alone, and the latch with lower vol floors.

    python -m research.regime_tape_vixm_swap
"""
import itertools

import pandas as pd

from research.regime_tape_final_review import COST, gate, market
from research.regime_tape_sleeve import load
from research.regime_tape_vixm import summary


def run(d, r, g_cash, g_risk=None, leg=None, share=0.0):
    w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})
    mv = d.wbox * 0.75 * g_cash
    w["VIXM"] += mv
    w["BOXX"] -= mv
    if leg:
        legs = ["SPMO", "TQQQ", "QLD"] if leg == "all" else [leg]
        for l in legs:
            x = w[l] * share * g_risk
            w[l] -= x
            w["VIXM"] += x
    held = w.shift(1).fillna(0)
    cost = held.diff().abs().sum(axis=1).fillna(0) * COST
    return (held * r[held.columns]).sum(axis=1) - cost


def main():
    d, r = load()
    rf = r.BOXX
    mk = market(d.index)
    g_live = gate(mk, lag=0)
    base = run(d, r, g_live)
    rows = {"live (VIXM in cash only)": summary(base, rf)}
    gates = {"live gate": g_live,
             "latch only": gate(mk, rv_min=0.0, fade=None, lag=0),
             "latch+vol15": gate(mk, rv_min=0.15, lag=0),
             "latch+vol25": gate(mk, rv_min=0.25, lag=0)}
    for (gn, g), leg, sh in itertools.product(gates.items(), ["SPMO", "TQQQ", "QLD", "all"], [0.05, 0.10, 0.20]):
        rows[f"{gn} | {leg} {sh:.0%}"] = summary(run(d, r, g_live, g, leg, sh), rf)
    t = pd.DataFrame(rows).T
    L = t.iloc[0]
    t["both halves"] = (t["h1 Sharpe"] > L["h1 Sharpe"]) & (t["h2 Sharpe"] > L["h2 Sharpe"])
    pd.set_option("display.width", 200)
    print(t.round(3).sort_values("Sharpe", ascending=False).to_string())
    for gn, g in gates.items():
        print(gn, "on", f"{g.mean():.1%}", "of days; risk-leg weight while on:",
              f"{(d.wc + d.wt + d.wq)[g].mean():.2f}", "states:", d.s[g].value_counts().to_dict())


if __name__ == "__main__":
    main()
