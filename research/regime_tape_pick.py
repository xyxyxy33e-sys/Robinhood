"""Rebuild the Regime Tape's strategy line for the design released 2026-10-09 ("the pick").

Design: A 25/75 SPMO/TQQQ (trim v2 on that base), D ladder (D1 50% SPMO / 50% QLD, D2 50% TQQQ / 50% QLD,
D3 25/75), D gate, E/F cash, 20/100 re-entry, 20% vol target, VIXM sleeve, 5% band, 4bp, same-session signal.
Driven through paper-track/state.py (target_weights_with_voltarget(..., d_ladder=True)), so it is the live code.
Comparison line: the 8 Oct design (A 50/50, D 100% QLD, VIXM). Window = the page's 29 Aug 2016 - 27 Aug 2026.

    python -m research.regime_tape_pick <artifact.html> <out.json>
"""
import json
import math
import sys

import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare

START, END = "2016-08-29", "2026-08-27"


def replay(P, base, ladder):
    rows, prev, held, nav, reb = [], None, None, 1.0, 0
    for d in (x for x in P["dates"] if START <= x <= END):
        g = 0.0
        if held is not None:
            rr = P["r"].loc[d, LEGS].values
            g = float(np.dot(held, rr))
            held = held * (1 + rr) / (1 + g)
        st, fa, gaps = P["st"][d], P["fa"][d], P["gp"][d]
        eff = S.effective_state(st, fa)
        t = dict(P["trim"][d])
        if t["in_a"]:
            t["base"] = base
        bp = P["pct"].get(d)
        gate = S.d_gate_active(st, bp if bp is not None else 1.0, gaps.get(200))
        w5 = S.target_weights_with_voltarget(st, P["mi"][d], P["vol"][d], fast_state=fa, gaps=gaps,
                                             d_gate=gate, a_trim=t, d_ladder=ladder)
        z = S.d_zone(gaps) if ladder and eff == "D" and not gate else None
        vx = P["vxm"].get(d, {"allowed": False})
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")), z)
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None,
                                     prev is not None and key != prev)
        if do:
            if held is not None:
                g = (1 + g) * (1 - COST * float(np.abs(tgt - held).sum())) - 1
                reb += 1
            held = tgt.copy()
        prev = key
        nav *= 1 + g
        rows.append((d, g, nav, *held, st))
    df = pd.DataFrame(rows, columns=["d", "ret", "nav", *LEGS, "st"]).set_index("d")
    return df, reb / (len(df) / 252)


def stats(ret, rf):
    eq = (1 + ret).cumprod()
    return [round((eq.iloc[-1] ** (252 / len(ret)) - 1) * 100, 1), round(((eq / eq.cummax()) - 1).min() * 100, 1),
            round(float((ret - rf).mean() / ret.std() * math.sqrt(252)), 2)]


if __name__ == "__main__":
    html, out = sys.argv[1], sys.argv[2]
    s = open(html).read()
    i = s.index("const D = ") + 10
    D, _ = json.JSONDecoder().raw_decode(s[i:])
    P = prepare(load())
    new, reb_new = replay(P, (0.25, 0.75), True)
    old, reb_old = replay(P, (0.50, 0.50), False)
    assert list(new.index) == D["d"], "date mismatch with the page"
    mism = sum(a != b for a, b in zip(new.st, D["s"]))
    rf = P["r"].loc[new.index, "BOXX"]
    for nm, df in (("pick", new), ("8 Oct", old)):
        print(nm, stats(df.ret.iloc[1:], rf.iloc[1:]))
    print("page strat stats", D["stats"]["strat"], "| state mismatches vs page:", mism, "| reb/yr", round(reb_new, 1), round(reb_old, 1))
    page_strat = pd.Series(D["strat"], index=D["d"])
    print("page strat vs my 8 Oct replay, end value:", D["strat"][-1], round(old.nav.iloc[-1] / old.nav.iloc[0] * 100, 1))
    pct = lambda x: [int(round(v * 100)) for v in x]
    patch = dict(
        strat=[round(v, 3) for v in (new.nav / new.nav.iloc[0] * 100)],
        base=[round(v, 3) for v in (old.nav / old.nav.iloc[0] * 100)],
        wc=pct(new.SPMO), wt=pct(new.TQQQ), wq=pct(new.QLD), vm=pct(new.VIXM),
        X=[round(a + 3 * b + 2 * c, 2) for a, b, c in zip(new.SPMO, new.TQQQ, new.QLD)],
        stats=dict(D["stats"], strat=stats(new.ret.iloc[1:], rf.iloc[1:]), base=stats(old.ret.iloc[1:], rf.iloc[1:])),
        rebpy=round(reb_new, 1))
    yr = lambda df: ((1 + df.ret).groupby(pd.to_datetime(df.index).year).prod() - 1).round(3).to_dict()
    print("years pick", yr(new)); print("years 8Oct", yr(old))
    print("mean gross pick", round(np.mean(patch["X"]), 2), "| VIXM days", round((new.VIXM > 0).mean() * 100, 1), "%")
    json.dump(patch, open(out, "w"))
