"""XLU as an alternative to BOXX in the cash leg, under the live rules of 9 Oct 2026 (owner, 2026-10-09).

Same replay as research/a_ratio_live_rules.py (state.py's own functions, drift band, regime-change
trades, 4bp, same-session signal, VIXM sleeve on). After VIXM takes its share, a fraction of the
remaining BOXX moves to XLU on the effective states listed. A row of 50/50 (the live spell).

    python -m research.xlu_cash_live_rules
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns


def run_xlu(P, share, states, base=(0.5, 0.5), start="2015-11-02", end="2026-10-07", vixm=True):
    out, prev, held = [], None, None
    sim = [d for d in P["dates"] if start <= d <= end]
    for d in sim:
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
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        w = list(S.apply_vixm(w5, vx))
        key_state = "Dg" if gate else eff
        if key_state in states:
            x = w[5] * share
            w[3] += x; w[5] -= x
        tgt = np.array(w)
        key = (eff, t["held"], gate, bool(vx.get("allowed")))
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                out[-1][1] = (1 + out[-1][1]) * (1 - COST * float(np.abs(tgt - held).sum())) - 1
            held = tgt.copy()
        prev = key
    s = pd.Series({pd.Timestamp(d): g for d, g in out})
    return s


CASES = [("BOXX only (live)", 0.0, ()),
         ("E: 50% XLU (the pre-19 Sep row)", 0.5, ("E",)),
         ("E: 100% XLU", 1.0, ("E",)),
         ("E+F: 50% XLU", 0.5, ("E", "F")),
         ("D-gate cash: 50% XLU", 0.5, ("Dg",)),
         ("A/B/C/D cash (trim + vol target): 50% XLU", 0.5, ("A", "B", "C", "D")),
         ("all cash: 25% XLU", 0.25, ("A", "B", "C", "D", "Dg", "E", "F")),
         ("all cash: 50% XLU", 0.5, ("A", "B", "C", "D", "Dg", "E", "F")),
         ("all cash: 100% XLU", 1.0, ("A", "B", "C", "D", "Dg", "E", "F"))]

if __name__ == "__main__":
    px = load(); P = prepare(px)
    pd.set_option("display.width", 250)
    for label, Q, kw in (("REAL ETFs 2015-11..2026-10, VIXM on", P, dict()),
                         ("PROXY 2001-2026 (QQQ core, synthetic 2x/3x, no VIXM)", proxy_returns(P, px),
                          dict(start="2001-01-02", vixm=False))):
        rows, ser = {}, {}
        for name, sh, sts in CASES:
            s = run_xlu(Q, sh, sts, **kw); ser[name] = s
            r = {k: float(v) for k, v in stats(s).items()}
            yr = (1 + s).groupby(s.index.year).prod() - 1
            for y in (2002, 2008, 2020, 2022, 2025):
                if y in yr.index: r[str(y)] = yr[y]
            if "start" in kw:
                h = stats(s[:"2015-10-30"]); r["hold Sh"] = float(h["Sharpe"]); r["hold DD"] = float(h["MaxDD"])
            rows[name] = r
        t = pd.DataFrame(rows).T
        cols = [c for c in ["CAGR", "Sharpe", "MaxDD", "Worst", "2002", "2008", "2020", "2022", "2025", "h1", "h2", "hold Sh", "hold DD"] if c in t]
        print("\n" + label); print(t[cols].round(3).to_string())
        base = ser["BOXX only (live)"]
        for name in ("E+F: 50% XLU", "A/B/C/D cash (trim + vol target): 50% XLU", "all cash: 50% XLU"):
            ci, p = block_boot(ser[name], base); print(f"  Sharpe {name} - live: CI {ci.round(3)} P<=0 {p:.2f}")
