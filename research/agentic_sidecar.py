"""What should the "cash" sleeve of the agentic account's weak states hold?

Live strategy (branch claude/robinhood-momentum-calls-0wl9b9, research/SPMO_TQQQ_OVERLAY_SPEC.md):
SPMO core + TQQQ satellite, sized by a six-state regime on QQQ's 50/200-day averages with a
1% hysteresis band, plus the owner's 2026-08-31 proposal to hold cash (BOXX) in D/E/F:

    state   core  sat  sleeve      A established uptrend     D pullback in uptrend
    A        65   35    0          B reclaim                 E breakdown (fast crash)
    B        25   75    0          C dead-cat bounce         F established downtrend
    C       100    0    0
    D        55   20   25
    E        50    0   50
    F        30    0   70

This test keeps everything above fixed and only changes what the sleeve holds:
T-bills (BOXX), gold (IAU), utilities (XLU), mid-curve long vol (VIXM), the improved
VIX term-structure switch from research/vix_improve.py, and simple blends.

Total-return prices (yfinance adjusted). State from QQQ close t, rebalanced at close t+1,
10 bp round trip on traded weight; sleeves drift between state changes like the live book.

    python -m research.agentic_sidecar
"""
import math
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

from research.vix_improve import load as load_vol, run as run_vol

warnings.simplefilter("ignore")
BUF = 0.01
OWNER = {"A": (.65, .35, 0), "B": (.25, .75, 0), "C": (1, 0, 0), "D": (.55, .20, .25), "E": (.50, 0, .50), "F": (.30, 0, .70)}
LIVE_A50 = {**OWNER, "A": (.50, .50, 0)}          # what the account actually holds in A today (~52% TQQQ)
NO_CASH = {"A": (.65, .35, 0), "B": (.65, .35, 0), "C": (1, 0, 0), "D": (.80, .20, 0), "E": (1, 0, 0), "F": (1, 0, 0)}


def states(q: pd.Series) -> pd.Series:
    ma50, ma200 = q.rolling(50).mean(), q.rolling(200).mean()
    a50 = a200 = None
    out = []
    for c, m5, m2 in zip(q, ma50, ma200):
        if np.isnan(m2):
            out.append(None); continue
        if c > m5 * (1 + BUF): a50 = True
        elif c < m5 * (1 - BUF): a50 = False
        if c > m2 * (1 + BUF): a200 = True
        elif c < m2 * (1 - BUF): a200 = False
        if a50 is None: a50 = c > m5
        if a200 is None: a200 = c > m2
        cross = m5 > m2
        out.append("A" if a50 and a200 and cross else "B" if a50 and a200 else "C" if a50 else
                   "D" if a200 else "E" if cross else "F")
    return pd.Series(out, index=q.index)


def load():
    px = yf.download(["QQQ", "SPMO", "TQQQ", "IAU", "XLU", "VIXM", "IEF", "SPY"], start="2014-01-01",
                     progress=False, auto_adjust=True)["Close"]
    vol = load_vol()
    vr, vw = run_vol(vol, long_mode="confirm2", side="cash")   # improved switch, cash on its sidelines
    rets = px.pct_change()
    rets["VOLSW"] = vr
    rets["SVXY_ONLY"] = run_vol(vol, long_mode="off", side="cash")[0]
    rets["BILL"] = vol.rf
    rets = rets.loc["2015-10-15":].dropna(subset=["SPMO", "TQQQ"])
    rets["BILL"] = rets.BILL.fillna(rets.BILL.ffill()).fillna(0)
    for c in ["VOLSW", "SVXY_ONLY"]:
        rets[c] = rets[c].fillna(rets.BILL)
    st = states(px.QQQ).reindex(rets.index)
    return rets, st, vol


def simulate(rets, st, wmap, sleeve, cost=0.0010):
    """sleeve: dict asset -> weight inside the cash sleeve."""
    target = st.shift(1).map(lambda s: wmap.get(s, (1, 0, 0)))   # state at close t-1 -> trade at close t (earns t+1)
    target = target.shift(1)                                       # one extra session: computed after close, traded next close
    hold = None; cur = None; eq = 1.0; out = []
    for d, row in rets.iterrows():
        t = target.loc[d]
        if t is None or (isinstance(t, float) and np.isnan(t)):
            t = (1, 0, 0)
        if t != cur:
            new = pd.Series({"SPMO": t[0], "TQQQ": t[1], **{k: t[2] * v for k, v in sleeve.items()}})
            if hold is not None:
                old = (hold / hold.sum()).reindex(new.index.union(hold.index), fill_value=0)
                eq *= 1 - (new.reindex(old.index, fill_value=0) - old).abs().sum() * cost / 2
            hold = new * eq; cur = t
        hold = hold * (1 + row[hold.index].fillna(0))
        eq = hold.sum(); out.append(eq)
    e = pd.Series(out, index=rets.index)
    return e.pct_change().fillna(e.iloc[0] - 1)


def stats(r, rf):
    eq = (1 + r).cumprod()
    roll12 = eq / eq.shift(252) - 1
    yr = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    ex = r - rf
    return {"CAGR": eq.iloc[-1] ** (252 / len(r)) - 1, "MaxDD": (eq / eq.cummax() - 1).min(),
            "Sharpe": ex.mean() / r.std() * math.sqrt(252), "Worst 12m": roll12.min(),
            **{str(y): yr.get(pd.Timestamp(f"{y}-12-31"), np.nan) for y in (2018, 2020, 2022, 2025)}}


def main():
    rets, st, vol = load()
    rf = rets.BILL
    print(f"{rets.index[0].date()} -> {rets.index[-1].date()}  ({len(rets) / 252:.1f} yrs)")
    print("time in each state: " + "  ".join(f"{k} {v:.0%}" for k, v in st.value_counts(normalize=True).sort_index().items()))
    print(f"current state ({st.index[-1].date()}): {st.iloc[-1]}\n")

    # what each sleeve candidate did while the book was actually in D/E/F
    weak = st.shift(2).isin(["D", "E", "F"])
    print("Sleeve candidates during D/E/F days only (annualised) and correlation with SPMO there:")
    for c in ["BILL", "IAU", "XLU", "IEF", "VIXM", "VOLSW", "SVXY_ONLY"]:
        x = rets.loc[weak, c].fillna(0)
        print(f"   {c:9s} {((1 + x).prod()) ** (252 / weak.sum()) - 1:+7.1%}/yr   corr SPMO {x.corr(rets.loc[weak, 'SPMO']):+.2f}")

    sleeves = {
        "T-bills / BOXX (owner proposal)": {"BILL": 1},
        "Gold (IAU)": {"IAU": 1},
        "Utilities (XLU)": {"XLU": 1},
        "7-10y Treasuries (IEF)": {"IEF": 1},
        "Mid-curve long vol (VIXM)": {"VIXM": 1},
        "Improved VIX switch": {"VOLSW": 1},
        "50 BOXX / 50 gold": {"BILL": .5, "IAU": .5},
        "70 BOXX / 30 VIX switch": {"BILL": .7, "VOLSW": .3},
        "80 BOXX / 20 VIXM": {"BILL": .8, "VIXM": .2},
        "40 BOXX / 40 gold / 20 VIXM": {"BILL": .4, "IAU": .4, "VIXM": .2},
    }
    rows = {"No cash (original spec)": stats(simulate(rets, st, NO_CASH, {"BILL": 1}), rf)}
    for name, sl in sleeves.items():
        rows[name] = stats(simulate(rets, st, OWNER, sl), rf)
    rows["SPY buy & hold"] = stats(rets.SPY, rf)
    t = pd.DataFrame(rows).T

    def fmt(t):
        t = t.copy()
        for c in t.columns:
            t[c] = t[c].map(lambda x: f"{x:.2f}" if "Sharpe" in c else f"{x:+.1%}")
        return t

    print("\nOwner's state weights, sleeve contents varied:")
    print(fmt(t).to_string())

    print("\nRobustness: same comparison on each half")
    halves = [("2015-10-15", "2020-12-31"), ("2021-01-01", "2026-10-07")]
    h = {}
    for name, sl in [("T-bills / BOXX", {"BILL": 1}), ("Gold", {"IAU": 1}), ("XLU", {"XLU": 1}), ("IEF", {"IEF": 1}),
                     ("VIXM", {"VIXM": 1}), ("VIX switch", {"VOLSW": 1}), ("50 BOXX/50 gold", {"BILL": .5, "IAU": .5}),
                     ("80 BOXX/20 VIXM", {"BILL": .8, "VIXM": .2}), ("70 BOXX/30 VIX switch", {"BILL": .7, "VOLSW": .3})]:
        r = simulate(rets, st, OWNER, sl)
        h[name] = {f"{a[:4]}-{b[:4]} {k}": v for a, b in halves for k, v in stats(r.loc[a:b], rf.loc[a:b]).items() if k in ("CAGR", "MaxDD", "Sharpe")}
    print(fmt(pd.DataFrame(h).T).to_string())

    print("\nWith the live account's state-A split (50/50 instead of 65/35):")
    rr = {n: stats(simulate(rets, st, LIVE_A50, sl), rf) for n, sl in
          [("T-bills / BOXX", {"BILL": 1}), ("Gold", {"IAU": 1}), ("50 BOXX/50 gold", {"BILL": .5, "IAU": .5}), ("80 BOXX/20 VIXM", {"BILL": .8, "VIXM": .2})]}
    print(fmt(pd.DataFrame(rr).T).to_string())


if __name__ == "__main__":
    main()
