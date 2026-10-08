"""Per-state VIX entry gate for the VIXM rule in the Regime Tape BOXX slot.

Rule: signal ON when VIX closes below the gate, stays ON until VIX closes above VIX3M.
While ON, 50% of the BOXX slot sits in VIXM. Here each state may use its own gate; one state
is varied at a time with the others at 18, kept only if it beats gate=18 on both halves.

    python -m research.regime_tape_gates
"""
import pandas as pd
import yfinance as yf

from research.regime_tape_sleeve import fmt, load
from research.regime_tape_vixm import run, summary

GATES = [14, 16, 18, 20, 22, 99]          # 99 = no gate: hold VIXM whenever the curve is not inverted
SHARE = 0.5


def signals(idx):
    v = yf.download(["^VIX", "^VIX3M"], start="2015-06-01", end="2026-08-28", progress=False, auto_adjust=True)["Close"].ffill()
    ratio = v["^VIX"] / v["^VIX3M"]
    out = {}
    for g in GATES:
        on, s = False, []
        for vix, rr in zip(v["^VIX"], ratio):
            if not on and vix < g and rr <= 1.0:
                on = True
            elif on and rr > 1.0:
                on = False
            s.append(on)
        out[g] = pd.Series(s, index=v.index).reindex(idx).ffill().shift(1).fillna(False).astype(bool)
    return out


def build(d, sig, gates):
    w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0})
    on = pd.Series(False, index=d.index)
    for st, g in gates.items():
        m = d.s == st
        on[m] = sig[g][m]
    mv = w.BOXX * SHARE * on
    w["VIXM"] += mv
    w["BOXX"] -= mv
    return w


def episodes(d, st):
    """Separate visits to a state that had money in the BOXX slot."""
    m = (d.s == st) & (d.wbox > 0)
    return int((m & ~m.shift(1, fill_value=False)).sum())


def main():
    d, r = load()
    rf = r.BOXX
    sig = signals(d.index)
    uniform = {s: 18 for s in "ABCDEF"}
    base = summary(run(build(d, sig, uniform), r), rf)
    none = summary(run(build(d, sig, {s: 0 for s in "ABCDEF"} | {}), r), rf) if False else None

    print("Uniform gates (all states the same):")
    rows = {}
    for g in GATES:
        rows[f"gate {g if g < 99 else 'none'}"] = summary(run(build(d, sig, {s: g for s in 'ABCDEF'}), r), rf)
    print(fmt(pd.DataFrame(rows).T).to_string())

    print("\nOne state at a time (others at 18). Δ vs uniform 18; 'keep' = better Sharpe on both halves, MaxDD no worse than 0.5pt")
    out, pick = [], {}
    for st in "ABCDEF":
        best = None
        for g in GATES:
            if g == 18:
                continue
            s = summary(run(build(d, sig, uniform | {st: g}), r), rf)
            dh1, dh2 = s["h1 Sharpe"] - base["h1 Sharpe"], s["h2 Sharpe"] - base["h2 Sharpe"]
            keep = dh1 > 0.005 and dh2 > 0.005 and s["MaxDD"] >= base["MaxDD"] - 0.005
            out.append({"state": st, "episodes w/ slot": episodes(d, st), "gate": g if g < 99 else "none",
                        "dSharpe h1": f"{dh1:+.3f}", "dSharpe h2": f"{dh2:+.3f}", "dCAGR": f"{s['CAGR'] - base['CAGR']:+.1%}",
                        "dMaxDD": f"{s['MaxDD'] - base['MaxDD']:+.1%}", "keep": "yes" if keep else ""})
            if keep and (best is None or min(dh1, dh2) > best[0]):
                best = (min(dh1, dh2), g)
        if best:
            pick[st] = best[1]
    print(pd.DataFrame(out).to_string(index=False))

    combo = uniform | pick
    print(f"\nPer-state picks: {pick or 'none'}")
    res = {"Gate 18 everywhere": base, f"Per-state {combo}": summary(run(build(d, sig, combo), r), rf)}
    print(fmt(pd.DataFrame(res).T).to_string())


if __name__ == "__main__":
    main()
