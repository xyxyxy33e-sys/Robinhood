"""Robustness review of the final VIXM rule before it goes into the live design.

Final rule: signal ON when VIX < 18, OFF when VIX > VIX3M; VIXM only while QQQ 30-day realized
vol >= 20%; VIXM = 75% of the BOXX slot; sell early if VIX falls 25% below its high since entry.

Checks: (1) VIXM trading cost up to 30 bp one-way, (2) one extra session of delay on every
VIXM decision, (3) every neighbouring parameter set, (4) the post-2019 and post-2021 windows.

    python -m research.regime_tape_final_review
"""
import itertools
import math

import numpy as np
import pandas as pd
import yfinance as yf

from research.regime_tape_sleeve import COST, fmt, load
from research.regime_tape_vixm import summary


def market(idx):
    v = yf.download(["^VIX", "^VIX3M", "QQQ", "VIXM"], start="2015-06-01", end="2026-08-28", progress=False,
                    auto_adjust=True)["Close"].ffill()
    rv = v.QQQ.pct_change().rolling(30).std() * math.sqrt(252)
    return pd.DataFrame({"vix": v["^VIX"], "ratio": v["^VIX"] / v["^VIX3M"], "rv": rv}).reindex(idx).ffill()


def gate(mk, gate_lvl=18, rv_min=0.20, fade=0.25, lag=1):
    m = mk.shift(lag)
    on = False; killed = False; hi = None; out = []
    for vix, ratio, rv in zip(m.vix, m.ratio, m.rv):
        if np.isnan(vix) or np.isnan(ratio) or np.isnan(rv):
            out.append(False); continue
        if not on and vix < gate_lvl and ratio <= 1.0:
            on, killed, hi = True, False, None
        elif on and ratio > 1.0:
            on = False
        if rv < rv_min:
            killed, hi = False, None
        ok = on and not killed and rv >= rv_min
        if ok:
            hi = vix if hi is None else max(hi, vix)
            if fade is not None and vix <= hi * (1 - fade):
                killed, ok = True, False
        out.append(ok)
    return pd.Series(out, index=mk.index)


def run(d, r, g, share=0.75, vixm_cost=COST):
    w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})
    mv = d.wbox * share * g
    w["VIXM"] = mv
    w["BOXX"] -= mv
    held = w.shift(1).fillna(0)
    dw = held.diff().abs().fillna(0)
    cost = dw.drop(columns="VIXM").sum(axis=1) * COST + dw.VIXM * vixm_cost
    return (held * r[held.columns]).sum(axis=1) - cost


def main():
    d, r = load()
    rf = r.BOXX
    mk = market(d.index)
    live = run(d, r, pd.Series(False, index=d.index))
    final = run(d, r, gate(mk))
    L, F = summary(live, rf), summary(final, rf)

    print("1) VIXM trading cost (one-way) -- base case assumed 4 bp")
    rows = {"Live": L}
    for c in (0.0004, 0.0010, 0.0020, 0.0030):
        rows[f"final @ {c * 1e4:.0f} bp"] = summary(run(d, r, gate(mk), vixm_cost=c), rf)
    print(fmt(pd.DataFrame(rows).T).to_string())

    print("\n2) One extra session of delay on every VIXM decision")
    rows = {"Live": L, "final (normal)": F, "final (+1 day late)": summary(run(d, r, gate(mk, lag=2)), rf),
            "final (+2 days late)": summary(run(d, r, gate(mk, lag=3)), rf)}
    print(fmt(pd.DataFrame(rows).T).to_string())

    print("\n3) Neighbouring parameters: gate 16/18/20 x share 50/75/100% x QQQ vol 18/20/22% x fade none/15/25/35%")
    res = []
    for g_, sh, rv_, fd in itertools.product((16, 18, 20), (0.5, 0.75, 1.0), (0.18, 0.20, 0.22), (None, 0.15, 0.25, 0.35)):
        s = summary(run(d, r, gate(mk, g_, rv_, fd), share=sh), rf)
        res.append({**s, "params": (g_, sh, rv_, fd)})
    t = pd.DataFrame(res)
    both = (t["h1 Sharpe"] > L["h1 Sharpe"]) & (t["h2 Sharpe"] > L["h2 Sharpe"])
    print(f"   {both.sum()} of {len(t)} neighbours beat live on BOTH halves; "
          f"{(t.MaxDD < L['MaxDD'] - 0.01).sum()} deepen max drawdown by >1pt")
    print(f"   Sharpe range {t.Sharpe.min():.2f}-{t.Sharpe.max():.2f} (live {L['Sharpe']:.2f}, final {F['Sharpe']:.2f}); "
          f"recent-half range {t['h2 Sharpe'].min():.2f}-{t['h2 Sharpe'].max():.2f} (live {L['h2 Sharpe']:.2f})")
    print(f"   final's rank among neighbours by Sharpe: {int((t.Sharpe > F['Sharpe']).sum()) + 1} of {len(t)}")

    print("\n4) Later windows")
    from research.regime_tape_sleeve import stats
    for a in ("2019-01-01", "2021-07-01", "2023-01-01"):
        sl, sf = stats(live.loc[a:], rf.loc[a:]), stats(final.loc[a:], rf.loc[a:])
        print(f"   from {a}: live CAGR {sl['CAGR']:+.1%} MaxDD {sl['MaxDD']:+.1%} Sharpe {sl['Sharpe']:.2f} | "
              f"final CAGR {sf['CAGR']:+.1%} MaxDD {sf['MaxDD']:+.1%} Sharpe {sf['Sharpe']:.2f}")

    g = gate(mk)
    trades = (g != g.shift()).sum() - 1
    print(f"\nVIXM on/off switches: {trades} in {len(d) / 252:.1f} yrs ({trades / (len(d) / 252):.0f}/yr); held {g.mean():.0%} of days")


if __name__ == "__main__":
    main()
