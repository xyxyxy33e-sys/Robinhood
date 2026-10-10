"""Backtest of long-volatility strategies that could be the article's "niche strategy".

The article (@Amy6Tina, Oct 7 2026) promises ~60%/yr, <5% max drawdown, negative
correlation to the S&P 500. Its body isn't public, so this tests the plausible
families of "vol trading that isn't selling vol" on daily data since 2011:

  1. Buy & hold VIXY (1-month VIX futures ETF)        - the naive long-vol baseline
  2. Term structure: long VIXY only in backwardation   - VIX / VIX3M > threshold
  3. Spike momentum: long VIXY when VIX jumps above its moving average
  4. VIX long/short: SVXY in contango, VIXY in backwardation (the author's own "core" style)
  5. Rolling SPX puts, priced with Black-Scholes off VIX + a skew bump (tail hedge)

Signals use the close on day t and earn the return from close t+lag to t+lag+1.
Default lag is 1 extra day, because VIX settles at 16:15 ET, after the ETFs close.
Costs: 5 bp per unit of turnover.

    python -m research.vol_backtest            # summary table
    python -m research.vol_backtest --grid     # best in-sample parameters (hindsight, upper bound)
"""
import argparse
import itertools
import math

import numpy as np
import pandas as pd
import yfinance as yf

COST = 0.0005
START = "2011-01-04"


def load() -> pd.DataFrame:
    syms = {"^VIX": "vix", "^VIX3M": "vix3m", "VIXY": "vixy", "SVXY": "svxy", "SPY": "spy", "^SPX": "spx"}
    df = yf.download(list(syms), start=START, progress=False, auto_adjust=True)["Close"]
    return df.rename(columns=syms).dropna()


def run(px: pd.DataFrame, w: pd.DataFrame, lag: int = 1) -> pd.Series:
    """w: target weights per ETF column, decided at close t. Returns daily strategy returns."""
    rets = px[w.columns].pct_change().fillna(0)
    held = w.shift(1 + lag).fillna(0)
    turnover = held.diff().abs().sum(axis=1).fillna(0)
    return (held * rets).sum(axis=1) - COST * turnover


def stats(r: pd.Series, spy: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    vol = r.std() * math.sqrt(252)
    m = pd.concat([r, spy], axis=1).resample("ME").apply(lambda x: (1 + x).prod() - 1)
    return {
        "CAGR": cagr,
        "MaxDD": dd,
        "Vol": vol,
        "Sharpe": r.mean() / r.std() * math.sqrt(252) if r.std() else np.nan,
        "Corr_d": r.corr(spy),
        "Corr_m": m.iloc[:, 0].corr(m.iloc[:, 1]),
        "Exposure": (r != 0).mean(),
    }


# ---- strategies -----------------------------------------------------------

def w_hold(px, sym="vixy"):
    return pd.DataFrame({sym: 1.0}, index=px.index)


def w_term(px, thresh=1.0):
    ratio = px.vix / px.vix3m
    return pd.DataFrame({"vixy": (ratio > thresh).astype(float)}, index=px.index)


def w_spike(px, ma=10, jump=0.15, hold_ratio=1.0):
    """Enter when VIX closes >jump above its MA; stay while VIX/VIX3M > hold_ratio or the spike persists."""
    sma = px.vix.rolling(ma).mean()
    on = (px.vix > sma * (1 + jump)) | ((px.vix / px.vix3m > hold_ratio) & (px.vix > sma))
    return pd.DataFrame({"vixy": on.astype(float)}, index=px.index)


def w_longshort(px, thresh=1.0, short_size=1.0):
    ratio = px.vix / px.vix3m
    back = ratio > thresh
    return pd.DataFrame({"vixy": back.astype(float), "svxy": (~back).astype(float) * short_size}, index=px.index)


def bs_put(S, K, T, sigma, r=0.03):
    from math import erf, exp, log, sqrt
    N = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
    if T <= 0:
        return max(K - S, 0.0)
    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return K * exp(-r * T) * N(-d2) - S * N(-d1)


def r_puts(px, otm=0.05, budget=0.01, days=21, skew_per_otm=3.0, min_prem=0.20):
    """Each `days` sessions spend `budget` of equity on SPX puts `otm` below spot, held to expiry.
    IV = VIX * (1 + skew_per_otm*otm): SPX skew puts a 10%-OTM 1-month put ~1.3x VIX.
    Purchases pay at least `min_prem` index points (ticks + spread on far-OTM strikes), so the
    model can't buy near-free lottery tickets that real markets don't sell.
    Rest of equity sits in cash (0% here, conservative). Returns daily returns of the hedge sleeve alone."""
    spx, vix = px.spx.values, px.vix.values / 100
    eq, cash = [1.0], 1.0
    pos = None  # (K, expiry_idx, contracts)
    for i in range(1, len(spx)):
        if pos is None or i - 1 == pos[1]:
            if pos is not None:
                cash += pos[2] * max(pos[0] - spx[i - 1], 0)
            K = spx[i - 1] * (1 - otm)
            prem = max(bs_put(spx[i - 1], K, days / 252, vix[i - 1] * (1 + skew_per_otm * otm)), min_prem)
            spend = cash * budget
            pos = (K, i - 1 + days, spend / prem)
            cash -= spend
        T = (pos[1] - i) / 252
        mark = pos[2] * bs_put(spx[i], pos[0], T, vix[i] * (1 + skew_per_otm * otm))
        eq.append(cash + mark)
    eq = pd.Series(eq, index=px.index)
    return eq.pct_change().fillna(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--lag", type=int, default=1)
    a = ap.parse_args()

    px = load()
    spy = px.spy.pct_change().fillna(0)
    print(f"Data {px.index[0].date()} -> {px.index[-1].date()}  ({len(px)} days)\n")

    rows = {
        "SPY buy & hold": spy,
        "SVXY buy & hold (short vol)": run(px, w_hold(px, "svxy"), a.lag),
        "1 VIXY buy & hold": run(px, w_hold(px), a.lag),
        "2 VIXY when VIX/VIX3M>1": run(px, w_term(px), a.lag),
        "3 VIXY on VIX spike": run(px, w_spike(px), a.lag),
        "4 Long/short VIX ETFs": run(px, w_longshort(px), a.lag),
        "5 SPX 5%-OTM puts, 1%/mo": r_puts(px),
        "5b SPX 10%-OTM puts, 0.5%/mo": r_puts(px, otm=0.10, budget=0.005),
        "50/50 SPY + strategy 2": 0.5 * spy + 0.5 * run(px, w_term(px), a.lag),
    }
    tbl = pd.DataFrame({k: stats(v, spy) for k, v in rows.items()}).T
    fmt = {c: "{:.1%}".format for c in ["CAGR", "MaxDD", "Vol", "Exposure"]}
    fmt.update({c: "{:.2f}".format for c in ["Sharpe", "Corr_d", "Corr_m"]})
    print(tbl.to_string(formatters=fmt))
    print("\nClaim to beat:  CAGR 60%   MaxDD > -5%   Corr < 0")

    print("\nCalendar-year returns:")
    yr = pd.DataFrame({k: v for k, v in rows.items()}).resample("YE").apply(lambda x: (1 + x).prod() - 1)
    yr.index = yr.index.year
    print(yr.map("{:+.0%}".format).to_string())

    if a.grid:
        print("\nIn-sample grid (parameters chosen with hindsight -> optimistic upper bound):")
        res = []
        for t in [0.90, 0.95, 1.0, 1.05, 1.1]:
            res.append(("term", f"thresh={t}", run(px, w_term(px, t), a.lag)))
            for s in [0.5, 1.0]:
                res.append(("long/short", f"thresh={t} short={s}", run(px, w_longshort(px, t, s), a.lag)))
        for ma, j, h in itertools.product([5, 10, 20], [0.05, 0.10, 0.15, 0.25], [0.95, 1.0, 1.05]):
            res.append(("spike", f"ma={ma} jump={j} hold={h}", run(px, w_spike(px, ma, j, h), a.lag)))
        for otm, b in itertools.product([0.0, 0.03, 0.05, 0.10], [0.0025, 0.005, 0.01, 0.02]):
            res.append(("puts", f"otm={otm} budget={b}", r_puts(px, otm, b)))
        g = pd.DataFrame([{"family": f, "params": p, **stats(r, spy)} for f, p, r in res])
        print("\nBest CAGR per family:")
        print(g.loc[g.groupby("family").CAGR.idxmax()].to_string(index=False, formatters=fmt))
        print("\nBest MaxDD-constrained (MaxDD > -5%) per family:")
        ok = g[g.MaxDD > -0.05]
        print(ok.loc[ok.groupby("family").CAGR.idxmax()].to_string(index=False, formatters=fmt) if len(ok) else "  none")
        print(f"\nAny of {len(g)} variants with CAGR>=60% & MaxDD>-5%: {((g.CAGR >= 0.6) & (g.MaxDD > -0.05)).any()}")
        print(f"Any with CAGR>=20% & MaxDD>-20% & Corr_d<0: {((g.CAGR >= 0.2) & (g.MaxDD > -0.2) & (g.Corr_d < 0)).any()}")


if __name__ == "__main__":
    main()
