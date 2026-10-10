"""More VIXM ideas for the live Regime Tape design.

Finding so far: VIXM pays when volatility jumps from a CALM base and loses when bought after
a spike -- so the regime state (a price-trend signal) is the wrong trigger. These variants key
VIXM off the volatility market itself:

  slot-cheap    BOXX slot holds VIXM only while insurance is cheap (VIX < x, or VIX/VIX3M < x)
  slot-tp       same, but exit into BOXX as soon as the curve inverts (take the spike's profit)
  overlay       a small always-on VIXM hedge in state A, funded pro rata from SPMO/TQQQ
  overlay-cheap the same hedge, only while insurance is cheap, with the same take-profit

Vol signals use closes two sessions back (VIX settles 16:15, after the ETFs), on top of the
page's own one-session lag. 4 bp one-way cost on every weight change.

    python -m research.regime_tape_vixm
"""
import pandas as pd
import yfinance as yf

from research.regime_tape_sleeve import COST, fmt, load, stats

HALVES = [("2016-08-29", "2021-06-30"), ("2021-07-01", "2026-08-27")]
EVENTS = [("Feb 2018", "2018-01-26", "2018-02-09"), ("Q4 2018", "2018-10-01", "2018-12-24"),
          ("Covid 2020", "2020-02-19", "2020-03-23"), ("2022 bear", "2022-01-03", "2022-10-14"),
          ("Aug 2024", "2024-07-10", "2024-08-07"), ("Apr 2025", "2025-02-19", "2025-04-08"),
          ("Mar 2026", "2026-02-27", "2026-03-30")]


def vol_signals(idx):
    v = yf.download(["^VIX", "^VIX3M"], start="2015-06-01", end="2026-08-28", progress=False, auto_adjust=True)["Close"]
    v = v.reindex(idx).ffill()
    ratio = v["^VIX"] / v["^VIX3M"]
    sig = {
        "VIX<16": v["^VIX"] < 16,
        "VIX<18": v["^VIX"] < 18,
        "ratio<0.88": ratio < 0.88,
        "ratio<0.92": ratio < 0.92,
    }
    # take-profit versions: enter when cheap, stay until the curve inverts (ratio > 1)
    for k in ["VIX<18", "ratio<0.88"]:
        on, out = False, []
        for c, r in zip(sig[k], ratio):
            if not on and c:
                on = True
            elif on and r > 1.0:
                on = False
            out.append(on)
        sig[k + " until inverted"] = pd.Series(out, index=idx)
    return {k: s.shift(1).fillna(False).astype(bool) for k, s in sig.items()}   # +1 session on top of weights' own lag


def build(d, slot=None, overlay=0.0, overlay_sig=None, overlay_states=("A",), gold_states=()):
    """slot: (share of BOXX slot in VIXM, signal or None=always). Returns weight frame."""
    w = pd.DataFrame({"SPMO": d.wc, "TQQQ": d.wt, "QLD": d.wq, "BOXX": d.wbox, "VIXM": 0.0, "IAU": 0.0})
    if gold_states:
        m = d.s.isin(gold_states)
        w.loc[m, "IAU"] = 0.5 * d.wbox[m]
        w.loc[m, "BOXX"] = 0.5 * d.wbox[m]
    if slot:
        share, sig = slot
        on = sig if sig is not None else pd.Series(True, index=d.index)
        move = w.BOXX * share * on
        w["VIXM"] += move
        w["BOXX"] -= move
    if overlay:
        on = d.s.isin(overlay_states) & (overlay_sig if overlay_sig is not None else True)
        risky = w[["SPMO", "TQQQ", "QLD"]].sum(axis=1)
        h = (overlay * on).where(risky > 0, 0)
        for c in ["SPMO", "TQQQ", "QLD"]:
            w[c] = w[c] - h * w[c] / risky.where(risky > 0, 1)
        w["VIXM"] += h
    return w


def run(w, r):
    held = w.shift(1).fillna(0)
    return (held * r[held.columns]).sum(axis=1) - held.diff().abs().sum(axis=1).fillna(0) * COST


def summary(x, rf):
    s = stats(x, rf)
    out = {"CAGR": s["CAGR"], "MaxDD": s["MaxDD"], "Sharpe": s["Sharpe"], "Worst 12m": s["Worst 12m"]}
    for tag, (a, b) in zip(("h1", "h2"), HALVES):
        out[f"{tag} Sharpe"] = stats(x.loc[a:b], rf.loc[a:b])["Sharpe"]
    return out


def main():
    d, r = load()
    rf = r.BOXX
    sig = vol_signals(d.index)
    print("share of days each signal is on: " + "  ".join(f"{k} {v.mean():.0%}" for k, v in sig.items()))

    cases = {"All BOXX (live)": build(d), "Static 20% VIXM in slot (last test)": build(d, slot=(0.2, None))}
    for k in sig:
        for share in (0.2, 0.5):
            cases[f"slot {int(share * 100)}% VIXM when {k}"] = build(d, slot=(share, sig[k]))
    for h in (0.03, 0.05, 0.10):
        cases[f"overlay {int(h * 100)}% VIXM in A, always"] = build(d, overlay=h)
        cases[f"overlay {int(h * 100)}% VIXM in A, ratio<0.88 until inverted"] = build(d, overlay=h, overlay_sig=sig["ratio<0.88 until inverted"])
        cases[f"overlay {int(h * 100)}% VIXM in A+D, ratio<0.88 until inverted"] = build(d, overlay=h, overlay_sig=sig["ratio<0.88 until inverted"], overlay_states=("A", "D"))

    res = {n: summary(run(w, r), rf) for n, w in cases.items()}
    t = pd.DataFrame(res).T
    base = t.loc["All BOXX (live)"]
    t["both halves better"] = ((t["h1 Sharpe"] > base["h1 Sharpe"]) & (t["h2 Sharpe"] > base["h2 Sharpe"])).map({True: "yes", False: ""})
    show = t.drop(columns="both halves better")
    out = fmt(show)
    out["both halves"] = t["both halves better"]
    print(out.to_string())

    winners = t[(t["both halves better"] == "yes") & (t.MaxDD >= base.MaxDD - 0.005)].sort_values("Sharpe", ascending=False)
    print(f"\nPass both halves with no deeper drawdown: {len(winners)}")
    pick = winners.index[0] if len(winners) else None
    if pick:
        print(f"Best of those: {pick}")

    print("\nEvent returns (strategy, period total):")
    ev_cases = {"All BOXX": cases["All BOXX (live)"], "Static 20% slot": cases["Static 20% VIXM in slot (last test)"]}
    if pick:
        ev_cases[pick] = cases[pick]
    gold = build(d, gold_states=("A", "C", "E"))
    ev_cases["Gold A/C/E (prev. rec.)"] = gold
    if pick:
        # rebuild pick on top of gold
        p = pick
        if p.startswith("overlay"):
            h = int(p.split()[1].rstrip("%")) / 100
            st = ("A", "D") if "A+D" in p else ("A",)
            ov = sig["ratio<0.88 until inverted"] if "until inverted" in p else None
            ev_cases["Gold A/C/E + " + p] = build(d, overlay=h, overlay_sig=ov, overlay_states=st, gold_states=("A", "C", "E"))
        else:
            share = int(p.split()[1].rstrip("%")) / 100
            k = p.split(" when ")[1]
            ev_cases["Gold A/C/E + " + p] = build(d, slot=(share, sig[k]), gold_states=("A", "C", "E"))
    rows = {}
    for n, w in ev_cases.items():
        x = run(w, r)
        rows[n] = {lab: (1 + x.loc[a:b]).prod() - 1 for lab, a, b in EVENTS}
    print(pd.DataFrame(rows).map(lambda v: f"{v:+.1%}").to_string())
    print("\nCombined with the gold rule:")
    print(fmt(pd.DataFrame({n: summary(run(w, r), rf) for n, w in ev_cases.items()}).T).to_string())


if __name__ == "__main__":
    main()
