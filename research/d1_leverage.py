"""How light should D1 be? (owner, 2026-10-09)

D1 (QQQ in D and above its 100-day line) is the weakest D zone. Sweep its row from 75% QLD down to cash,
with D2 = 50% QLD + 50% TQQQ and D3 = A, for both A mixes. Rows are (SPMO, TQQQ, QLD); the rest is cash.

    python -m research.d1_leverage
"""
import pandas as pd

from research.a_ratio_live_rules import load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5
from research.d_substates_dma import zones
from research.d_three_levels import run_3

D1S = {
    "75% QLD + 25% SPMO (1.75x)": (0.25, 0, 0.75),
    "50% QLD + 50% SPMO (1.5x)": (0.5, 0, 0.5),
    "25% QLD + 75% SPMO (1.25x)": (0.75, 0, 0.25),
    "100% SPMO (1x)": (1.0, 0, 0),
    "50% QLD + 50% cash (1x)": (0, 0, 0.5),
    "50% SPMO + 50% cash (0.5x)": (0.5, 0, 0),
    "cash (0x)": (0, 0, 0),
}
TOPS = {"A 25S/75T": (0.25, 0.75), "A 40S/60T": (0.4, 0.6)}
REF = "50% QLD + 50% SPMO (1.5x)"

if __name__ == "__main__":
    px = load(); P = prepare(px); depth, _, _ = zones(px)
    pd.set_option("display.width", 260)
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.1, 0.0):
            st_ = stats(run_p(Q, base=(c, round(1 - c, 2)), **kw)); front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        rows, ser = {}, {}
        for tn, top in TOPS.items():
            for dn, d1 in D1S.items():
                s = run_3(Q, {"D1 above 100d": d1, "D2 100-150d": (0, 0.5, 0.5), "D3 150-200d": (top[0], top[1], 0.0)},
                          depth, base=top, **kw)
                x = {k: float(v) for k, v in stats(s).items()}; x["top-5"] = top5(s)
                rows[(tn, dn)] = x; ser[(tn, dn)] = s
            for dn in D1S:
                rows[(tn, dn)]["P vs 1.5x"] = block_boot(ser[(tn, dn)], ser[(tn, REF)])[1] if dn != REF else float("nan")
        t = pd.DataFrame(rows).T
        t["vs frontier"] = [r - frontier_cagr_at(dd, front) for r, dd in zip(t.CAGR, t.MaxDD)]
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "Y2022", "h1", "h2", "P vs 1.5x", "vs frontier", "top-5"]].round(3).to_string())
