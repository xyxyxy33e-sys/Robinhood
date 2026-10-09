"""Protections aimed at what the five worst drawdowns have in common (owner, 2026-10-09; see
research/drawdown_anatomy.py).

Findings that drive the arms:
  1. The losses land mostly in state D, where the row is 100% QLD (2x) -- barely less leverage
     than the 40/60 A row (~2.2x) the book just left.
  2. In choppy falls the D gate flips cash <-> QLD as QQQ hovers around 200-day +2%, buying QLD
     back in just before the next leg down (2005: 14 flips; 2011; 2015-16; 2025-02/03).
Arms (each alone, on the live rules, A 40/60, VIXM on for real ETFs):
  D rows:   QLD 75% + cash 25%; QLD 50% + cash 50%; QLD 50% + SPMO 50%; SPMO 100%
  D latch:  once the gate fires inside a D episode, stay in cash until the episode ends
            (macro state leaves D for more than `gap` sessions)
  D gate wider: gap200 line at 4% / 6% instead of 2%
Judged against the plain-ratio upper envelope (CAGR at equal or shallower max drawdown) on real
ETFs and the 2001-2026 proxy, plus the five worst drawdowns of each.

    python -m research.dd_protection
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.drawdown_anatomy import episodes


def run_p(P, base=(0.4, 0.6), d_row=None, latch=False, latch_gap=3, g200=0.02,
          start="2015-11-02", end="2026-10-07", vixm=True):
    out, prev, held = [], None, None
    latched, out_of_d = False, 99
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
        gate = S.d_gate_active(st, bp if bp is not None else 1.0, gaps.get(200)) if g200 == 0.02 else \
            (st == "D" and ((bp is not None and bp < 0.20) or (gaps.get(200) is not None and gaps[200] < g200)))
        if st == "D":
            out_of_d = 0
            if gate:
                latched = latched or latch
            elif latched:
                gate = True
        else:
            out_of_d += 1
            if out_of_d > latch_gap:
                latched = False
        w5 = S.target_weights_with_voltarget(st, P["mi"][d], P["vol"][d], fast_state=fa, gaps=gaps,
                                             d_gate=gate, a_trim=t)
        if d_row is not None and eff == "D" and not gate:
            m = S.vol_target_multiplier(P["vol"][d])
            c, q, cash = d_row
            w5 = (c * m, 0.0, q * m, 0.0, 1 - (c + q) * m)
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")))
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                out[-1][1] = (1 + out[-1][1]) * (1 - COST * float(np.abs(tgt - held).sum())) - 1
            held = tgt.copy()
        prev = key
    return pd.Series({pd.Timestamp(d): g for d, g in out})


ARMS = {
    "live (D = 100% QLD, gate 2%)": dict(),
    "D = 75% QLD + 25% cash": dict(d_row=(0.0, 0.75, 0.25)),
    "D = 50% QLD + 50% cash": dict(d_row=(0.0, 0.50, 0.50)),
    "D = 50% QLD + 50% SPMO": dict(d_row=(0.5, 0.50, 0.0)),
    "D = 100% SPMO": dict(d_row=(1.0, 0.0, 0.0)),
    "D gate latch (stay cash till D ends)": dict(latch=True),
    "D gate line 4% over 200d": dict(g200=0.04),
    "D gate line 6% over 200d": dict(g200=0.06),
    "latch + D = 50% QLD + 50% SPMO": dict(latch=True, d_row=(0.5, 0.5, 0.0)),
}


def top5(s):
    nav = (1 + s).cumprod()
    df = pd.DataFrame({"nav": nav}); df.index = df.index.strftime("%Y-%m-%d")
    return [round(e[2] * 100, 1) for e in episodes(df)]


if __name__ == "__main__":
    px = load(); P = prepare(px)
    pd.set_option("display.width", 260)
    res = {}
    for label, Q, kw in (("REAL 2015-26 (A 40/60, VIXM on)", P, dict()),
                         ("PROXY 2001-26 (A 40/60)", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front, rows, ser = [], {}, {}
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.2):
            s = run_p(Q, base=(c, round(1 - c, 2)), **kw); st_ = stats(s)
            front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        for nm, a in ARMS.items():
            s = run_p(Q, **a, **kw)
            r = {k: float(v) for k, v in stats(s).items()}
            r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
            r["top-5 drawdowns"] = top5(s)
            rows[nm] = r; ser[nm] = s
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print(f"\n{label}")
        print(t[["CAGR", "Sharpe", "MaxDD", "Y2022", "h1", "h2", "vs frontier", "top-5 drawdowns"]].round(3).to_string())
    (tr, sr), (tp, sp) = res.values()
    both = [i for i in tr.index if i != "live (D = 100% QLD, gate 2%)" and tr.loc[i, "vs frontier"] > 0 and tp.loc[i, "vs frontier"] > 0]
    print("\nAhead of the plain-ratio frontier on BOTH real and proxy:", both or "none")
    for nm in both:
        for lab, (t, ser) in res.items():
            ci, p = block_boot(ser[nm], ser["live (D = 100% QLD, gate 2%)"])
            print(f"  {lab} {nm}: {t.loc[nm,'vs frontier']*100:+.2f}pp; Sharpe vs live CI {ci.round(3)} P<=0 {p:.2f}")
