"""D1 / D2 / D3 at three different mixes (owner, 2026-10-09).

D sub-zones by depth (research/d_substates_dma.py): D1 above the 100-day, D2 between the 100- and
150-day, D3 between the 150- and 200-day. Each zone gets its own row (SPMO, TQQQ, QLD), scaled by
the vol target; the D gate still sends the whole row to cash. Grid:
  D1: 50 / 75 / 100% QLD (rest SPMO)
  D2: 100% QLD | 50% QLD + 50% TQQQ
  D3: 100% QLD | 50% QLD + 50% TQQQ | 100% TQQQ
Live rules otherwise, A 40/60; real ETFs 2015-26 (VIXM on) and the 2001-26 proxy. D3 is rare
(9 gate-off days real, 27 proxy), so its cells rest on very few days.

    python -m research.d_three_levels
"""
import itertools

import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5
from research.d_substates_dma import zones

D1 = {"D1 50% QLD": (0.5, 0.0, 0.5), "D1 75% QLD": (0.25, 0.0, 0.75), "D1 100% QLD": (0.0, 0.0, 1.0)}
D2 = {"D2 100% QLD": (0.0, 0.0, 1.0), "D2 50 QLD/50 TQQQ": (0.0, 0.5, 0.5)}
D3 = {"D3 100% QLD": (0.0, 0.0, 1.0), "D3 50 QLD/50 TQQQ": (0.0, 0.5, 0.5), "D3 100% TQQQ": (0.0, 1.0, 0.0)}


def run_3(P, rows, depth, base=(0.4, 0.6), start="2015-11-02", end="2026-10-07", vixm=True):
    out, prev, held = [], None, None
    for d in (x for x in P["dates"] if start <= x <= end):
        if held is not None:
            rr = P["r"].loc[d, LEGS].values
            g = float(np.dot(held, rr))
            held = held * (1 + rr) / (1 + g)
            out.append([d, g])
        st, fa, gaps = P["st"][d], P["fa"][d], P["gp"][d]
        eff = S.effective_state(st, fa)
        t = dict(P["trim"][d])
        if t["in_a"]:
            t["base"] = base
        bp = P["pct"].get(d)
        gate = S.d_gate_active(st, bp if bp is not None else 1.0, gaps.get(200))
        w5 = S.target_weights_with_voltarget(st, P["mi"][d], P["vol"][d], fast_state=fa, gaps=gaps,
                                             d_gate=gate, a_trim=t)
        z = None
        if eff == "D" and not gate:
            z = depth.get(d)
            c, tq, ql = rows[z]
            m = S.vol_target_multiplier(P["vol"][d])
            w5 = (c * m, tq * m, ql * m, 0.0, 1 - m)
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")), z)
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                out[-1][1] = (1 + out[-1][1]) * (1 - COST * float(np.abs(tgt - held).sum())) - 1
            held = tgt.copy()
        prev = key
    return pd.Series({pd.Timestamp(d): g for d, g in out})


if __name__ == "__main__":
    px = load(); P = prepare(px)
    depth, _, _ = zones(px)
    pd.set_option("display.width", 260)
    res = {}
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.2):
            st_ = stats(run_p(Q, base=(c, round(1 - c, 2)), **kw)); front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        rows, ser = {}, {}
        for (n1, r1), (n2, r2), (n3, r3) in itertools.product(D1.items(), D2.items(), D3.items()):
            s = run_3(Q, {"D1 above 100d": r1, "D2 100-150d": r2, "D3 150-200d": r3}, depth, **kw)
            r = {k: float(v) for k, v in stats(s).items()}
            r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front); r["top-5"] = top5(s)
            nm = f"{n1} | {n2} | {n3}"
            rows[nm] = r; ser[nm] = s
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "h1", "h2", "vs frontier", "top-5"]].round(3).to_string())
    (tr, sr), (tp, sp) = res.values()
    live = "D1 100% QLD | D2 100% QLD | D3 100% QLD"
    print("\nSharpe up on BOTH datasets vs live (D all 100% QLD), with bootstrap P(not better):")
    for nm in tr.index:
        if nm != live and tr.loc[nm, "Sharpe"] > tr.loc[live, "Sharpe"] and tp.loc[nm, "Sharpe"] > tp.loc[live, "Sharpe"]:
            pr = block_boot(sr[nm], sr[live])[1]; pp = block_boot(sp[nm], sp[live])[1]
            print(f"  {nm}: real {tr.loc[nm,'CAGR']*100:.1f}% / {tr.loc[nm,'Sharpe']:.3f} / {tr.loc[nm,'MaxDD']*100:.1f}% (P {pr:.2f});"
                  f" proxy {tp.loc[nm,'CAGR']*100:.1f}% / {tp.loc[nm,'Sharpe']:.3f} / {tp.loc[nm,'MaxDD']*100:.1f}% (P {pp:.2f});"
                  f" vs frontier {tr.loc[nm,'vs frontier']*100:+.1f} / {tp.loc[nm,'vs frontier']*100:+.1f}")
