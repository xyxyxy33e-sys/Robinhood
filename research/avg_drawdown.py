"""Cutting the AVERAGE drawdown, not just the max (owner, 2026-10-09).

Base = the best design so far ("pick"): A and D3 25% SPMO / 75% TQQQ, D1 (above the 100-day)
50% QLD + 50% SPMO, D2 (100-150 day) 50% QLD + 50% TQQQ, live trim v2, D gate, vol target 20%,
VIXM, drift band, 4bp.

Drawdown scored on WEEKLY (Friday) closes:
  avgDD   mean depth below the running peak, every week counted (0 at a new high)
  ulcer   root-mean-square of that depth (punishes long/deep stretches)
  >10%    share of weeks more than 10% under the peak
  lossWk  average losing week;  cvar5  average of the worst 5% of weeks
Yardstick: simply holding less (risky legs x0.9/0.8/0.7, rest cash) also cuts every drawdown, so an
arm only helps if it beats that line: "edge" = arm CAGR minus the scaled-pick CAGR at the same avgDD.

    python -m research.avg_drawdown
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns
from research.dd_protection import top5
from research.d_substates_dma import zones

PICK = dict(top=(0.25, 0.75), d1=(0.5, 0, 0.5), d2=(0, 0.5, 0.5))
ARMS = {
    "pick": {},
    "pick x0.9 (hold less)": dict(scale=0.9),
    "pick x0.8 (hold less)": dict(scale=0.8),
    "pick x0.7 (hold less)": dict(scale=0.7),
    "cand B: A 40S/60T, D1 25Q/75S": dict(top=(0.4, 0.6), d1=(0.75, 0, 0.25)),
    "A & D3 40S/60T (pick D rows)": dict(top=(0.4, 0.6)),
    "A & D3 50S/50T (pick D rows)": dict(top=(0.5, 0.5)),
    "vol target 18%": dict(vt=0.18),
    "vol target 16%": dict(vt=0.16),
    "vol target 14%": dict(vt=0.14),
    "vol target 12%": dict(vt=0.12),
    "A below 20d: half TQQQ -> QLD": dict(ma=(0.5, "qld")),
    "A below 20d: all TQQQ -> QLD": dict(ma=(1.0, "qld")),
    "A below 20d: half TQQQ -> SPMO": dict(ma=(0.5, "spmo")),
    "NAV 10% under peak: x0.5": dict(brake=(0.10, 0.5)),
    "NAV 15% under peak: x0.5": dict(brake=(0.15, 0.5)),
}


def run_g(P, depth, trend, top=PICK["top"], d1=PICK["d1"], d2=PICK["d2"], vt=None, scale=1.0, ma=None, brake=None,
          start="2015-11-02", end="2026-10-07", vixm=True):
    rows = {"D1 above 100d": d1, "D2 100-150d": d2, "D3 150-200d": (top[0], top[1], 0.0)}
    out, prev, held, nav, peak = [], None, None, 1.0, 1.0
    for d in (x for x in P["dates"] if start <= x <= end):
        if held is not None:
            rr = P["r"].loc[d, LEGS].values
            g = float(np.dot(held, rr))
            held = held * (1 + rr) / (1 + g)
            out.append([d, g]); nav *= 1 + g; peak = max(peak, nav)
        st, fa, gaps = P["st"][d], P["fa"][d], P["gp"][d]
        eff = S.effective_state(st, fa)
        t = dict(P["trim"][d])
        if t["in_a"]:
            t["base"] = top
        bp = P["pct"].get(d)
        gate = S.d_gate_active(st, bp if bp is not None else 1.0, gaps.get(200))
        w5 = list(S.target_weights_with_voltarget(st, P["mi"][d], P["vol"][d], fast_state=fa, gaps=gaps,
                                                  d_gate=gate, a_trim=t))
        z = None
        m20 = S.vol_target_multiplier(P["vol"][d])
        if eff == "D" and not gate:
            z = depth.get(d)
            c, tq, ql = rows[z]
            w5 = [c * m20, tq * m20, ql * m20, 0.0, 0.0]
        f = 1.0
        if vt is not None and m20 > 0:
            f *= S.vol_target_multiplier(P["vol"][d], target=vt) / m20
        f *= scale
        br = brake is not None and nav < peak * (1 - brake[0])
        if br:
            f *= brake[1]
        sh = False
        if ma is not None and eff == "A" and trend.get(d) == "below 20d" and w5[1] > 0:
            mv = w5[1] * ma[0]; w5[1] -= mv
            w5[2 if ma[1] == "qld" else 0] += mv; sh = True
        w5 = [x * f for x in w5[:4]]
        w5.append(1 - sum(w5))
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(tuple(w5), vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")), z, br, sh)
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                out[-1][1] = (1 + out[-1][1]) * (1 - COST * float(np.abs(tgt - held).sum())) - 1
            held = tgt.copy()
        prev = key
    return pd.Series({pd.Timestamp(d): g for d, g in out})


def on_line(a, t):
    """CAGR of the hold-less line (pick scaled x0.7..x1.0) at average drawdown a, extended linearly."""
    ln = t.loc[["pick x0.7 (hold less)", "pick x0.8 (hold less)", "pick x0.9 (hold less)", "pick"]]
    x, y = ln.avgDD.values[::-1], ln.CAGR.values[::-1]          # increasing avgDD (deepest first)
    if a < x[0]:
        return y[0] + (a - x[0]) * (y[1] - y[0]) / (x[1] - x[0])
    if a > x[-1]:
        return y[-1] + (a - x[-1]) * (y[-1] - y[-2]) / (x[-1] - x[-2])
    return float(np.interp(a, x, y))


def wk(s):
    nav = (1 + s).cumprod().resample("W-FRI").last().dropna()
    uw = nav / nav.cummax() - 1
    wr = nav.pct_change().dropna()
    q = wr.quantile(0.05)
    return dict(avgDD=uw.mean(), ulcer=float(np.sqrt((uw ** 2).mean())), over10=(uw < -0.10).mean(),
                lossWk=wr[wr < 0].mean(), cvar5=wr[wr <= q].mean())


if __name__ == "__main__":
    px = load(); P = prepare(px); depth, trend, _ = zones(px)
    pd.set_option("display.width", 260)
    for label, Q, kw in (("REAL 2015-26", P, dict()), ("PROXY 2001-26", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        rows, ser = {}, {}
        for nm, a in ARMS.items():
            s = run_g(Q, depth, trend, **a, **kw); ser[nm] = s
            st_ = stats(s)
            rows[nm] = dict(CAGR=st_["CAGR"], Sharpe=st_["Sharpe"], MaxDD=st_["MaxDD"], **wk(s))
        t = pd.DataFrame(rows).T.astype(float)
        t["edge"] = [c - on_line(a, t) for c, a in zip(t.CAGR, t.avgDD)]
        t["P vs pick"] = [block_boot(ser[n], ser["pick"])[1] if n != "pick" else np.nan for n in t.index]
        print("\n" + label)
        f = t.copy()
        for c in ("CAGR", "MaxDD", "avgDD", "ulcer", "over10", "lossWk", "cvar5", "edge"):
            f[c] = (f[c] * 100).round(2)
        print(f.round(3).to_string())
