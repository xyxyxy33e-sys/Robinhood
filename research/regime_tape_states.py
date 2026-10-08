"""Per-state composition of the BOXX slot in the live Regime Tape design.

For each state (A-F), try a few mixes of BOXX / VIXM / gold in that state's BOXX slot while
every other state stays 100% BOXX. A change is only kept if it helps on BOTH halves of the
window (2016-08..2021-06 and 2021-07..2026-08); the kept per-state choices are then combined
and compared with uniform mixes.

    python -m research.regime_tape_states
"""
import itertools

import pandas as pd

from research.regime_tape_sleeve import fmt, load, replay, stats

MIXES = {
    "BOXX": {"BOXX": 1},
    "90/10 VIXM": {"BOXX": .9, "VIXM": .1},
    "80/20 VIXM": {"BOXX": .8, "VIXM": .2},
    "60/40 VIXM": {"BOXX": .6, "VIXM": .4},
    "100 VIXM": {"VIXM": 1},
    "50/50 gold": {"BOXX": .5, "IAU": .5},
    "40/40/20": {"BOXX": .4, "IAU": .4, "VIXM": .2},
}
HALVES = [("2016-08-29", "2021-06-30"), ("2021-07-01", "2026-08-27")]


def score(x, rf):
    out = {}
    for tag, (a, b) in zip(("h1", "h2"), HALVES):
        s = stats(x.loc[a:b], rf.loc[a:b])
        out[f"{tag} Sharpe"], out[f"{tag} MaxDD"] = s["Sharpe"], s["MaxDD"]
    s = stats(x, rf)
    out.update({"CAGR": s["CAGR"], "MaxDD": s["MaxDD"], "Sharpe": s["Sharpe"], "Worst 12m": s["Worst 12m"]})
    return out


def main():
    d, r = load()
    rf = r.BOXX
    print("BOXX slot by state (avg share of book when in that state, days):")
    print("   " + "  ".join(f"{s} {d.wbox[d.s == s].mean():.0%}/{(d.s == s).sum()}" for s in "ABCDEF"))
    base = score(replay(d, r, MIXES["BOXX"]), rf)

    print("\nVIXM and gold vs BOXX inside each state's slot (annualised excess return while held):")
    for a in ["VIXM", "IAU"]:
        row = []
        for st in "ABCDEF":
            m = (d.s.shift(1) == st) & (d.wbox.shift(1) > 0)
            row.append(f"{st} {((r[a] - r.BOXX)[m]).mean() * 252:+6.1%}")
        print(f"   {a:5s} " + "  ".join(row))

    rows, keep = [], {}
    for st in "ABCDEF":
        best = None
        for name, mix in MIXES.items():
            if name == "BOXX":
                continue
            s = score(replay(d, r, MIXES["BOXX"], {st: mix}), rf)
            both = s["h1 Sharpe"] > base["h1 Sharpe"] and s["h2 Sharpe"] > base["h2 Sharpe"]
            no_dd = s["MaxDD"] >= base["MaxDD"] - 0.005
            rows.append({"state": st, "mix": name, "dSharpe h1": s["h1 Sharpe"] - base["h1 Sharpe"],
                         "dSharpe h2": s["h2 Sharpe"] - base["h2 Sharpe"], "dCAGR": s["CAGR"] - base["CAGR"],
                         "dMaxDD": s["MaxDD"] - base["MaxDD"], "dWorst12m": s["Worst 12m"] - base["Worst 12m"],
                         "keep": "yes" if both and no_dd else ""})
            if both and no_dd:
                gain = min(s["h1 Sharpe"] - base["h1 Sharpe"], s["h2 Sharpe"] - base["h2 Sharpe"])
                if best is None or gain > best[0]:
                    best = (gain, name)
        if best:
            keep[st] = best[1]
    t = pd.DataFrame(rows)
    for c in ["dSharpe h1", "dSharpe h2"]:
        t[c] = t[c].map(lambda x: f"{x:+.3f}")
    for c in ["dCAGR", "dMaxDD", "dWorst12m"]:
        t[c] = t[c].map(lambda x: f"{x:+.1%}")
    print("\nOne state at a time (deltas vs all-BOXX; 'keep' = better Sharpe in both halves and MaxDD no worse than 0.5pt):")
    print(t.to_string(index=False))

    print(f"\nPer-state picks: {keep or 'none'}")
    combos = {
        "All BOXX (live)": (MIXES["BOXX"], None),
        "Uniform 80/20 VIXM": (MIXES["80/20 VIXM"], None),
        "Uniform 50/50 gold": (MIXES["50/50 gold"], None),
        "Uniform 40/40/20": (MIXES["40/40/20"], None),
        "Per-state picks": (MIXES["BOXX"], {s: MIXES[m] for s, m in keep.items()}),
    }
    out = {n: score(replay(d, r, sl, bs), rf) for n, (sl, bs) in combos.items()}
    print(fmt(pd.DataFrame(out).T).to_string())


if __name__ == "__main__":
    main()
