"""More trim-vote levels, 10% of the book per level (owner, 2026-10-09).

On effective-A days a ladder of extension levels (QQQ's gap above a long SMA) is counted like the
live trim v2 votes: the held level rises at once to the raw count, steps down ONE level only on a
new 15-session closing high (never below the raw count), and resets after more than 3 sessions out
of A (A_SPELL_GAP_CARRY). Each held level moves 10% of the book out of TQQQ, to SPMO or to cash.

Modes:
  replace -- the ladder replaces the live trim (live held votes ignored; TQQQ leaves only as the
             ladder climbs)
  front   -- the ladder runs in front of the live trim: it steps TQQQ down early, and the live trim
             v2 still takes all TQQQ out (and cuts SPMO 1/6 per vote) at its own votes

Ladders (gap = close / SMA - 1):
  g200s2: 200d, 7 levels at 3,5,7,9,11,13,15%
  g150s2: 150d, 7 levels at 2,4,6,8,10,12,14%
  g100s15:100d, 7 levels at 1.5,3,4.5,6,7.5,9,10.5%
  mix:    one level each for 100d>{4,7,10}%, 150d>{6,9,12}%, 200d>{9,12,15}% (9 levels)

Judged against the plain-ratio frontier (CAGR at equal max drawdown) on real ETFs (VIXM on) and on
the 2001-2026 proxy, with a block bootstrap of Sharpe against plain 40/60.

    python -m research.a_vote_ladder
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at

LADDERS = {
    "g200s2": [(200, x) for x in (0.03, 0.05, 0.07, 0.09, 0.11, 0.13, 0.15)],
    "g150s2": [(150, x) for x in (0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14)],
    "g100s15": [(100, x) for x in (0.015, 0.03, 0.045, 0.06, 0.075, 0.09, 0.105)],
    "mix": [(100, 0.04), (100, 0.07), (100, 0.10), (150, 0.06), (150, 0.09), (150, 0.12),
            (200, 0.09), (200, 0.12), (200, 0.15)],
}


def ladder_series(P, closes, ladder, n=S.EXTENSION_REENTRY_HIGH_N, carry=S.A_SPELL_GAP_CARRY):
    held, gapn, out = 0, 0, {}
    dates = P["dates"]
    for i, d in enumerate(dates):
        eff = S.effective_state(P["st"][d], P["fa"][d])
        if eff != "A":
            gapn += 1
            if gapn > carry:
                held = 0
            out[d] = 0
            continue
        gapn = 0
        g = P["gp"][d]
        raw = sum(1 for w, x in ladder if g.get(w) is not None and g[w] > x)
        if raw > held:
            held = raw
        elif held > raw and closes[i] >= max(closes[max(0, i - n + 1):i + 1]):
            held -= 1
        out[d] = held
    return out


def run_ladder(P, lad, base, mode=None, to="SPMO", step=0.10, start="2015-11-02", end="2026-10-07", vixm=True):
    out, prev, held = [], None, None
    sim = [d for d in P["dates"] if start <= d <= end]
    for d in sim:
        if held is not None:
            rr = P["r"].loc[d, LEGS].values
            g = float(np.dot(held, rr))
            held = held * (1 + rr) / (1 + g)
            out.append([d, g])
        st, fa, gaps = P["st"][d], P["fa"][d], P["gp"][d]
        eff = S.effective_state(st, fa)
        t = dict(P["trim"][d])
        k = lad[d] if (mode and lad) else 0
        if t["in_a"]:
            c0, t0 = base
            cut = min(t0, step * k)
            t["base"] = (c0 + cut, t0 - cut) if to == "SPMO" else (c0, t0 - cut)
            if mode == "replace":
                t["held"] = 0
        bp = P["pct"].get(d)
        gate = S.d_gate_active(st, bp if bp is not None else 1.0, gaps.get(200))
        w5 = S.target_weights_with_voltarget(st, P["mi"][d], P["vol"][d], fast_state=fa, gaps=gaps,
                                             d_gate=gate, a_trim=t)
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")), k)
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                out[-1][1] = (1 + out[-1][1]) * (1 - COST * float(np.abs(tgt - held).sum())) - 1
            held = tgt.copy()
        prev = key
    return pd.Series({pd.Timestamp(d): g for d, g in out})


if __name__ == "__main__":
    px = load(); P = prepare(px)
    closes = [float(px["QQQ"].dropna().loc[d]) for d in P["dates"]]
    lads = {nm: ladder_series(P, closes, L) for nm, L in LADDERS.items()}
    pd.set_option("display.width", 260)
    res = {}
    for label, Q, kw in (("REAL", P, dict()), ("PROXY", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front, rows, ser = [], {}, {}
        for c in (0.7, 0.6, 0.5, 0.4, 0.3, 0.2):
            s = run_ladder(Q, None, (c, round(1 - c, 2)), **kw); st_ = stats(s)
            front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
            rows[f"plain {c*100:.0f}/{(1-c)*100:.0f}"] = {k: float(v) for k, v in st_.items()}; ser[f"plain{c}"] = s
        for nm in LADDERS:
            for mode in ("replace", "front"):
                for to in ("SPMO", "cash"):
                    for base in ((0.3, 0.7), (0.4, 0.6)):
                        s = run_ladder(Q, lads[nm], base, mode=mode, to=to, **kw)
                        r = {kk: float(v) for kk, v in stats(s).items()}
                        r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
                        key = f"{nm} {mode} ->{to} from {base[0]*100:.0f}/{base[1]*100:.0f}"
                        rows[key] = r; ser[key] = s
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print(f"\n{label}")
        print(t[["CAGR", "Sharpe", "MaxDD", "Y2022", "h1", "h2", "vs frontier"]].round(3).to_string())
    tr, tp = res["REAL"][0], res["PROXY"][0]
    both = [i for i in tr.index if not i.startswith("plain") and tr.loc[i, "vs frontier"] > 0 and tp.loc[i, "vs frontier"] > 0]
    print("\nAhead of the plain-ratio frontier on BOTH real and proxy:", both or "none")
    for nm in both:
        for lab in ("REAL", "PROXY"):
            t, ser = res[lab]
            ci, p = block_boot(ser[nm], ser["plain0.4"])
            print(f"  {lab} {nm}: {t.loc[nm,'vs frontier']*100:+.2f}pp vs frontier; Sharpe vs plain 40/60 CI {ci.round(3)} P<=0 {p:.2f}")
    # how often each ladder is engaged on A days
    adays = [d for d in P["dates"] if d >= "2015-11-02" and S.effective_state(P["st"][d], P["fa"][d]) == "A"]
    for nm, L in lads.items():
        v = np.array([L[d] for d in adays]); print(f"{nm}: mean held level on A days {v.mean():.2f}, share of A days with >=1 level {np.mean(v>0):.2f}")


# Second pass (same day): ladders that start higher, so the book holds the full base most of the
# time and steps down only as QQQ stretches, reaching zero TQQQ near the live trim lines.
LADDERS_HI = {
    "g200 7..15%": [(200, x) for x in np.linspace(0.07, 0.15, 7)],
    "g200 5..14%": [(200, x) for x in np.linspace(0.05, 0.14, 7)],
    "g150 5..12%": [(150, x) for x in np.linspace(0.05, 0.12, 7)],
    "g150 4..11%": [(150, x) for x in np.linspace(0.04, 0.11, 7)],
    "g100 3..10%": [(100, x) for x in np.linspace(0.03, 0.10, 7)],
}


def avg_tqqq_on_a(P, lad, base, step=0.10, start="2015-11-02"):
    v = [max(0.0, base[1] - step * lad[d]) for d in P["dates"]
         if d >= start and S.effective_state(P["st"][d], P["fa"][d]) == "A"]
    return float(np.mean(v))


def second_pass():
    px = load(); P = prepare(px)
    closes = [float(px["QQQ"].dropna().loc[d]) for d in P["dates"]]
    lads = {nm: ladder_series(P, closes, L) for nm, L in LADDERS_HI.items()}
    pd.set_option("display.width", 260)
    res = {}
    for label, Q, kw in (("REAL", P, dict()), ("PROXY", proxy_returns(P, px), dict(start="2001-01-02", vixm=False))):
        front, rows, ser = [], {}, {}
        for c in (0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1):
            s = run_ladder(Q, None, (c, round(1 - c, 2)), **kw); st_ = stats(s)
            front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
            rows[f"plain {c*100:.0f}/{(1-c)*100:.0f}"] = {k: float(v) for k, v in st_.items()}; ser[f"plain{c}"] = s
        for nm in LADDERS_HI:
            for mode in ("front", "replace"):
                for to in ("SPMO", "cash"):
                    for base in ((0.3, 0.7), (0.2, 0.8)):
                        s = run_ladder(Q, lads[nm], base, mode=mode, to=to, **kw)
                        r = {kk: float(v) for kk, v in stats(s).items()}
                        r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
                        r["avg TQQQ in A"] = avg_tqqq_on_a(P, lads[nm], base)
                        key = f"{nm} {mode} ->{to} from {base[0]*100:.0f}/{base[1]*100:.0f}"
                        rows[key] = r; ser[key] = s
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print(f"\n{label}")
        print(t[["CAGR", "Sharpe", "MaxDD", "Y2022", "h1", "h2", "avg TQQQ in A", "vs frontier"]].round(3).to_string())
    tr, tp = res["REAL"][0], res["PROXY"][0]
    both = [i for i in tr.index if not i.startswith("plain") and tr.loc[i, "vs frontier"] > 0 and tp.loc[i, "vs frontier"] > 0]
    print("\nAhead of the plain-ratio frontier on BOTH real and proxy:", both or "none")
    for nm in both:
        for lab in ("REAL", "PROXY"):
            t, ser = res[lab]
            ci, p = block_boot(ser[nm], ser["plain0.4"])
            print(f"  {lab} {nm}: {t.loc[nm,'vs frontier']*100:+.2f}pp vs frontier, Sharpe {t.loc[nm,'Sharpe']:.3f}; vs plain 40/60 CI {ci.round(3)} P<=0 {p:.2f}")
