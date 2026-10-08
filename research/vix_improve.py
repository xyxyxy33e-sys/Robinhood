"""Attempts to improve the VIX/VIX3M switch, judged out of sample.

Base rule (matches the author's 60.8/36.6/2.6 time split):
    VIX/VIX3M < 0.90 -> SVXY, > 1.05 -> VXX, else cash.

Each add-on has a reason to work, not just a good backtest:
  ts9    VIX9D/VIX < x       : short-dated stress shows up before the 3-month ratio flips
  vrp    VIX - RV10 > x      : only sell vol when implied is above realized (the premium exists)
  fut    M1/M2 futures < x   : the roll yield SVXY actually earns
  vt     vol-target sizing   : shrink the short when its own recent vol is high
  long   VXX leg on/off/confirmed

Returns: synthetic front-month futures (CBOE settles) before 2018-03, real SVXY/VXX prices
after; T-bills on idle cash; 5 bp per unit traded. Signals at close t, traded at close t+1+lag.
Parameters are picked on TRAIN and reported on TEST untouched.

    python -m research.vix_improve
"""
import itertools
import math
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

from research.vix_curve import constant_maturity, load_futures
from research.vix_ratio import load as load_ratio

warnings.simplefilter("ignore")
TRAIN = ("2013-05-21", "2019-12-31")
TEST = ("2020-01-01", "2026-10-07")
REAL_FROM = "2018-03-01"


def load():
    df = load_ratio()
    lvl, _ = constant_maturity(load_futures())
    df = df.join(lvl[["M1", "M2"]].rename(columns={"M1": "F1", "M2": "F2"}), how="left")
    extra = yf.download(["^VIX9D"], start="2013-01-01", progress=False, auto_adjust=True)["Close"]
    df = df.join(extra.rename(columns={"^VIX9D": "VIX9D"}) if isinstance(extra, pd.DataFrame) else extra.rename("VIX9D"), how="left")
    spy = df.SPY.pct_change()
    df["rv10"] = spy.rolling(10).std() * math.sqrt(252) * 100
    # leg returns: synthetic before REAL_FROM, real ETP after
    syn_short = -0.5 * df.m1 + df.rf - 0.0095 / 252
    syn_long = df.m1 + df.rf - 0.0089 / 252
    real = df.index >= REAL_FROM
    df["short_r"] = np.where(real, df.SVXY.pct_change(), syn_short)
    df["long_r"] = np.where(real, df.VXX.pct_change(), syn_long)
    df["gold_r"] = df.IAU.pct_change()
    return df.dropna(subset=["short_r", "long_r", "VIX9D", "F1", "F2", "rv10"])


def run(df, ts9=None, vrp=None, fut=None, vt=None, long_mode="base", side="cash", lag=1, r_short=0.90, r_long=1.05):
    ratio = df.ratio
    short = ratio < r_short
    if ts9 is not None:
        short &= df.VIX9D / df["^VIX"] < ts9
    if vrp is not None:
        short &= df["^VIX"] - df.rv10 > vrp
    if fut is not None:
        short &= df.F1 / df.F2 < fut
    up = ratio > r_long
    long_ = {"base": up, "confirm2": up & up.shift(1, fill_value=False), "off": up & False}[long_mode]
    short &= ~long_
    w_short = short.astype(float)
    if vt is not None:   # target annual vol for the SVXY sleeve, capped at 1x SVXY
        rv = df.short_r.rolling(20).std() * math.sqrt(252)
        w_short = w_short * (vt / rv).clip(upper=1.0).fillna(0)
    w = pd.DataFrame({"s": w_short, "l": long_.astype(float)}).shift(1 + lag).fillna(0)
    idle = 1 - w.s - w.l
    side_r = df.gold_r.fillna(0) if side == "gold" else df.rf
    r = w.s * df.short_r + w.l * df.long_r + idle * side_r
    return r - w.diff().abs().sum(axis=1).fillna(0) * 0.0005, w


def stats(r, spy=None):
    r = r.dropna()
    eq = (1 + r).cumprod()
    yr = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    mdd = (eq / eq.cummax() - 1).min()
    cagr = eq.iloc[-1] ** (252 / len(r)) - 1
    out = {"CAGR": cagr, "MaxDD": mdd, "Sharpe": r.mean() / r.std() * math.sqrt(252), "Calmar": cagr / -mdd if mdd else np.nan,
           "Worst day": r.min(), "Losing yrs": int((yr < 0).sum())}
    if spy is not None:
        out["Corr SPY"] = r.corr(spy.reindex(r.index))
    return out


def fmt(t):
    t = t.copy()
    for c in t.columns:
        if c in ("CAGR", "MaxDD", "Worst day") or c.endswith(("CAGR", "MaxDD")):
            t[c] = t[c].map(lambda x: f"{x:+.1%}")
        elif c in ("Sharpe", "Calmar") or c.endswith(("Sharpe", "Calmar")):
            t[c] = t[c].map(lambda x: f"{x:.2f}")
        elif c == "Corr SPY":
            t[c] = t[c].map(lambda x: f"{x:+.2f}")
    return t


def main():
    df = load()
    spy = df.SPY.pct_change().fillna(0)
    tr, te = slice(*TRAIN), slice(*TEST)
    print(f"Train {TRAIN[0]}..{TRAIN[1]}   Test {TEST[0]}..{TEST[1]}   (real SVXY/VXX prices from {REAL_FROM})\n")

    grid = itertools.product([None, 1.0, 0.95], [None, 0, 3, 5], [None, 0.95, 0.92], [None, 0.15, 0.25],
                             ["base", "confirm2", "off"], ["cash", "gold"])
    rows = []
    for ts9, vrp, fut, vt, lm, side in grid:
        r, w = run(df, ts9, vrp, fut, vt, lm, side)
        a, b = stats(r[tr]), stats(r[te])
        rows.append({"ts9": ts9, "vrp": vrp, "fut": fut, "vt": vt, "long": lm, "side": side,
                     **{f"tr {k}": v for k, v in a.items() if k in ("CAGR", "MaxDD", "Sharpe", "Calmar")},
                     **{f"te {k}": v for k, v in b.items() if k in ("CAGR", "MaxDD", "Sharpe", "Calmar")},
                     "te Losing yrs": b["Losing yrs"], "short%": (w.s > 0).mean(), "_r": r})
    g = pd.DataFrame(rows)
    show = ["ts9", "vrp", "fut", "vt", "long", "side", "short%", "tr CAGR", "tr MaxDD", "tr Sharpe", "te CAGR", "te MaxDD", "te Sharpe", "te Calmar", "te Losing yrs"]
    g["short%"] = g["short%"].map(lambda x: f"{x:.0%}")

    base = g[(g.ts9.isna()) & (g.vrp.isna()) & (g.fut.isna()) & (g.vt.isna()) & (g.long == "base") & (g.side == "cash")]
    print("Base rule:")
    print(fmt(base[show]).to_string(index=False))

    print(f"\nTop 10 of {len(g)} variants ranked on TRAIN Sharpe -> their TEST results:")
    print(fmt(g.nlargest(10, "tr Sharpe")[show]).to_string(index=False))
    print(f"\nRank correlation train Sharpe vs test Sharpe: {g['tr Sharpe'].rank().corr(g['te Sharpe'].rank()):+.2f}")

    # one add-on at a time, everything else at base: which ideas help on their own?
    print("\nEach add-on alone (rest = base). Median TEST change vs base across its settings:")
    b_te = base.iloc[0]
    for col, base_val in [("ts9", None), ("vrp", None), ("fut", None), ("vt", None)]:
        others = [c for c in ["ts9", "vrp", "fut", "vt"] if c != col]
        sub = g[g[others].isna().all(axis=1) & (g.long == "base") & (g.side == "cash") & g[col].notna()]
        print(f"   {col:4s}: test Sharpe {sub['te Sharpe'].median() - b_te['te Sharpe']:+.2f}, "
              f"test CAGR {sub['te CAGR'].median() - b_te['te CAGR']:+.1%}, test MaxDD {sub['te MaxDD'].median() - b_te['te MaxDD']:+.1%}")
    for col, vals in [("long", ["confirm2", "off"]), ("side", ["gold"])]:
        for v in vals:
            sub = g[g[["ts9", "vrp", "fut", "vt"]].isna().all(axis=1) & (g[col] == v) & ((g.side == "cash") if col == "long" else (g.long == "base"))]
            print(f"   {col}={v}: test Sharpe {sub['te Sharpe'].iloc[0] - b_te['te Sharpe']:+.2f}, test CAGR {sub['te CAGR'].iloc[0] - b_te['te CAGR']:+.1%}, "
                  f"test MaxDD {sub['te MaxDD'].iloc[0] - b_te['te MaxDD']:+.1%}")

    pick = g.nlargest(1, "tr Sharpe").iloc[0]
    print(f"\nChosen on train: ts9={pick.ts9} vrp={pick.vrp} fut={pick.fut} vt={pick.vt} long={pick.long} side={pick.side}")
    r = pick["_r"]
    rb = base.iloc[0]["_r"]
    yr = pd.DataFrame({"improved": r, "base": rb, "SPY": spy}).resample("YE").apply(lambda x: (1 + x).prod() - 1)
    yr.index = yr.index.year
    print(yr.map("{:+.1%}".format).to_string())
    full = pd.DataFrame({"improved": stats(r, spy), "base": stats(rb, spy), "SPY": stats(spy, spy)}).T
    print("\nFull period:")
    print(fmt(full).to_string())
    for start in ["2025-12-31", "2026-03-23"]:
        print(f"   2026 from {start}: improved {(1 + r.loc[start:'2026-10-02'].iloc[1:]).prod() - 1:+.1%}, "
              f"base {(1 + rb.loc[start:'2026-10-02'].iloc[1:]).prod() - 1:+.1%}")
    r0, _ = run(df, pick.ts9, pick.vrp, pick.fut, pick.vt, pick.long, pick.side, lag=0)
    print(f"   same rule traded at the signal close (needs ~3:55pm values): test {fmt(pd.DataFrame([stats(r0[te])]))[['CAGR', 'MaxDD', 'Sharpe']].to_string(index=False, header=False)}")


if __name__ == "__main__":
    main()
