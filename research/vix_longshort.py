"""Backtest of the article's actual "VIX long/short" (VIX多空) strategy, as described.

Rules from the article (@Amy6Tina, Oct 2026), made mechanical:
  - Trend following, not mean reversion.
  - VIX low / contango          -> short vol with SVXY (-0.5x since Feb 2018).  ~60% of days.
  - VIX trending up + backwardation confirmed -> long vol (VXX/VIXY).          <3% of days.
  - Otherwise                   -> gold or cash.                               ~37% of days.
  - Exit as soon as the signal flips ("don't hold losers").

Parameters aren't published, so we grid over them and keep the variants whose time in
each leg matches the article (short 50-70%, long 1-5%). Results are an in-sample best case.

Signals use day-t closes and trade at t+1+lag closes (VIX settles 16:15, after ETFs).

    python -m research.vix_longshort
"""
import argparse
import itertools
import math

import numpy as np
import pandas as pd
import yfinance as yf

COST = 0.0005
CLAIM_START = "2018-03-01"   # SVXY at -0.5x; "8 years of live trading"


def load(start="2011-10-04") -> pd.DataFrame:
    syms = {"^VIX": "vix", "^VIX3M": "vix3m", "VIXY": "vixy", "SVXY": "svxy", "SPY": "spy", "GLD": "gld", "BIL": "bil"}
    df = yf.download(list(syms), start=start, progress=False, auto_adjust=True)["Close"]
    return df.rename(columns=syms).dropna()


def signals(px, n=10, r_short=0.9, r_long=1.0, jump=0.10, short_below_ma=True):
    ratio = px.vix / px.vix3m
    sma = px.vix.rolling(n).mean()
    long_ = (ratio > r_long) & (px.vix > sma * (1 + jump))
    short = (ratio < r_short) & ~long_
    if short_below_ma:
        short &= px.vix < sma * (1 + jump / 2)
    return short, long_


def run(px, short, long_, alt="gld", lag=1):
    w = pd.DataFrame(0.0, index=px.index, columns=["svxy", "vixy", "gld", "bil"])
    w["svxy"] = short.astype(float)
    w["vixy"] = long_.astype(float)
    w[alt] = (~short & ~long_).astype(float)
    rets = px[w.columns].pct_change().fillna(0)
    held = w.shift(1 + lag).fillna(0)
    turnover = held.diff().abs().sum(axis=1).fillna(0)
    return (held * rets).sum(axis=1) - COST * turnover, held


def stats(r, spy):
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    yr = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {
        "CAGR": eq.iloc[-1] ** (1 / yrs) - 1,
        "Total": eq.iloc[-1] - 1,
        "MaxDD": (eq / eq.cummax() - 1).min(),
        "Sharpe": r.mean() / r.std() * math.sqrt(252),
        "Corr_d": r.corr(spy),
        "WorstYr": yr.min(),
        "NegYrs": int((yr < 0).sum()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lag", type=int, default=1)
    ap.add_argument("--start", default=CLAIM_START)
    a = ap.parse_args()

    full = load()
    rows = []
    for n, rs, rl, j, bm, alt in itertools.product(
        [5, 10, 20], [0.85, 0.90, 0.95, 1.0], [0.95, 1.0, 1.05, 1.10], [0.0, 0.05, 0.10, 0.20, 0.30], [True, False], ["gld", "bil"]
    ):
        s, l = signals(full, n, rs, rl, j, bm)
        r, held = run(full, s, l, alt, a.lag)
        r, held = r[a.start:], held[a.start:]
        spy = full.spy.pct_change()[a.start:]
        rows.append({"n": n, "r_short": rs, "r_long": rl, "jump": j, "below_ma": bm, "alt": alt,
                     "short%": held.svxy.mean(), "long%": held.vixy.mean(), **stats(r, spy), "_r": r})
    g = pd.DataFrame(rows)
    match = g[g["short%"].between(0.5, 0.7) & g["long%"].between(0.01, 0.05)]

    pct = {c: "{:.1%}".format for c in ["CAGR", "MaxDD", "WorstYr", "short%", "long%"]}
    pct.update({"Total": "{:.0%}".format, "Sharpe": "{:.2f}".format, "Corr_d": "{:+.2f}".format})
    cols = ["n", "r_short", "r_long", "jump", "below_ma", "alt", "short%", "long%", "CAGR", "Total", "MaxDD", "Sharpe", "Corr_d", "WorstYr", "NegYrs"]

    spy = full.spy.pct_change()[a.start:].fillna(0)
    print(f"Period {spy.index[0].date()} -> {spy.index[-1].date()} ({len(spy)} days), lag={a.lag}")
    print(f"{len(g)} variants, {len(match)} match the article's time split (short 50-70%, long 1-5%)\n")
    print("Benchmarks:")
    for name, r in {"SPY": spy, "SVXY hold": full.svxy.pct_change()[a.start:].fillna(0), "GLD hold": full.gld.pct_change()[a.start:].fillna(0)}.items():
        st = stats(r, spy)
        print(f"  {name:10s} CAGR {st['CAGR']:6.1%}  MaxDD {st['MaxDD']:6.1%}  Corr {st['Corr_d']:+.2f}  neg yrs {st['NegYrs']}")

    print("\nMatching variants, top 10 by CAGR:")
    print(match.sort_values("CAGR", ascending=False)[cols].head(10).to_string(index=False, formatters=pct))
    print("\nMatching variants, top 5 by fewest negative years then MaxDD:")
    print(match.sort_values(["NegYrs", "MaxDD"], ascending=[True, False])[cols].head(5).to_string(index=False, formatters=pct))
    print("\nAcross matching variants: median CAGR {:.1%}, median MaxDD {:.1%}, median corr {:+.2f}".format(
        match.CAGR.median(), match.MaxDD.median(), match.Corr_d.median()))
    print("Any matching variant with CAGR>=45% : ", (match.CAGR >= 0.45).any())
    print("Any matching variant with 0 negative years:", (match.NegYrs == 0).any())
    print("Any matching variant with MaxDD > -15%:", (match.MaxDD > -0.15).any())

    best = match.sort_values("CAGR", ascending=False).iloc[0]
    r = best["_r"]
    print("\nBest-CAGR matching variant, calendar years:")
    yr = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    spy_yr = spy.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    print(pd.DataFrame({"strategy": yr, "SPY": spy_yr}, index=yr.index).set_axis(yr.index.year).map("{:+.1%}".format).to_string())
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    print(f"\nWorst drawdown {dd.min():.1%}, trough {dd.idxmin().date()}")
    for d0, d1, label in [("2018-02-01", "2018-02-28", "Feb 2018 (Volmageddon; SVXY was -1x until Feb 27)"),
                          ("2020-02-15", "2020-03-31", "Feb-Mar 2020 Covid"),
                          ("2024-07-25", "2024-08-15", "Aug 2024 yen unwind"),
                          ("2025-03-25", "2025-04-30", "Apr 2025 tariffs")]:
        seg = r[d0:d1]
        if len(seg):
            print(f"  {label:50s} {(1 + seg).prod() - 1:+.1%}")


if __name__ == "__main__":
    main()
