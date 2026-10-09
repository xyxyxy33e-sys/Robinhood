"""State-A SPMO/TQQQ split under the live rules of 9 Oct 2026 (owner, 2026-10-09).

Replays the live design day by day with paper-track/state.py's own functions -- six-state
classifier, 20/100 fast re-entry, extension trim v2 (held votes, whipsaw carry), 20% vol target on
30-day vol, state-D gate (breadth / gap200), E/F cash, VIXM cash sleeve -- with the 5% drift band,
regime-change trades (effective state, held votes, D gate, VIXM allowed), 4bp one-way cost, signal
and fill on the same session's close. Only the A base row (core, tqqq) changes between runs; at
held votes >= 1 TQQQ is out and SPMO is cut 1/6 of its base per vote, exactly as live.

    python -m research.a_ratio_live_rules
"""
import math
import os
import sys
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.simplefilter("ignore")
LIVE = os.environ.get("LIVE_REPO", "/home/user/robinhood-stock")
sys.path.insert(0, os.path.join(LIVE, "paper-track"))
import state as S  # noqa: E402
import breadth_tracker as BT  # noqa: E402

COST = 0.0004
LEGS = ["SPMO", "TQQQ", "QLD", "XLU", "VIXM", "BOXX"]


def load(end="2026-10-08"):
    tick = ["QQQ", "QQEW", "SPMO", "TQQQ", "QLD", "XLU", "VIXM", "^VIX", "^VIX3M", "^IRX"]
    px = yf.download(tick, start="1999-03-10", end=end, progress=False, auto_adjust=False)["Close"]
    return px


def prepare(px):
    q = px["QQQ"].dropna()
    dates = [d.strftime("%Y-%m-%d") for d in q.index]
    qpx = dict(zip(dates, q.values.astype(float)))
    st = S.compute_states(dates, qpx)
    fa = S.compute_fast_states(dates, qpx)
    gp = S.compute_extension_gaps(dates, qpx)
    mi = S.compute_micro_agreement(dates, qpx)
    trim = S.a_trim_series(dates, qpx)
    qe = px["QQEW"].dropna()
    qew = {d.strftime("%Y-%m-%d"): float(v) for d, v in qe.items()}
    common, x = BT.relative_strength_series(dates, qew, qpx)
    pct = dict(zip(common, BT.trailing_pct(x)))
    vol = {d: S.realized_vol_live(dates, qpx, as_of=d) for d in dates}
    vx, v3 = px["^VIX"].dropna(), px["^VIX3M"].dropna()
    vix = {d.strftime("%Y-%m-%d"): float(v) for d, v in vx.items()}
    vix3m = {d.strftime("%Y-%m-%d"): float(v) for d, v in v3.items()}
    idx = sorted(d for d in vix if d in vix3m)
    vxm = S.vixm_series(idx, vix, vix3m, vol)
    r = px[["SPMO", "TQQQ", "QLD", "XLU", "VIXM"]].pct_change()
    r["BOXX"] = px["^IRX"].ffill() / 100 / 252
    r.index = [d.strftime("%Y-%m-%d") for d in r.index]
    return dict(dates=dates, st=dict(zip(dates, st)), fa=fa, gp=gp, mi=dict(zip(dates, mi)) if isinstance(mi, list) else mi,
                trim=trim, pct=pct, vol=vol, vxm=vxm, r=r.fillna(0.0))


def run(P, base, start="2015-11-02", end="2026-10-07", vixm=True):
    out, prev = [], None
    held = None
    nav = 1.0
    reb = 0
    sim = [d for d in P["dates"] if start <= d <= end]
    for i, d in enumerate(sim):
        if held is not None:
            rr = P["r"].loc[d, LEGS].values if d in P["r"].index else np.zeros(6)
            g = float(np.dot(held, rr))
            nav *= 1 + g
            held = held * (1 + rr) / (1 + g)
            out.append((d, g))
        st, fa, gaps = P["st"][d], P["fa"][d], P["gp"][d]
        eff = S.effective_state(st, fa)
        t = dict(P["trim"][d])
        if t["in_a"]:
            t["base"] = base
        bp = P["pct"].get(d)
        gate = S.d_gate_active(st, bp if bp is not None else 1.0, gaps.get(200))
        w5 = S.target_weights_with_voltarget(st, P["mi"][d] if isinstance(P["mi"], dict) else False, P["vol"][d],
                                             fast_state=fa, gaps=gaps, d_gate=gate, a_trim=t)
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")))
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None:
                cost = COST * float(np.abs(tgt - held).sum())
                nav *= 1 - cost
                if out:
                    out[-1] = (out[-1][0], (1 + out[-1][1]) * (1 - cost) - 1)
            held = tgt.copy(); reb += 1
        prev = key
    s = pd.Series(dict(out))
    s.index = pd.to_datetime(s.index)
    return s, reb / (len(sim) / 252)


def stats(x, rf=None):
    eq = (1 + x).cumprod()
    n = len(x)
    cagr = eq.iloc[-1] ** (252 / n) - 1
    vol = x.std() * math.sqrt(252)
    sh = x.mean() / x.std() * math.sqrt(252)
    dd = (eq / eq.cummax() - 1).min()
    yr = (1 + x).groupby(x.index.year).prod() - 1
    h = n // 2
    sh1 = x.iloc[:h].mean() / x.iloc[:h].std() * math.sqrt(252)
    sh2 = x.iloc[h:].mean() / x.iloc[h:].std() * math.sqrt(252)
    return dict(CAGR=cagr, Vol=vol, Sharpe=sh, MaxDD=dd, Worst=yr.min(), Y2022=yr.get(2022, np.nan),
                h1=sh1, h2=sh2, Mult=eq.iloc[-1])


if __name__ == "__main__":
    px = load()
    P = prepare(px)
    pd.set_option("display.width", 220)
    rows = {}
    for c in (1.0, 0.8, 0.7, 0.6, 0.55, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.1, 0.0):
        s, rpy = run(P, (c, round(1 - c, 2)))
        rows[f"{c*100:.0f}/{(1-c)*100:.0f}"] = {**stats(s), "Reb/yr": rpy}
    t = pd.DataFrame(rows).T
    print(t.round(3).to_string())


def proxy_returns(P, px):
    """2000+ proxy: QQQ as the core, TQQQ/QLD synthesized as 3x/2x daily QQQ minus fees (0.95%/yr)
    and financing on the borrowed part at the T-bill rate; cash at the T-bill rate; XLU real. No VIXM
    (VIXM starts 2011, VIX3M 2007)."""
    q = px["QQQ"].pct_change()
    rf = px["^IRX"].ffill() / 100 / 252
    fee = 0.0095 / 252
    r = pd.DataFrame({"SPMO": q, "TQQQ": 3 * q - 2 * rf - fee, "QLD": 2 * q - rf - fee,
                      "XLU": px["XLU"].pct_change(), "VIXM": 0.0, "BOXX": rf})
    r.index = [d.strftime("%Y-%m-%d") for d in r.index]
    Q = dict(P)
    Q["r"] = r.fillna(0.0)
    return Q


def block_boot(a, b, n=2000, block=21, seed=7):
    """Circular block bootstrap of Sharpe(a) - Sharpe(b) on aligned daily returns."""
    rng = np.random.default_rng(seed)
    x, y = a.values, b.values
    T = len(x)
    k = int(np.ceil(T / block))
    d = []
    for _ in range(n):
        st = rng.integers(0, T, k)
        ix = (st[:, None] + np.arange(block)[None, :]).ravel()[:T] % T
        xa, ya = x[ix], y[ix]
        d.append(xa.mean() / xa.std() - ya.mean() / ya.std())
    d = np.array(d) * math.sqrt(252)
    return np.percentile(d, [2.5, 97.5]), (d <= 0).mean()
