"""Boundary check for the D sub-zones (owner, 2026-10-09): do the 100/150-day cut lines matter?

Re-runs the two ladder designs with the D1/D2/D3 cut lines moved to 90/140 and 110/160 (plus single-line
shifts), against the live design and the plain A split at the same top leverage. Rows are (SPMO, TQQQ, QLD).

    python -m research.d_zone_boundaries
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5
from research.d_three_levels import run_3

LINES = [(100, 150), (90, 140), (110, 160), (90, 150), (110, 150), (100, 140), (100, 160)]
DESIGNS = {
    "pick (A 25S/75T)": ([(0.5, 0, 0.5), (0, 0.5, 0.5)], (0.25, 0.75)),
    "cand B (A 40S/60T)": ([(0.5, 0, 0.5), (0, 0.5, 0.5)], (0.4, 0.6)),
}


def depth_map(px, a, b):
    q = px["QQQ"].dropna(); q.index = [d.strftime("%Y-%m-%d") for d in q.index]
    ma, mb = q.rolling(a).mean(), q.rolling(b).mean()
    return pd.Series(np.where(q > ma, "D1", np.where(q > mb, "D2", "D3")), index=q.index).to_dict()


if __name__ == "__main__":
    px = load(); P = prepare(px)
    pd.set_option("display.width", 260)
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.1, 0.0):
            st_ = stats(run_p(Q, base=(c, round(1 - c, 2)), **kw)); front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        plain = {top: run_p(Q, base=top, **kw) for _, top in DESIGNS.values()}
        rows = {}
        for tn, (dr, top) in DESIGNS.items():
            p = plain[top]; sp = stats(p)
            rows[f"{tn} | plain split, D 100% QLD"] = {k: float(v) for k, v in sp.items()}
            for a, b in LINES:
                dm = depth_map(px, a, b)
                s = run_3(Q, {"D1": dr[0], "D2": dr[1], "D3": (top[0], top[1], 0.0)}, dm, base=top, **kw)
                x = {k: float(v) for k, v in stats(s).items()}
                x["dSharpe vs plain"] = x["Sharpe"] - float(sp["Sharpe"]); x["P"] = block_boot(s, p)[1]
                x["top-5"] = top5(s)
                rows[f"{tn} | lines {a}/{b}"] = x
        t = pd.DataFrame(rows).T
        t["vs frontier"] = [r - frontier_cagr_at(dd, front) for r, dd in zip(t.CAGR, t.MaxDD)]
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "Y2022", "h1", "h2", "dSharpe vs plain", "P", "vs frontier", "top-5"]].round(3).to_string())
