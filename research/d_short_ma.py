"""D sub-zones cut by the 5-day and 10-day lines (owner, 2026-10-09), next to the 20-day.

Part 1: QQQ's next-day / next-20-day return on D days (gate off), above vs below each short line.
Part 2: D rows that hold 50% QLD + 50% SPMO on one side of the line (100% QLD on the other), and
the same stacked on the shallow-D rule (D1 = above the 100-day: 75% QLD + 25% SPMO, from
research/d_substates_dma.py). Live rules otherwise, A 40/60, real ETFs and the 2001-26 proxy.

    python -m research.d_short_ma
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import S, load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5
from research.d_substates_dma import zones, run_z

if __name__ == "__main__":
    px = load(); P = prepare(px)
    depth, _, q = zones(px)
    side = {n: pd.Series(np.where(q > q.rolling(n).mean(), f"above {n}d", f"below {n}d"), index=q.index).to_dict()
            for n in (5, 10, 20)}
    pd.set_option("display.width", 250)
    nxt1 = q.shift(-1) / q - 1; nxt20 = q.shift(-20) / q - 1
    for label, start in (("REAL 2015-26", "2015-11-02"), ("PROXY 2001-26", "2001-01-02")):
        days = [d for d in P["dates"] if start <= d <= "2026-09-01" and S.effective_state(P["st"][d], P["fa"][d]) == "D"
                and not S.d_gate_active(P["st"][d], P["pct"].get(d) if P["pct"].get(d) is not None else 1.0, P["gp"][d].get(200))]
        print(f"\n{label}: D days (gate off), QQQ next day / next 20 days")
        for n in (5, 10, 20):
            g = pd.DataFrame({"z": [side[n][d] for d in days], "n1": [nxt1[d] for d in days], "n20": [nxt20[d] for d in days]})
            t = g.groupby("z").agg(days=("n1", "size"), next_day=("n1", "mean"), next20=("n20", "mean"))
            print("  " + "; ".join(f"{z}: {int(r.days)} days, {r.next_day*100:+.2f}% / {r.next20*100:+.1f}%" for z, r in t.iterrows()))
    combos = {}
    for n in (5, 10, 20):
        combos[f"{n}d: 50% QLD while below"] = (side[n], {f"below {n}d": 0.5})
        combos[f"{n}d: 50% QLD while above"] = (side[n], {f"above {n}d": 0.5})
    res = {}
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.2):
            st_ = stats(run_p(Q, base=(c, round(1 - c, 2)), **kw)); front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        rows, ser = {}, {}
        live = run_p(Q, **kw); ser["live"] = live
        rows["live (D 100% QLD)"] = {**{k: float(v) for k, v in stats(live).items()}, "vs frontier": 0.0, "top-5": top5(live)}
        d1 = {z: (0.75 if z == "D1 above 100d" else 1.0) for z in ("D1 above 100d", "D2 100-150d", "D3 150-200d")}
        s = run_z(Q, d1, depth, **kw); ser["shallow-D 75/25"] = s
        rows["shallow-D 75/25 (yesterday's candidate)"] = {**{k: float(v) for k, v in stats(s).items()},
                                                           "vs frontier": float(stats(s)["CAGR"] - frontier_cagr_at(stats(s)["MaxDD"], front)), "top-5": top5(s)}
        for nm, (zone, zmap) in combos.items():
            s = run_z(Q, zmap, zone, **kw); ser[nm] = s
            r = {k: float(v) for k, v in stats(s).items()}
            r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front); r["top-5"] = top5(s)
            rows[nm] = r
            # stacked with shallow-D: key = (depth zone, side)
            stz = {d: (depth.get(d), zone.get(d)) for d in zone}
            key_side = list(zmap)[0]
            smap = {}
            for dz in ("D1 above 100d", "D2 100-150d", "D3 150-200d"):
                for sd in (key_side, key_side.replace("below", "X").replace("above", "below").replace("X", "above")):
                    base_q = 0.75 if dz == "D1 above 100d" else 1.0
                    smap[(dz, sd)] = min(base_q, 0.5) if sd == key_side else base_q
            s = run_z(Q, smap, stz, **kw); ser[nm + " + shallow-D"] = s
            r = {k: float(v) for k, v in stats(s).items()}
            r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front); r["top-5"] = top5(s)
            rows[nm + " + shallow-D"] = r
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "h1", "h2", "vs frontier", "top-5"]].round(3).to_string())
    (tr, sr), (tp, sp) = res.values()
    print("\nSharpe up on BOTH datasets vs live, with bootstrap P(not better):")
    for nm in tr.index[1:]:
        if tr.loc[nm, "Sharpe"] > tr.iloc[0]["Sharpe"] and tp.loc[nm, "Sharpe"] > tp.iloc[0]["Sharpe"]:
            key = "shallow-D 75/25" if nm.startswith("shallow") else nm
            pr = block_boot(sr[key], sr["live"])[1]; pp = block_boot(sp[key], sp["live"])[1]
            print(f"  {nm}: real {tr.loc[nm,'Sharpe']:.3f} (P {pr:.2f}), proxy {tp.loc[nm,'Sharpe']:.3f} (P {pp:.2f}); "
                  f"CAGR {tr.loc[nm,'CAGR']*100:.1f} / {tp.loc[nm,'CAGR']*100:.1f}; MaxDD {tr.loc[nm,'MaxDD']*100:.1f} / {tp.loc[nm,'MaxDD']*100:.1f}")
