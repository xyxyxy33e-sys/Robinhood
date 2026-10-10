"""Swap-only D ladders (owner, 2026-10-09): make zone moves a QLD<->TQQQ swap to cut trading.

Rows are (SPMO, TQQQ, QLD). The previous pick moves SPMO->TQQQ at D1->D2 and QLD->SPMO/TQQQ at D2->D3.
The "fixed SPMO" ladders hold SPMO constant across D1, D2, D3 and A, so every zone change only swaps
QLD for TQQQ. Cost drag = CAGR with zero cost minus CAGR at 4bp, which shows what the trades cost.

    python -m research.d_swap_ladder
"""
import pandas as pd

import research.d_three_levels as d3
from research.a_ratio_live_rules import load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5
from research.d_substates_dma import zones

Z = ("D1 above 100d", "D2 100-150d", "D3 150-200d")
DESIGNS = {
    "pick: D1 50S/50Q, D2 50T/50Q, A 25S/75T": [(0.5, 0, 0.5), (0, 0.5, 0.5), (0.25, 0.75)],
    "D1 100Q, D2 50T/50Q, A 25S/75T": [(0, 0, 1), (0, 0.5, 0.5), (0.25, 0.75)],
    "D1 50S/50Q, D2 50S/50T, A 25S/75T": [(0.5, 0, 0.5), (0.5, 0.5, 0), (0.25, 0.75)],
    "fixed 25S: D1 75Q, D2 50T/25Q, A 75T": [(0.25, 0, 0.75), (0.25, 0.5, 0.25), (0.25, 0.75)],
    "fixed 25S: D1 75Q, D2 25T/50Q, A 75T": [(0.25, 0, 0.75), (0.25, 0.25, 0.5), (0.25, 0.75)],
    "fixed 20S: D1 80Q, D2 40T/40Q, A 80T": [(0.2, 0, 0.8), (0.2, 0.4, 0.4), (0.2, 0.8)],
    "fixed 40S: D1 60Q, D2 30T/30Q, A 60T": [(0.4, 0, 0.6), (0.4, 0.3, 0.3), (0.4, 0.6)],
}


def go(Q, rows, depth, kw, cost):
    d3.COST = cost
    a = rows[2]
    return d3.run_3(Q, {Z[0]: rows[0], Z[1]: rows[1], Z[2]: (a[0], a[1], 0.0)}, depth, base=a, **kw)


if __name__ == "__main__":
    px = load(); P = prepare(px); depth, _, _ = zones(px)
    pd.set_option("display.width", 260)
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.1, 0.0):
            st_ = stats(run_p(Q, base=(c, round(1 - c, 2)), **kw)); front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        live = run_p(Q, base=(0.4, 0.6), **kw)
        rows = {"live 40S/60T, D 100Q": {**{k: float(v) for k, v in stats(live).items()}}}
        ser = {}
        for nm, r in DESIGNS.items():
            s = go(Q, r, depth, kw, 0.0004); s0 = go(Q, r, depth, kw, 0.0)
            x = {k: float(v) for k, v in stats(s).items()}
            x["cost drag"] = float(stats(s0)["CAGR"]) - x["CAGR"]; x["top-5"] = top5(s)
            x["P vs live"] = block_boot(s, live)[1]
            rows[nm] = x; ser[nm] = s
        d3.COST = 0.0004
        t = pd.DataFrame(rows).T
        t["vs frontier"] = [r - frontier_cagr_at(dd, front) for r, dd in zip(t.CAGR, t.MaxDD)]
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "Y2022", "h1", "h2", "cost drag", "vs frontier", "P vs live", "top-5"]].round(4).to_string())
