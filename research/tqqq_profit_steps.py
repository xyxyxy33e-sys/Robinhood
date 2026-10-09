"""Take profit on TQQQ in three steps keyed to TQQQ's OWN gain: +10%, +15%, +20% (owner, 2026-10-09).

Live rules as research/a_ratio_live_rules.py. On effective-A days, each threshold TQQQ's gain has
reached cuts one third of the TQQQ base, moved to SPMO or to cash; the live trim v2 still does the
full exit at its own votes. TQQQ's gain is measured two ways:
  spell:   since the A spell began (close of its first day); steps only add up within the spell and
           reset when a new A spell starts (pure profit-taking)
  roll20:  TQQQ's 20-session return; the step count follows it up and down
Judged against the plain-ratio upper envelope (CAGR at equal or shallower max drawdown).

    python -m research.tqqq_profit_steps
"""
import numpy as np
import pandas as pd

from research.a_ratio_live_rules import LEGS, COST, S, load, prepare, stats, block_boot, proxy_returns
from research.a7030_quick_exit import frontier_cagr_at

TH = (0.10, 0.15, 0.20)


def run_tp(P, tq, base, kind=None, th=TH, to="SPMO", start="2015-11-02", end="2026-10-07", vixm=True):
    out, prev, held = [], None, None
    spell, ref, k = None, None, 0
    idx = {d: i for i, d in enumerate(P["dates"])}
    steps_days = a_days = 0
    for d in (d for d in P["dates"] if start <= d <= end):
        if held is not None:
            rr = P["r"].loc[d, LEGS].values
            g = float(np.dot(held, rr))
            held = held * (1 + rr) / (1 + g)
            out.append([d, g])
        st, fa, gaps = P["st"][d], P["fa"][d], P["gp"][d]
        eff = S.effective_state(st, fa)
        t = dict(P["trim"][d])
        lvl = 0
        if kind and t["in_a"]:
            if kind == "spell":
                if t["spell_start"] != spell:
                    spell, ref, k = t["spell_start"], tq.get(t["spell_start"], tq[d]), 0
                k = max(k, sum(1 for x in th if tq[d] / ref - 1 >= x))
                lvl = k
            else:
                i = idx[d]
                if i >= 20:
                    lvl = sum(1 for x in th if tq[d] / tq[P["dates"][i - 20]] - 1 >= x)
        if t["in_a"]:
            a_days += 1; steps_days += lvl > 0
            c0, t0 = base
            cut = t0 * lvl / 3.0
            t["base"] = (c0 + cut, t0 - cut) if to == "SPMO" else (c0, t0 - cut)
        bp = P["pct"].get(d)
        gate = S.d_gate_active(st, bp if bp is not None else 1.0, gaps.get(200))
        w5 = S.target_weights_with_voltarget(st, P["mi"][d], P["vol"][d], fast_state=fa, gaps=gaps,
                                             d_gate=gate, a_trim=t)
        vx = P["vxm"].get(d, {"allowed": False}) if vixm else {"allowed": False}
        tgt = np.array(S.apply_vixm(w5, vx))
        key = (eff, t["held"], gate, bool(vx.get("allowed")), lvl)
        changed = prev is not None and key != prev
        do, _, _ = S.needs_rebalance(tuple(tgt), tuple(held) if held is not None else None, changed)
        if do:
            if held is not None and out:
                out[-1][1] = (1 + out[-1][1]) * (1 - COST * float(np.abs(tgt - held).sum())) - 1
            held = tgt.copy()
        prev = key
    s = pd.Series({pd.Timestamp(d): g for d, g in out})
    s.attrs["stepped"] = steps_days / max(a_days, 1)
    return s


if __name__ == "__main__":
    px = load(); P = prepare(px)
    tq_real = {d.strftime("%Y-%m-%d"): float(v) for d, v in px["TQQQ"].dropna().items()}
    Qp = proxy_returns(P, px)
    tq_proxy = (1 + Qp["r"]["TQQQ"]).cumprod().to_dict()
    pd.set_option("display.width", 260)
    res = {}
    for label, Q, tq, kw in (("REAL 2015-26 (VIXM on)", P, tq_real, dict()),
                             ("PROXY 2001-26", Qp, tq_proxy, dict(start="2001-01-02", vixm=False))):
        front, rows, ser = [], {}, {}
        for c in (0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2):
            s = run_tp(Q, tq, (c, round(1 - c, 2)), **kw); st_ = stats(s)
            front.append((float(st_["MaxDD"]), float(st_["CAGR"])))
            rows[f"plain {c*100:.0f}/{(1-c)*100:.0f}"] = {k: float(v) for k, v in st_.items()}; ser[f"plain{c}"] = s
        for kind in ("spell", "roll20"):
            for to in ("SPMO", "cash"):
                for base in ((0.3, 0.7), (0.4, 0.6)):
                    s = run_tp(Q, tq, base, kind=kind, to=to, **kw)
                    r = {kk: float(v) for kk, v in stats(s).items()}
                    r["vs frontier"] = r["CAGR"] - frontier_cagr_at(r["MaxDD"], front)
                    r["A days stepped"] = s.attrs["stepped"]
                    nm = f"{kind} 10/15/20% ->{to} from {base[0]*100:.0f}/{base[1]*100:.0f}"
                    rows[nm] = r; ser[nm] = s
        t = pd.DataFrame(rows).T
        res[label] = (t, ser)
        print(f"\n{label}")
        print(t[["CAGR", "Sharpe", "MaxDD", "Y2022", "h1", "h2", "A days stepped", "vs frontier"]].round(3).to_string())
    (tr, sr), (tp, sp) = res.values()
    both = [i for i in tr.index if not i.startswith("plain") and tr.loc[i, "vs frontier"] > 0 and tp.loc[i, "vs frontier"] > 0]
    print("\nAhead of the plain-ratio frontier on BOTH real and proxy:", both or "none")
    for nm in both:
        for lab, (t, ser) in res.items():
            ci, p = block_boot(ser[nm], ser["plain0.4"])
            print(f"  {lab} {nm}: {t.loc[nm,'vs frontier']*100:+.2f}pp; Sharpe vs plain 40/60 CI {ci.round(3)} P<=0 {p:.2f}")
