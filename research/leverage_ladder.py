"""Leverage ladder D1 < D2 <= D3 = A (owner, 2026-10-09).

Owner's rule: the shallow dip (D1) carries the least leverage, the deeper dip (D2) more, and both
D3 and A at least as much as D2. D2 = 50% QLD + 50% TQQQ (2.5x); A base row and D3 move together
through 25/75 (2.5x), 20/80 (2.6x), 10/90 (2.8x), 0/100 (3x) SPMO/TQQQ; D1 = 75% or 50% QLD, rest
SPMO. Trim v2 still acts on the A row, the vol target scales every row, the D gate still sends D to
cash. Compared with the live design (A 40/60, D all 100% QLD) and with plain A splits.

    python -m research.leverage_ladder
"""
import itertools

import pandas as pd

from research.a_ratio_live_rules import load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5
from research.d_substates_dma import zones
from research.d_three_levels import run_3

TOPS = {"25/75 (2.5x)": (0.25, 0.75), "20/80 (2.6x)": (0.2, 0.8), "10/90 (2.8x)": (0.1, 0.9), "0/100 (3x)": (0.0, 1.0)}
D1S = {"D1 75% QLD": (0.25, 0.0, 0.75), "D1 50% QLD": (0.5, 0.0, 0.5)}
D2 = (0.0, 0.5, 0.5)

if __name__ == "__main__":
    px = load(); P = prepare(px); depth, _, _ = zones(px)
    pd.set_option("display.width", 260)
    res = {}
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        rows, ser = {}, {}
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.1, 0.0):
            s = run_p(Q, base=(c, round(1 - c, 2)), **kw); st_ = stats(s)
            front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
            if c in (0.4, 0.25, 0.2, 0.1, 0.0):
                nm = "live 40/60, D 100% QLD" if c == 0.4 else f"plain A {c*100:.0f}/{(1-c)*100:.0f}, D 100% QLD"
                rows[nm] = {**{k: float(v) for k, v in st_.items()}, "top-5": top5(s)}; ser[nm] = s
        for (tn, top), (dn, d1) in itertools.product(TOPS.items(), D1S.items()):
            s = run_3(Q, {"D1 above 100d": d1, "D2 100-150d": D2, "D3 150-200d": (top[0], top[1], 0.0)}, depth,
                      base=top, **kw)
            r = {k: float(v) for k, v in stats(s).items()}
            r["top-5"] = top5(s)
            nm = f"ladder: A & D3 {tn}, D2 2.5x, {dn}"
            rows[nm] = r; ser[nm] = s
        t = pd.DataFrame(rows).T
        t["vs frontier"] = [r - frontier_cagr_at(dd, front) for r, dd in zip(t.CAGR, t.MaxDD)]
        res[label] = (t, ser)
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "Worst", "Y2022", "h1", "h2", "vs frontier", "top-5"]].round(3).to_string())
    (tr, sr), (tp, sp) = res.values()
    print("\nLadders vs the plain A split at the SAME top leverage (D all 100% QLD): Sharpe real/proxy, P(not better)")
    for tn, top in TOPS.items():
        plain = f"plain A {top[0]*100:.0f}/{top[1]*100:.0f}, D 100% QLD"
        for dn in D1S:
            nm = f"ladder: A & D3 {tn}, D2 2.5x, {dn}"
            pr = block_boot(sr[nm], sr[plain])[1]; pp = block_boot(sp[nm], sp[plain])[1]
            print(f"  {nm}: {tr.loc[nm,'Sharpe']:.3f} vs {tr.loc[plain,'Sharpe']:.3f} (P {pr:.2f}) | "
                  f"{tp.loc[nm,'Sharpe']:.3f} vs {tp.loc[plain,'Sharpe']:.3f} (P {pp:.2f})")
