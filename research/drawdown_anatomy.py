"""Anatomy of the live design's five worst drawdowns (owner, 2026-10-09).

Replays the live rules (research/a_ratio_live_rules.py) with the 40/60 A base and records, per day:
effective state, macro state, held trim votes, D gate, VIXM, the held weights, the day's return
and each leg's contribution, plus QQQ's distance to its 50/100/150/200-day averages, 30-day vol,
breadth pct, VIX and VIX/VIX3M. Then finds the five deepest peak-to-trough drawdowns and breaks
each down by state and by leg, with the signal readings at the peak and through the fall.

    python -m research.drawdown_anatomy
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, proxy_returns


def replay(P, base=(0.4, 0.6), start="2015-11-02", end="2026-10-07", vixm=True):
    rows, prev, held = [], None, None
    vix = {d: v["vix"] for d, v in P["vxm"].items()}
    ratio = {d: v["ratio"] for d, v in P["vxm"].items()}
    for d in (x for x in P["dates"] if start <= x <= end):
        contrib = np.zeros(6); g = 0.0; hold_before = held.copy() if held is not None else np.zeros(6)
        if held is not None:
            rr = P["r"].loc[d, LEGS].values
            contrib = held * rr
            g = float(contrib.sum())
            held = held * (1 + rr) / (1 + g)
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
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")))
        changed = prev is not None and key != prev
        do, _, why = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        cost = 0.0
        if do:
            if held is not None:
                cost = COST * float(np.abs(tgt - held).sum())
            held = tgt.copy()
        prev = key
        rows.append(dict(d=d, ret=(1 + g) * (1 - cost) - 1, eff=eff, macro=st, held_votes=t["held"], gate=gate,
                         vixm=bool(vx.get("allowed")), traded=do, why=why if do else "",
                         **{f"w_{l}": w for l, w in zip(LEGS, hold_before)},
                         **{f"c_{l}": c for l, c in zip(LEGS, contrib)},
                         g50=gaps.get(50) if 50 in gaps else None, g100=gaps.get(100), g150=gaps.get(150),
                         g200=gaps.get(200), vol30=P["vol"].get(d), breadth=bp, vix=vix.get(d), vratio=ratio.get(d)))
    df = pd.DataFrame(rows).set_index("d")
    df["nav"] = (1 + df.ret).cumprod()
    return df


def episodes(df, n=5):
    nav = df.nav.values; dates = df.index
    eps, pk, pki, i = [], nav[0], 0, 0
    cur = None
    for i, v in enumerate(nav):
        if v >= pk:
            if cur and cur[2] < -0.05:
                eps.append(cur + (dates[i],))
            pk, pki, cur = v, i, None
        else:
            dd = v / pk - 1
            if cur is None or dd < cur[2]:
                cur = (dates[pki], dates[i], dd)
    if cur and cur[2] < -0.05:
        eps.append(cur + (None,))
    return sorted(eps, key=lambda e: e[2])[:n]


def describe(df, ep, qqq):
    p, t, dd, rec = ep
    seg = df.loc[p:t].iloc[1:]
    print(f"\n=== {p} -> {t}: {dd*100:.1f}%  ({len(seg)} sessions down; recovered {rec or 'not yet'})")
    q = qqq.loc[p:t]; print(f"    QQQ over the same days: {(q.iloc[-1]/q.iloc[0]-1)*100:+.1f}%")
    lr = np.log1p(seg.ret)
    by_state = lr.groupby(seg.eff).sum()
    print("    loss by effective state (log %):", {k: round(v * 100, 1) for k, v in by_state.items()},
          " days:", seg.eff.value_counts().to_dict())
    legs = {l: round(seg[f"c_{l}"].sum() * 100, 1) for l in LEGS}
    print("    leg contributions (sum of daily %):", legs)
    a = df.loc[p]
    print(f"    AT THE PEAK: state {a.eff} (macro {a.macro}), held votes {a.held_votes}, holdings "
          f"SPMO {a.w_SPMO:.0%} TQQQ {a.w_TQQQ:.0%} QLD {a.w_QLD:.0%} VIXM {a.w_VIXM:.0%} cash {a.w_BOXX:.0%}; "
          f"QQQ vs 50/100/150/200d {fmt(a.g50)}/{fmt(a.g100)}/{fmt(a.g150)}/{fmt(a.g200)}; vol30 {fmt(a.vol30)}; "
          f"breadth {fmt(a.breadth,2,False)}; VIX {fmt(a.vix,1,False)} ratio {fmt(a.vratio,2,False)}")
    # timeline: state changes and trades
    ch = seg[(seg.eff != seg.eff.shift()) | seg.traded]
    print("    trades / state changes in the fall:")
    for d, r in ch.iterrows():
        nav_dd = df.nav.loc[d] / df.nav.loc[p] - 1
        print(f"      {d}  {r.eff}{'(gate)' if r.gate else ''} votes {r.held_votes} vixm {int(r.vixm)}  dd so far {nav_dd*100:5.1f}%  "
              f"QQQ/50d {fmt(r.g50)} /200d {fmt(r.g200)} vol30 {fmt(r.vol30)}  {r.why}")
    worst = seg.ret.nsmallest(5)
    print("    5 worst days:", [(d, f"{v*100:.1f}%", seg.loc[d].eff, f"TQQQ {seg.loc[d].w_TQQQ:.0%} QLD {seg.loc[d].w_QLD:.0%}") for d, v in worst.items()])
    first5 = lr.iloc[:5].sum(); print(f"    loss in the first 5 sessions: {first5*100:.1f}% of {np.log1p(dd)*100:.1f}% (log)")


def fmt(x, nd=1, pct=True):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x*100:+.{nd}f}%" if pct else f"{x:.{nd}f}"


if __name__ == "__main__":
    px = load(); P = prepare(px)
    q = px["QQQ"].dropna(); q.index = [d.strftime("%Y-%m-%d") for d in q.index]
    pd.set_option("display.width", 250)
    for label, Q, kw in (("REAL ETFs 2015-11..2026-10, A 40/60, VIXM on", P, dict()),
                         ("PROXY 2001-2026, A 40/60, no VIXM", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        df = replay(Q, **kw)
        df.to_csv(f"/tmp/dd_{label.split()[0].lower()}.csv")
        print("\n" + "#" * 20, label, "#" * 20)
        for ep in episodes(df):
            describe(df, ep, q)
