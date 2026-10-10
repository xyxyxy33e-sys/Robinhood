"""30/70 A row that STEPS DOWN to a lighter base (50/50 or 40/60) on an early warning instead of
exiting; the live trim v2 still does the full exit on top (owner, 2026-10-09).

Same replay and the same early-warning arms as research/a7030_quick_exit.py. While the warning is
on, the A base row becomes `step` (so at held votes >= 1 the usual trim rows of that base apply);
the switch is a regime change and trades the same session. Judged against the plain-ratio frontier
(CAGR at equal max drawdown) on real ETFs and on the 2001-2026 proxy.

    python -m research.a7030_step_down
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import ARMS, indicators, make_arm, name, frontier_cagr_at


def run_step(P, ind, base, step=None, arm=None, start="2015-11-02", end="2026-10-07", vixm=True):
    out, prev, held = [], None, None
    nav, peak, on = 1.0, 1.0, False
    sim = [d for d in P["dates"] if start <= d <= end]
    for d in sim:
        if held is not None:
            rr = P["r"].loc[d, LEGS].values
            g = float(np.dot(held, rr))
            held = held * (1 + rr) / (1 + g)
            out.append([d, g]); nav *= 1 + g; peak = max(peak, nav)
        st, fa, gaps = P["st"][d], P["fa"][d], P["gp"][d]
        eff = S.effective_state(st, fa)
        if arm is not None and d in ind.index:
            on = arm(ind.loc[d], on, nav / peak - 1)
        active = bool(arm is not None and on and eff == "A")
        t = dict(P["trim"][d])
        if t["in_a"]:
            t["base"] = step if active else base
        bp = P["pct"].get(d)
        gate = S.d_gate_active(st, bp if bp is not None else 1.0, gaps.get(200))
        w5 = S.target_weights_with_voltarget(st, P["mi"][d], P["vol"][d], fast_state=fa, gaps=gaps,
                                             d_gate=gate, a_trim=t)
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")), active)
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                c = COST * float(np.abs(tgt - held).sum())
                out[-1][1] = (1 + out[-1][1]) * (1 - c) - 1; nav *= 1 - c
            held = tgt.copy()
        prev = key
    return pd.Series({pd.Timestamp(d): g for d, g in out})


if __name__ == "__main__":
    px = load(); P = prepare(px); ind = indicators(px)
    pd.set_option("display.width", 250)
    summary = {}
    for label, Q, kw in (("REAL", P, dict()),
                         ("PROXY", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front, rows, ser = [], {}, {}
        for c in (0.7, 0.6, 0.5, 0.4, 0.3, 0.2):
            s = run_step(Q, ind, (c, round(1 - c, 2)), **kw); st_ = stats(s)
            front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
            rows[f"plain {c*100:.0f}/{(1-c)*100:.0f}"] = {k: float(v) for k, v in st_.items()}; ser[f"plain{c}"] = s
        for k, a, b in ARMS:
            for step in ((0.5, 0.5), (0.4, 0.6)):
                s = run_step(Q, ind, (0.3, 0.7), step=step, arm=make_arm(k, a, b), **kw)
                r = {kk: float(v) for kk, v in stats(s).items()}
                r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
                nm = f"30/70 -> {step[0]*100:.0f}/{step[1]*100:.0f} on {name(k, a, b)}"
                rows[nm] = r; ser[nm] = s
        t = pd.DataFrame(rows).T
        summary[label] = (t, ser)
        print(f"\n{label}")
        print(t[["CAGR", "Sharpe", "MaxDD", "Y2022", "h1", "h2", "vs frontier"]].round(3).to_string())
    tr, tp = summary["REAL"][0], summary["PROXY"][0]
    both = tr.index[(tr["vs frontier"] > 0) & (tp["vs frontier"] > 0)]
    print("\nArms ahead of the plain-ratio frontier on BOTH real and proxy:", list(both) or "none")
    for nm in both:
        for lab in ("REAL", "PROXY"):
            t, ser = summary[lab]
            ci, p = block_boot(ser[nm], ser["plain0.4"])
            print(f"  {lab} {nm}: Sharpe vs plain 40/60 CI {ci.round(3)} P<=0 {p:.2f}")
