"""A 30/70 SPMO/TQQQ row with a quicker profit-locking exit (owner, 2026-10-09).

Live rules as research/a_ratio_live_rules.py (trim v2, vol target, D gate, fast re-entry, VIXM,
drift band, 4bp, same-session signal). On effective-A days with TQQQ in the row, an extra exit can
switch the TQQQ leg to BOXX (or to SPMO); the switch is a regime change, so it trades the same
session it fires. Each arm is judged against the plain-ratio frontier: the exit must beat simply
holding less TQQQ at the same drawdown, on real ETFs AND on the 2001-2026 proxy.

Arms (all decided on the QQQ close):
  dd{x}_{n}:  QQQ x% below its n-day closing high -> out; back in on a new 10-day closing high
  ma{k}:      QQQ close below its k-day SMA -> out; back in on a close above it
  vol{v}:     QQQ 10-day realized vol above v -> out; back in below v
  nav{x}:     strategy NAV x% below its running peak -> out; back in on a new 10-day QQQ high

    python -m research.a7030_quick_exit
"""
import math

import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns


def indicators(px):
    q = px["QQQ"].dropna()
    q.index = [d.strftime("%Y-%m-%d") for d in q.index]
    lr = np.log(q).diff()
    ind = pd.DataFrame({"c": q})
    for n in (10, 20, 50):
        ind[f"hi{n}"] = q.rolling(n).max()
    for k in (10, 20):
        ind[f"ma{k}"] = q.rolling(k).mean()
    ind["v10"] = lr.rolling(10).std() * math.sqrt(252)
    return ind


def make_arm(kind, a=None, b=None):
    """Return f(row, state_on, navdd) -> new state_on."""
    if kind == "dd":
        def f(r, on, navdd):
            if not on and r.c <= r[f"hi{b}"] * (1 - a):
                return True
            if on and r.c >= r.hi10:
                return False
            return on
    elif kind == "ma":
        def f(r, on, navdd):
            return r.c < r[f"ma{a}"]
    elif kind == "vol":
        def f(r, on, navdd):
            return r.v10 > a
    elif kind == "nav":
        def f(r, on, navdd):
            if not on and navdd <= -a:
                return True
            if on and r.c >= r.hi10:
                return False
            return on
    return f


def run_exit(P, ind, base, arm=None, to="BOXX", start="2015-11-02", end="2026-10-07", vixm=True):
    out, prev, held = [], None, None
    nav, peak, on = 1.0, 1.0, False
    sim = [d for d in P["dates"] if start <= d <= end]
    for d in sim:
        if held is not None:
            rr = P["r"].loc[d, LEGS].values
            g = float(np.dot(held, rr))
            held = held * (1 + rr) / (1 + g)
            out.append([d, g]); nav *= 1 + g; peak = max(peak, nav)
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
        if arm is not None and d in ind.index:
            on = arm(ind.loc[d], on, nav / peak - 1)
        active = bool(arm is not None and on and eff == "A" and w5[1] > 0)
        w5 = list(w5)
        if active:
            if to == "SPMO":
                w5[0] += w5[1]
            else:
                w5[4] += w5[1]
            w5[1] = 0.0
        w = list(S.apply_vixm(tuple(w5), vx))
        tgt = np.array(w)
        key = (eff, t["held"], gate, bool(vx.get("allowed")), active)
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                c = COST * float(np.abs(tgt - held).sum())
                out[-1][1] = (1 + out[-1][1]) * (1 - c) - 1; nav *= 1 - c
            held = tgt.copy()
        prev = key
    return pd.Series({pd.Timestamp(d): g for d, g in out})


ARMS = ([("dd", a, n) for n in (20, 50) for a in (0.03, 0.04, 0.05, 0.07)]
        + [("ma", 10, None), ("ma", 20, None)]
        + [("vol", v, None) for v in (0.20, 0.25, 0.30)]
        + [("nav", x, None) for x in (0.05, 0.08, 0.10)])


def name(k, a, b):
    return {"dd": f"dd{a*100:.0f}%/{b}d", "ma": f"ma{a}", "vol": f"vol10>{a*100:.0f}%", "nav": f"NAV-{a*100:.0f}%"}[k]


def frontier_cagr_at(dd, front):
    """Best CAGR a plain ratio reaches with a max drawdown no deeper than `dd`: the upper envelope
    of the (depth, CAGR) points, linearly interpolated. (Fixed 2026-10-09: the first version
    interpolated the raw points, which on the proxy -- where 50/50 has a SHALLOWER max drawdown
    than 70/30 -- compared some arms with 80/20's CAGR instead of 50/50's and flattered them.)"""
    pts = sorted((-a, b) for a, b in front)          # depth ascending
    env, best = [], -1e9
    for x, y in pts:
        if y > best:
            env.append((x, y)); best = y
    xs = [x for x, _ in env]; ys = [y for _, y in env]
    return float(np.interp(-dd, xs, ys))


if __name__ == "__main__":
    px = load(); P = prepare(px); ind = indicators(px)
    pd.set_option("display.width", 250)
    for label, Q, kw in (("REAL ETFs 2015-11..2026-10 (VIXM on)", P, dict()),
                         ("PROXY 2001-2026 (no VIXM)", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front, rows, ser = [], {}, {}
        for c in (0.7, 0.6, 0.5, 0.4, 0.3, 0.2):
            s = run_exit(Q, ind, (c, round(1 - c, 2)), **kw); st_ = stats(s)
            front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
            rows[f"plain {c*100:.0f}/{(1-c)*100:.0f}"] = {k: float(v) for k, v in st_.items()}; ser[f"{c}"] = s
        for k, a, b in ARMS:
            for to in ("BOXX", "SPMO"):
                s = run_exit(Q, ind, (0.3, 0.7), arm=make_arm(k, a, b), to=to, **kw)
                st_ = stats(s); r = {kk: float(v) for kk, v in st_.items()}
                r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
                rows[f"30/70 + {name(k, a, b)} -> {to}"] = r; ser[f"{k}{a}{b}{to}"] = s
        t = pd.DataFrame(rows).T
        cols = ["CAGR", "Sharpe", "MaxDD", "Worst", "Y2022", "h1", "h2", "vs frontier"]
        print("\n" + label)
        print(t[cols].round(3).to_string())
