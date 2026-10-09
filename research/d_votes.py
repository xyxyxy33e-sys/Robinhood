"""A graded vote system inside state D (owner, 2026-10-09).

Today the D gate is a binary switch: breadth pct < 0.20 OR QQQ < 2% above its 200-day -> D row
100% cash, else 100% QLD. Here each vote cuts the QLD leg by a step instead (to SPMO or cash), and
the full gate stays as the last level.
  gap200:   votes for QQQ less than 6% / 4% above its 200-day (the live 2% line still gates fully)
  breadth:  votes for breadth pct below 0.40 / 0.30 (the live 0.20 still gates fully)
  depth50:  votes for QQQ more than 2% / 4% below its 50-day
  combo:    gap200 + breadth votes together
Each vote cuts 25 points of QLD. Live rules otherwise (A 40/60, trim v2, vol target, VIXM on real).
Judged against the plain-split upper envelope on real ETFs 2015-26 and the 2001-26 proxy.

    python -m research.d_votes
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5


def d_votes(kind, gaps, bp, close_vs_50):
    v = 0
    g200 = gaps.get(200)
    if kind in ("gap200", "combo") and g200 is not None:
        v += sum(1 for x in (0.06, 0.04) if g200 < x)
    if kind in ("breadth", "combo") and bp is not None:
        v += sum(1 for x in (0.40, 0.30) if bp < x)
    if kind == "depth50" and close_vs_50 is not None:
        v += sum(1 for x in (-0.02, -0.04) if close_vs_50 < x)
    return v


def run_dv(P, q50, kind=None, to="SPMO", step=0.25, base=(0.4, 0.6), start="2015-11-02", end="2026-10-07", vixm=True):
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
        v = 0
        if kind and eff == "D" and not gate:
            v = d_votes(kind, gaps, bp, q50.get(d))
            if v:
                m = S.vol_target_multiplier(P["vol"][d])
                cut = min(1.0, step * v)
                ql = 1.0 - cut
                c = cut if to == "SPMO" else 0.0
                w5 = (c * m, 0.0, ql * m, 0.0, 1 - (c + ql) * m)
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")), v)
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
    q = px["QQQ"].dropna(); q.index = [d.strftime("%Y-%m-%d") for d in q.index]
    q50 = (q / q.rolling(50).mean() - 1).to_dict()
    pd.set_option("display.width", 250)
    res = {}
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.2):
            st_ = stats(run_p(Q, base=(c, round(1 - c, 2)), **kw)); front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        rows, ser = {}, {}
        for kind in (None, "gap200", "breadth", "depth50", "combo"):
            for to in (("SPMO", "cash") if kind else ("-",)):
                s = run_dv(Q, q50, kind=kind, to=to, **kw)
                r = {k: float(v) for k, v in stats(s).items()}
                r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
                r["top-5"] = top5(s)
                nm = "live (binary D gate)" if kind is None else f"D votes {kind} -> {to}"
                rows[nm] = r; ser[nm] = s
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "h1", "h2", "vs frontier", "top-5"]].round(3).to_string())
    (tr, sr), (tp, sp) = res.values()
    both = [i for i in tr.index if i != "live (binary D gate)" and tr.loc[i, "vs frontier"] > 0 and tp.loc[i, "vs frontier"] > 0]
    print("\nAhead of the plain-split frontier on BOTH:", both or "none")
    for nm in both:
        for lab, (t, ser) in res.items():
            ci, p = block_boot(ser[nm], ser["live (binary D gate)"])
            print(f"  {lab} {nm}: {t.loc[nm,'vs frontier']*100:+.2f}pp; Sharpe vs live CI {ci.round(3)} P<=0 {p:.2f}")
