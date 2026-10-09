"""More leverage in A, less in D: do they offset? (owner, 2026-10-09)

Grid of A base rows x D rows on the live rules (trim v2, D gate, vol target, fast re-entry, VIXM on
real ETFs). Yardstick: plain A splits with today's D row (100% QLD), CAGR at equal or shallower max
drawdown (upper envelope), on real ETFs 2015-26 and the 2001-26 proxy.

    python -m research.a_up_d_down
"""
import pandas as pd

from research.a_ratio_live_rules import load, prepare, stats, proxy_returns, block_boot
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5

A_ROWS = [(0.4, 0.6), (0.35, 0.65), (0.3, 0.7), (0.25, 0.75)]
D_ROWS = {"D 100% QLD": None, "D 75 QLD/25 SPMO": (0.25, 0.75, 0.0), "D 50 QLD/50 SPMO": (0.5, 0.5, 0.0)}

if __name__ == "__main__":
    px = load(); P = prepare(px)
    pd.set_option("display.width", 250)
    res = {}
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.1):
            st_ = stats(run_p(Q, base=(c, round(1 - c, 2)), **kw)); front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        rows, ser = {}, {}
        for a in A_ROWS:
            for dn, dr in D_ROWS.items():
                s = run_p(Q, base=a, d_row=dr, **kw)
                r = {k: float(v) for k, v in stats(s).items()}
                r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
                r["top-5"] = top5(s)
                nm = f"A {a[0]*100:.0f}/{a[1]*100:.0f} + {dn}"
                rows[nm] = r; ser[nm] = s
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "h1", "h2", "vs frontier", "top-5"]].round(3).to_string())
    (tr, sr), (tp, sp) = res.values()
    both = [i for i in tr.index if "100% QLD" not in i and tr.loc[i, "vs frontier"] > 0 and tp.loc[i, "vs frontier"] > 0]
    print("\nAhead of the plain-split frontier on BOTH:", both or "none")
    for nm in both:
        for lab, (t, ser) in res.items():
            ci, p = block_boot(ser[nm], ser["A 40/60 + D 100% QLD"])
            print(f"  {lab} {nm}: {t.loc[nm,'vs frontier']*100:+.2f}pp; Sharpe vs live 40/60 CI {ci.round(3)} P<=0 {p:.2f}")
