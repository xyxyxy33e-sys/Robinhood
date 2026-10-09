"""Sub-zones inside state D cut by other moving-average lines (owner, 2026-10-09).

D = QQQ below its 50-day, still above its 200-day. Sub-zones:
  by depth: D1 above the 100-day | D2 between 100- and 150-day | D3 between 150- and 200-day
  by the 20-day line: QQQ above it (bouncing) | below it (still falling)
Part 1 measures each sub-zone on the days the book is in D (gate off): next-day and next-20-day QLD
and QQQ returns, and how often the D spell goes on to E. Part 2 tests D rows that differ by
sub-zone (QLD share; the rest to SPMO), both "lighter when deeper" and "heavier when deeper",
on the live rules (A 40/60) against the plain-split upper envelope.

    python -m research.d_substates_dma
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at
from research.dd_protection import run_p, top5


def zones(px):
    q = px["QQQ"].dropna(); q.index = [d.strftime("%Y-%m-%d") for d in q.index]
    m = {n: q.rolling(n).mean() for n in (20, 100, 150)}
    depth = pd.Series(np.where(q > m[100], "D1 above 100d", np.where(q > m[150], "D2 100-150d", "D3 150-200d")), index=q.index)
    trend = pd.Series(np.where(q > m[20], "above 20d", "below 20d"), index=q.index)
    return depth.to_dict(), trend.to_dict(), q


def run_z(P, zmap, zone, base=(0.4, 0.6), start="2015-11-02", end="2026-10-07", vixm=True):
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
        z = None
        if eff == "D" and not gate:
            z = zone.get(d)
            ql = zmap.get(z, 1.0)
            m = S.vol_target_multiplier(P["vol"][d])
            w5 = ((1 - ql) * m, 0.0, ql * m, 0.0, 1 - m)
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")), z)
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                out[-1][1] = (1 + out[-1][1]) * (1 - COST * float(np.abs(tgt - held).sum())) - 1
            held = tgt.copy()
        prev = key
    return pd.Series({pd.Timestamp(d): g for d, g in out})


MAPS = {
    "depth: lighter deeper (D1 100 / D2 75 / D3 50% QLD)": ("depth", {"D1 above 100d": 1.0, "D2 100-150d": 0.75, "D3 150-200d": 0.5}),
    "depth: lighter deeper, steep (100 / 50 / 0)": ("depth", {"D1 above 100d": 1.0, "D2 100-150d": 0.5, "D3 150-200d": 0.0}),
    "depth: heavier deeper (D1 50 / D2 75 / D3 100)": ("depth", {"D1 above 100d": 0.5, "D2 100-150d": 0.75, "D3 150-200d": 1.0}),
    "depth: shallow only light (D1 50 / D2 100 / D3 100)": ("depth", {"D1 above 100d": 0.5, "D2 100-150d": 1.0, "D3 150-200d": 1.0}),
    "20d: light while below 20d (below 50% / above 100%)": ("trend", {"below 20d": 0.5, "above 20d": 1.0}),
    "20d: light while above 20d (above 50% / below 100%)": ("trend", {"above 20d": 0.5, "below 20d": 1.0}),
}

if __name__ == "__main__":
    px = load(); P = prepare(px)
    depth, trend, q = zones(px)
    qld = px["QLD"].dropna(); qld.index = [d.strftime("%Y-%m-%d") for d in qld.index]
    pd.set_option("display.width", 250)
    # Part 1: what each sub-zone did (gate-off D days)
    for label, start, lev in (("REAL 2015-26 (QLD)", "2015-11-02", None), ("PROXY 2001-26 (2x QQQ)", "2001-01-02", 2)):
        days = [d for d in P["dates"] if d >= start and d <= "2026-09-01"
                and S.effective_state(P["st"][d], P["fa"][d]) == "D"
                and not S.d_gate_active(P["st"][d], P["pct"].get(d) if P["pct"].get(d) is not None else 1.0, P["gp"][d].get(200))]
        nxt1 = (q.shift(-1) / q - 1); nxt20 = (q.shift(-20) / q - 1)
        df = pd.DataFrame({"depth": [depth[d] for d in days], "trend": [trend[d] for d in days],
                           "QQQ next day": [nxt1[d] for d in days], "QQQ next 20d": [nxt20[d] for d in days]}, index=days)
        # did this D spell go on to E within 20 sessions
        idx = {d: i for i, d in enumerate(P["dates"])}
        df["to E in 20d"] = [any(S.effective_state(P["st"][x], P["fa"][x]) in "EF" for x in P["dates"][idx[d] + 1: idx[d] + 21]) for d in days]
        for col in ("depth", "trend"):
            g = df.groupby(col).agg(days=("QQQ next day", "size"), next_day=("QQQ next day", "mean"),
                                    next20=("QQQ next 20d", "mean"), down20=("QQQ next 20d", lambda x: (x < 0).mean()),
                                    toE=("to E in 20d", "mean"))
            g["next_day x2 ann%"] = g.next_day * 2 * 252 * 100
            print(f"\n{label}: D days (gate off) by {col}")
            print((g.assign(next_day=g.next_day * 100, next20=g.next20 * 100, down20=g.down20 * 100, toE=g.toE * 100)).round(2).to_string())
    # Part 2: D rows by sub-zone
    res = {}
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front = []
        for c in (0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.2):
            st_ = stats(run_p(Q, base=(c, round(1 - c, 2)), **kw)); front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
        rows, ser = {}, {}
        s = run_p(Q, **kw); r = {k: float(v) for k, v in stats(s).items()}; r["vs frontier"] = 0.0; r["top-5"] = top5(s)
        rows["live (D = 100% QLD)"] = r; ser["live"] = s
        for nm, (kind, zmap) in MAPS.items():
            s = run_z(Q, zmap, depth if kind == "depth" else trend, **kw)
            r = {k: float(v) for k, v in stats(s).items()}
            r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
            r["top-5"] = top5(s)
            rows[nm] = r; ser[nm] = s
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print("\n" + label)
        print(t[["CAGR", "Sharpe", "MaxDD", "h1", "h2", "vs frontier", "top-5"]].round(3).to_string())
    (tr, sr), (tp, sp) = res.values()
    both = [i for i in tr.index if not i.startswith("live") and tr.loc[i, "vs frontier"] > 0 and tp.loc[i, "vs frontier"] > 0]
    print("\nAhead of the plain-split frontier on BOTH:", both or "none")
    for nm in both:
        for lab, (t, ser) in res.items():
            ci, p = block_boot(ser[nm], ser["live"])
            print(f"  {lab} {nm}: {t.loc[nm,'vs frontier']*100:+.2f}pp; Sharpe vs live CI {ci.round(3)} P<=0 {p:.2f}")
