"""Term-structure switch: VIX / VIX3M ratio decides short vol, long vol or the sidelines.

    ratio < r_short  -> SVXY (-0.5x front-month VIX futures), or SVIX (-1x)
    ratio > r_long   -> VXX  (+1x front-month)
    otherwise        -> IAU (gold) or T-bills

Same front-month futures series, fees and T-bill collateral as research/vix_threshold.py.
Thresholds are swept; rows whose time split matches the author's screenshot
(60.8% short / 36.6% sidelines / 2.6% long) are flagged.

    python -m research.vix_ratio
"""
import itertools
import math
import warnings

import pandas as pd
import yfinance as yf

from research.vix_threshold import load as load_base

warnings.simplefilter("ignore")
FEE = {0.5: 0.0095, 1.0: 0.0135, "long": 0.0089}   # SVXY, SVIX, VXX
TARGET = (0.608, 0.366, 0.026)


def load():
    df = load_base()
    extra = yf.download(["^VIX3M", "IAU"], start="2013-01-01", progress=False, auto_adjust=True)["Close"]
    df = df.join(extra, how="left")
    df["ratio"] = df["^VIX"] / df["^VIX3M"]
    return df.dropna(subset=["ratio"])


def run(df, r_short=1.0, r_long=1.0, short_lev=0.5, alt="cash", lag=1, confirm=1):
    ratio = df.ratio
    long_sig = (ratio > r_long).rolling(confirm).sum().eq(confirm)
    state = pd.Series(0, index=df.index)
    state[ratio < r_short] = -1
    state[long_sig] = 1
    pos = state.shift(1 + lag).fillna(0)
    short_r = -short_lev * df.m1 + df.rf - FEE[short_lev] / 252
    long_r = df.m1 + df.rf - FEE["long"] / 252
    side_r = df.IAU.pct_change().fillna(0) if alt == "gold" else df.rf
    r = side_r.where(pos == 0, 0) + short_r.where(pos == -1, 0) + long_r.where(pos == 1, 0)
    return r - pos.diff().abs().fillna(0) * 0.0005, pos


def stats(r, spy, pos=None):
    eq = (1 + r).cumprod()
    yr = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    out = {"CAGR": eq.iloc[-1] ** (252 / len(r)) - 1, "MaxDD": (eq / eq.cummax() - 1).min(),
           "Sharpe": r.mean() / r.std() * math.sqrt(252), "Corr SPY": r.corr(spy), "Worst day": r.min(),
           "Losing yrs": int((yr < 0).sum())}
    if pos is not None:
        out.update({"short%": (pos == -1).mean(), "side%": (pos == 0).mean(), "long%": (pos == 1).mean()})
    return out


def fmt(t):
    t = t.copy()
    for c in t.columns:
        if c in ("CAGR", "MaxDD", "Worst day", "short%", "side%", "long%"):
            t[c] = t[c].map(lambda x: f"{x:+.1%}" if c in ("CAGR", "MaxDD", "Worst day") else f"{x:.1%}")
        elif c in ("Sharpe",):
            t[c] = t[c].map(lambda x: f"{x:.2f}")
        elif c == "Corr SPY":
            t[c] = t[c].map(lambda x: f"{x:+.2f}")
    return t


def main():
    df = load()
    spy = df.SPY.pct_change().fillna(0)
    print(f"{df.index[0].date()} -> {df.index[-1].date()} ({len(df)} days)\n")

    print("1) Plain switch: SVXY when VIX<VIX3M, VXX when VIX>VIX3M (no sidelines)")
    rows = {}
    for lev, lag in itertools.product([0.5, 1.0], [1, 0]):
        r, pos = run(df, 1.0, 1.0, lev, "cash", lag)
        rows[f"{'SVXY' if lev == .5 else 'SVIX'} / VXX, {'next close' if lag else 'same close (optimistic)'}"] = stats(r, spy, pos)
    print(fmt(pd.DataFrame(rows).T).to_string())

    print("\n2) Threshold sweep (SVXY, next-close trading)")
    res = []
    for rs, rl, alt, conf in itertools.product([0.80, 0.85, 0.88, 0.90, 0.92, 0.95, 1.0], [1.0, 1.05, 1.10, 1.15, 1.20],
                                               ["cash", "gold"], [1, 2, 3]):
        r, pos = run(df, rs, rl, 0.5, alt, 1, conf)
        res.append({"r_short": rs, "r_long": rl, "side": alt, "confirm": conf, **stats(r, spy, pos), "_r": r, "_pos": pos})
    g = pd.DataFrame(res)
    g["split err"] = (g["short%"] - TARGET[0]).abs() + (g["long%"] - TARGET[2]).abs()
    cols = ["r_short", "r_long", "side", "confirm", "short%", "side%", "long%", "CAGR", "MaxDD", "Sharpe", "Corr SPY", "Worst day", "Losing yrs"]
    print("   closest to the author's 60.8 / 36.6 / 2.6 split:")
    print(fmt(g.nsmallest(8, "split err")[cols]).to_string(index=False))
    print("\n   best CAGR overall (hindsight):")
    print(fmt(g.nlargest(5, "CAGR")[cols]).to_string(index=False))
    print(f"\n   all {len(g)} variants: median CAGR {g.CAGR.median():+.1%}, median MaxDD {g.MaxDD.median():+.1%}, "
          f"best MaxDD {g.MaxDD.max():+.1%}, any with 0 losing years: {(g['Losing yrs'] == 0).any()}")

    best = g.nsmallest(1, "split err").iloc[0]
    r, pos = best["_r"], best["_pos"]
    print(f"\n3) Closest-split variant (r_short={best.r_short}, r_long={best.r_long}, {best.side}, confirm={best.confirm}) by year:")
    yr = pd.DataFrame({"rule": r, "SPY": spy}).resample("YE").apply(lambda x: (1 + x).prod() - 1)
    yr["short/side/long days"] = [f"{(p == -1).sum()}/{(p == 0).sum()}/{(p == 1).sum()}" for _, p in pos.groupby(pos.index.year)]
    yr.index = yr.index.year
    print(yr.to_string(formatters={"rule": "{:+.1%}".format, "SPY": "{:+.1%}".format}))
    worst = r.nsmallest(5)
    print("\n   worst days:")
    print(pd.DataFrame({"rule": worst.map("{:+.1%}".format), "pos": pos[worst.index].map({-1: "SVXY", 0: best.side, 1: "VXX"}),
                        "ratio prev": df.ratio.shift(1)[worst.index].round(2), "ratio": df.ratio[worst.index].round(2),
                        "VIX": df["^VIX"][worst.index].round(1)}).to_string())
    for start in ["2025-12-31", "2026-03-23"]:
        seg = r.loc[start:"2026-10-02"].iloc[1:]
        print(f"   2026 check from {start}: {(1 + seg).prod() - 1:+.1%}  (author claims +28.95%)")
    eq = (1 + r.loc["2018-03-01":]).cumprod()
    print(f"   since Mar 2018 (SVXY at -0.5x the whole time): CAGR {eq.iloc[-1] ** (252 / len(eq)) - 1:+.1%}, "
          f"MaxDD {(eq / eq.cummax() - 1).min():+.1%}   (author's backtest: 36% CAGR, -35.6% MaxDD)")


if __name__ == "__main__":
    main()
