"""Simple VIX-level rule: short vol below one level, long vol above another, cash between.

    VIX < 15  -> SVIX  (-1x front-month VIX futures)      [or SVXY, -0.5x]
    VIX > 30  -> VXX   (+1x front-month VIX futures)
    otherwise -> cash (T-bills)

Front-month exposure comes from the 30-day constant-maturity VIX futures position
built in research/vix_curve.py (CBOE settles, 2013+), minus ETP fees. That series
tracks SVIX/VXX with 0.99/0.93 daily correlation; real ETP prices are used as a check.

    python -m research.vix_threshold
"""
import math
import warnings

import pandas as pd
import yfinance as yf

from research.vix_curve import constant_maturity, load_futures

warnings.simplefilter("ignore")
FEE = {"short": 0.0135, "long": 0.0089}  # SVIX, VXX expense ratios


def load():
    _, cm = constant_maturity(load_futures())
    m1 = cm["M1"]
    mkt = yf.download(["^VIX", "^IRX", "SPY", "SVIX", "VXX", "SVXY"], start="2013-01-01", progress=False, auto_adjust=True)["Close"]
    df = pd.DataFrame({"m1": m1}).join(mkt, how="inner")
    df["rf"] = (df["^IRX"].ffill() / 100 / 252).fillna(0)
    return df.loc[df.m1.ne(0).idxmax():]


def run(df, lo=15, hi=30, short_lev=1.0, lag=1, cash=True):
    vix = df["^VIX"]
    state = pd.Series(0, index=df.index)            # 0 cash, -1 short, +1 long
    state[vix < lo] = -1
    state[vix > hi] = 1
    pos = state.shift(1 + lag).fillna(0)
    short_r = -short_lev * df.m1 + df.rf - FEE["short"] / 252   # inverse ETP: collateral earns T-bills
    long_r = df.m1 + df.rf - FEE["long"] / 252
    cash_r = df.rf if cash else 0 * df.rf
    r = pd.Series(cash_r, index=df.index).where(pos == 0, 0) + short_r.where(pos == -1, 0) + long_r.where(pos == 1, 0)
    trades = pos.diff().abs().gt(0).sum()
    return r - pos.diff().abs().fillna(0) * 0.0005, pos


def stats(r, spy):
    eq = (1 + r).cumprod()
    yr = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {"CAGR": eq.iloc[-1] ** (252 / len(r)) - 1, "MaxDD": (eq / eq.cummax() - 1).min(),
            "Sharpe": (r.mean() / r.std()) * math.sqrt(252), "Corr SPY": r.corr(spy),
            "Worst day": r.min(), "Losing yrs": int((yr < 0).sum()), "Years": len(yr)}


def show(rows, spy):
    t = pd.DataFrame({k: stats(v, spy) for k, v in rows.items()}).T
    for c in ["CAGR", "MaxDD", "Worst day"]:
        t[c] = t[c].map(lambda x: f"{x:+.1%}")
    t["Sharpe"] = t["Sharpe"].map(lambda x: f"{x:.2f}")
    t["Corr SPY"] = t["Corr SPY"].map(lambda x: f"{x:+.2f}")
    print(t.to_string())


def main():
    df = load()
    spy = df.SPY.pct_change().fillna(0)
    print(f"{df.index[0].date()} -> {df.index[-1].date()} ({len(df)} days)\n")

    r, pos = run(df)
    print(f"Time split, VIX<15 / 15-30 / >30: {(pos == -1).mean():.0%} / {(pos == 0).mean():.0%} / {(pos == 1).mean():.1%}"
          f"   (article: 61% / 37% / 2.6%)\n")

    print("Your rule (signal at VIX close, trade next close) vs variants:")
    rows = {"SVIX<15 / cash / VXX>30": r,
            "  same, trade at signal close (optimistic)": run(df, lag=0)[0],
            "SVXY(-0.5x)<15 / cash / VXX>30": run(df, short_lev=0.5)[0],
            "SVIX<15 / cash, never long": run(df, hi=999)[0],
            "SVIX<18 / cash / VXX>30": run(df, lo=18)[0],
            "SVIX<20 / cash / VXX>30": run(df, lo=20)[0],
            "SVIX<15 / cash / VXX>25": run(df, hi=25)[0],
            "SVIX<15 / cash / VXX>40": run(df, hi=40)[0],
            "Cash only": df.rf,
            "SPY": spy}
    show(rows, spy)

    print("\nYour rule by calendar year (SVIX version, next-close trading):")
    yr = pd.DataFrame({"rule": r, "SPY": spy}).resample("YE").apply(lambda x: (1 + x).prod() - 1)
    yr["days short/cash/long"] = [f"{(p == -1).sum()}/{(p == 0).sum()}/{(p == 1).sum()}" for _, p in pos.groupby(pos.index.year)]
    yr.index = yr.index.year
    print(yr.to_string(formatters={"rule": "{:+.1%}".format, "SPY": "{:+.1%}".format}))

    print("\nWhere the losses came from (worst 6 days):")
    worst = r.nsmallest(6)
    print(pd.DataFrame({"rule": worst.map("{:+.1%}".format), "pos": pos[worst.index].map({-1: "SVIX", 0: "cash", 1: "VXX"}),
                        "VIX prev close": df["^VIX"].shift(1)[worst.index].round(1), "VIX close": df["^VIX"][worst.index].round(1)}).to_string())

    print("\nCheck with real ETP prices where they exist (SVIX since 2022-03, VXX since 2018-01):")
    real = df.dropna(subset=["SVIX", "VXX"])
    rr = real[["SVIX", "VXX"]].pct_change().fillna(0)
    p = pos.loc[real.index]
    real_r = rr.SVIX.where(p == -1, 0) + rr.VXX.where(p == 1, 0) + real.rf.where(p == 0, 0)
    show({"real ETPs": real_r, "synthetic": r.loc[real.index], "SPY": spy.loc[real.index]}, spy.loc[real.index])

    print("\nThe article's 2026 claim: +28.95% by Oct 3")
    for start in ["2025-12-31", "2026-03-23"]:
        seg = r.loc[start:"2026-10-02"].iloc[1:]
        print(f"   rule from {start}: {(1 + seg).prod() - 1:+.1%}")


if __name__ == "__main__":
    main()
