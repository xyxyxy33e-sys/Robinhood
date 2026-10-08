"""VIXM decay and extra exit triggers for the Regime Tape BOXX-slot rule.

Base rule: signal ON when VIX < 18, OFF when VIX > VIX3M; VIXM only while QQQ 30-day realized
vol >= 20%; VIXM = 75% of the BOXX slot. An "episode" is one ON stretch of the signal.

Extra exits (by default one ends VIXM until QQQ vol next falls below 20% and returns;
the "episode-wide" rows instead block it until the signal resets with VIX < 18):
  tp X     VIXM up X% from the episode's entry price
  trail Y  VIXM down Y% from its highest close since entry
  stop Z   VIXM down Z% from entry
  time N   VIXM held N sessions in the episode
  fade F   VIX down F% from its highest close since entry (the spike is receding)
  ratio R  curve-inversion exit moved earlier: VIX/VIX3M > R instead of > 1.0

VIXM-price exits use the same close the trade happens at; VIX-based ones lag one more session.

    python -m research.regime_tape_vixm_exits
"""
import math

import numpy as np
import pandas as pd
import yfinance as yf

from research.regime_tape_sleeve import fmt, load
from research.regime_tape_vixm import run, summary

SHARE = 0.75
EVENTS = [("Q4 2018", "2018-10-01", "2018-12-24"), ("2022 bear", "2022-01-03", "2022-10-14"),
          ("Aug 2024", "2024-07-10", "2024-08-07"), ("Apr 2025", "2025-02-19", "2025-04-08"), ("Jun 2026", "2026-06-01", "2026-06-30")]


def market(idx):
    v = yf.download(["^VIX", "^VIX3M", "QQQ", "VIXM"], start="2015-06-01", end="2026-08-28", progress=False,
                    auto_adjust=True)["Close"].ffill()
    rv = v.QQQ.pct_change().rolling(30).std() * math.sqrt(252)
    lag = lambda s: s.reindex(idx).ffill().shift(1)            # VIX settles after the ETF close
    return {"vix": lag(v["^VIX"]), "ratio": lag(v["^VIX"] / v["^VIX3M"]), "rv": lag(rv),
            "vixm": v.VIXM.reindex(idx).ffill()}


def gate(m, tp=None, trail=None, stop=None, time=None, fade=None, ratio_exit=1.0, scope="stretch"):
    """scope='episode': an extra exit blocks VIXM until the signal resets (VIX < 18 again).
    scope='stretch': it blocks VIXM only until QQQ vol drops below 20% and comes back."""
    on = False; killed = False; entry = peak = vix_hi = None; held = 0
    out = []; episodes = 0
    for vix, ratio, rv, px in zip(m["vix"], m["ratio"], m["rv"], m["vixm"]):
        if np.isnan(vix) or np.isnan(ratio):
            out.append(False); continue
        if not on and vix < 18 and ratio <= ratio_exit:
            on, killed, entry, peak, vix_hi, held = True, False, None, None, None, 0
            episodes += 1
        elif on and ratio > ratio_exit:
            on = False
        if scope == "stretch" and rv < 0.20:
            killed, entry, peak, vix_hi, held = False, None, None, None, 0
        allowed = on and not killed and rv >= 0.20
        if allowed:
            if entry is None:
                entry, peak, vix_hi = px, px, vix
            peak, vix_hi = max(peak, px), max(vix_hi, vix)
            held += 1
            hit = ((tp is not None and px >= entry * (1 + tp)) or
                   (trail is not None and px <= peak * (1 - trail)) or
                   (stop is not None and px <= entry * (1 - stop)) or
                   (time is not None and held >= time) or
                   (fade is not None and vix <= vix_hi * (1 - fade)))
            if hit:
                killed, allowed = True, False
        out.append(allowed)
    return pd.Series(out, index=m["vix"].index), episodes


def build(d, g):
    w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})
    mv = d.wbox * SHARE * g
    w["VIXM"] = mv
    w["BOXX"] -= mv
    return w


def main():
    d, r = load()
    rf = r.BOXX
    m = market(d.index)
    live = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})

    # 1. how much does VIXM decay under the current rule?
    g0, _ = gate(m)
    w0 = build(d, g0)
    held = w0.VIXM.shift(1) > 0
    ex = (r.VIXM - r.BOXX)
    contrib = (w0.VIXM.shift(1) * ex).fillna(0)
    print("Decay under the current rule (75%, filter on):")
    print(f"   VIXM held on {held.mean():.0%} of days; on those days VIXM vs BOXX averages {ex[held].mean() * 252:+.0%}/yr, "
          f"median day {ex[held].median() * 100:+.2f}%")
    print(f"   share of held days VIXM lost to BOXX: {(ex[held] < 0).mean():.0%}")
    print(f"   total contribution to the book: gains {contrib[contrib > 0].sum():+.1%}, losses {contrib[contrib < 0].sum():+.1%}, "
          f"net {contrib.sum():+.1%} (simple sum over 10 years)")
    runs = (held != held.shift()).cumsum()[held]
    lens = runs.value_counts()
    print(f"   holding stretches: {len(lens)}, median {lens.median():.0f} sessions, longest {lens.max()} sessions\n")

    cases = {"Live (all BOXX)": live, "Current rule (inversion exit only)": w0}
    specs = {}
    for x in (0.10, 0.20, 0.30): specs[f"tp +{int(x * 100)}%"] = dict(tp=x)
    for x in (0.05, 0.10, 0.15): specs[f"trail -{int(x * 100)}% from peak"] = dict(trail=x)
    for x in (0.05, 0.10, 0.15): specs[f"stop -{int(x * 100)}% from entry"] = dict(stop=x)
    for x in (10, 20, 40): specs[f"time {x} sessions"] = dict(time=x)
    for x in (0.15, 0.25, 0.35): specs[f"VIX fade -{int(x * 100)}% from high"] = dict(fade=x)
    for x in (0.90, 0.95): specs[f"inversion exit at {x}"] = dict(ratio_exit=x)
    for n, kw in specs.items():
        cases[n] = build(d, gate(m, **kw)[0])
    for n in ["tp +10%", "stop -5% from entry", "time 20 sessions"]:
        cases[n + " (episode-wide block)"] = build(d, gate(m, **specs[n], scope="episode")[0])

    rows, rets = {}, {}
    for n, w in cases.items():
        x = run(w, r)
        rets[n] = x
        s = summary(x, rf)
        s.update({lab: (1 + x.loc[a:b]).prod() - 1 for lab, a, b in EVENTS})
        s["avg VIXM"] = w.VIXM.mean()
        rows[n] = s
    t = pd.DataFrame(rows).T
    base = t.loc["Current rule (inversion exit only)"]
    out = fmt(t)
    out["both halves vs current"] = [("yes" if (t.loc[n, "h1 Sharpe"] > base["h1 Sharpe"] and t.loc[n, "h2 Sharpe"] > base["h2 Sharpe"]) else "")
                                     for n in t.index]
    print(out.to_string())

    winners = [n for n in specs if out.loc[n, "both halves vs current"] == "yes"]
    print(f"\nBeat the current rule on both halves: {winners or 'none'}")
    if len(winners) >= 2:
        best = sorted(winners, key=lambda n: -t.loc[n, "Sharpe"])[:2]
        kw = {**specs[best[0]], **specs[best[1]]}
        x = run(build(d, gate(m, **kw)[0]), r)
        print(f"Combined {best}:")
        print(fmt(pd.DataFrame({"combined": summary(x, rf)}).T).to_string())


if __name__ == "__main__":
    main()
