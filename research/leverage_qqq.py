"""How much Nasdaq leverage pays, and does CAOS actually protect a QLD position?

Checks the claims in 期权坤哥's "QQQ tail strategy" post (Oct 2026):
  - QLD (2x) is the leverage "sweet spot"; TQQQ (3x) loses more to daily-reset drag.
  - "Past 8 years: 4x ~100%/yr, but 1M falls to 350k" (about -65% max drawdown).
  - CAOS (Alpha Architect Tail Risk ETF) offsets QLD losses in crashes.

Synthetic L-x QQQ = daily reset: L * QQQ total return - (L-1) * T-bill - 0.95%/yr fee.
It is checked against the real QLD and TQQQ before being extended back to 1999.

    python -m research.leverage_qqq
"""
import math
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.simplefilter("ignore")
FEE = 0.0095
LEVELS = [1, 1.5, 2, 2.5, 3, 4]


def load():
    px = yf.download(["QQQ", "QLD", "TQQQ", "XLU", "CAOS", "BIL"], start="1999-03-10", progress=False, auto_adjust=True)["Close"]
    irx = yf.download("^IRX", start="1999-03-10", progress=False, auto_adjust=True)["Close"].squeeze()
    rf = (irx.reindex(px.index).ffill() / 100 / 252).fillna(0)
    return px, rf


def synth(q: pd.Series, rf: pd.Series, L: float) -> pd.Series:
    if L == 1:
        return q
    return L * q - (L - 1) * rf - FEE / 252


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    under = (dd < 0).astype(int)
    longest = under.groupby((under == 0).cumsum()).sum().max()
    return {"CAGR": eq.iloc[-1] ** (252 / len(r)) - 1, "MaxDD": dd.min(), "Vol": r.std() * math.sqrt(252),
            "$1M ->": eq.iloc[-1] * 1e6, "Trough of $1M": (1 + dd.min()) * 1e6, "Longest underwater (yrs)": longest / 252}


def fmt(df):
    out = df.copy()
    for c in out.columns:
        if c in ("CAGR", "MaxDD", "Vol") or c.startswith("Track"):
            out[c] = out[c].map(lambda x: f"{x:+.1%}")
        elif "$" in c:
            out[c] = out[c].map(lambda x: f"${x/1e6:,.2f}M")
        elif "yrs" in c:
            out[c] = out[c].map(lambda x: f"{x:.1f}")
    return out


def main():
    px, rf = load()
    rets = px.pct_change()
    q = rets.QQQ.dropna()
    rf = rf.reindex(q.index).fillna(0)
    lev = pd.DataFrame({L: synth(q, rf, L) for L in LEVELS})

    # 0. sanity: synthetic vs real ETFs
    print("0) Synthetic vs real leveraged ETFs (annual return over the real ETF's life)")
    for t, L in [("QLD", 2), ("TQQQ", 3)]:
        real = rets[t].dropna()
        s = lev[L].reindex(real.index)
        print(f"   {t}: real {stats(real)['CAGR']:+.1%}  synthetic {stats(s)['CAGR']:+.1%}  daily corr {real.corr(s):.3f}")

    # 1. the article's 8 years, and longer windows
    end = "2026-10-05"
    for label, start in [("Article's window: last 8 years", "2018-10-05"), ("Since 2010 (TQQQ launch)", "2010-02-11"),
                         ("Since 1999 (includes dot-com and 2008)", "1999-03-11")]:
        t = pd.DataFrame({f"{L}x": stats(lev[L].loc[start:end]) for L in LEVELS}).T
        print(f"\n1) {label}  ({start} -> {end})")
        print(fmt(t).to_string())

    # 2. which leverage won, across every 8-year window
    print("\n2) Best leverage (highest ending wealth) across rolling 8-year windows, 1999-2026")
    win = 252 * 8
    logret = np.log1p(lev)
    roll = logret.rolling(win).sum().dropna()
    best = roll.idxmax(axis=1)
    print("   share of windows each level wins: " + "  ".join(f"{L}x {(best == L).mean():.0%}" for L in LEVELS))
    for d in ["2007-06-01", "2010-03-01", "2016-01-04", "2026-10-05"]:
        row = roll.loc[:d].iloc[-1]
        print(f"   8 yrs ending {d}: " + "  ".join(f"{L}x {math.exp(v):.1f}x" for L, v in row.items()))

    # 3. CAOS as insurance for QLD
    c = rets.CAOS.dropna()
    s = c.index[0]
    print(f"\n3) CAOS since launch {s.date()}: annual {stats(c)['CAGR']:+.1%}, max drawdown {stats(c)['MaxDD']:+.1%}, "
          f"BIL {stats(rets.BIL.loc[s:])['CAGR']:+.1%}, corr to QQQ {c.corr(q.loc[s:]):+.2f}")
    qq = px.QQQ.loc[s:]
    eps = []
    dd = qq / qq.cummax() - 1
    # find the QQQ drawdowns deeper than 7% since CAOS launched
    in_dd, peak = False, None
    for d, v in dd.items():
        if not in_dd and v < -0.07:
            in_dd, peak = True, qq.loc[:d].idxmax()
        if in_dd and v == 0:
            trough = dd.loc[peak:d].idxmin()
            eps.append((peak, trough)); in_dd = False
    if in_dd:
        eps.append((peak, dd.loc[peak:].idxmin()))
    rows = {}
    for a, b in eps:
        seg = rets.loc[a:b].iloc[1:]
        rows[f"{a.date()} -> {b.date()}"] = {t: (1 + seg[t]).prod() - 1 for t in ["QQQ", "QLD", "TQQQ", "XLU", "CAOS"]}
    print("   QQQ peak-to-trough drawdowns > 7%:")
    print(pd.DataFrame(rows).T.map(lambda x: f"{x:+.1%}").to_string())

    # 4. portfolios since CAOS launch, monthly rebalanced
    print(f"\n4) Portfolios since {s.date()}, rebalanced monthly")
    mixes = {"QQQ": {"QQQ": 1}, "QLD": {"QLD": 1}, "TQQQ": {"TQQQ": 1},
             "50 QLD / 50 BIL (same exposure as QQQ)": {"QLD": .5, "BIL": .5},
             "50 QLD / 50 CAOS": {"QLD": .5, "CAOS": .5},
             "50 QLD / 25 CAOS / 25 XLU": {"QLD": .5, "CAOS": .25, "XLU": .25},
             "40 QLD / 20 CAOS / 20 XLU / 20 BIL": {"QLD": .4, "CAOS": .2, "XLU": .2, "BIL": .2},
             "90 QLD / 10 CAOS": {"QLD": .9, "CAOS": .1}}
    r = rets.loc[s:].iloc[1:].fillna(0)
    out = {}
    for name, w in mixes.items():
        w = pd.Series(w)
        eq, val = [], 1.0
        hold = w.copy()
        for d, row in r.iterrows():
            hold = hold * (1 + row[hold.index])
            val = hold.sum()
            eq.append(val)
            if d.is_month_end or (d + pd.offsets.BDay(1)).month != d.month:
                hold = w * val
        e = pd.Series(eq, index=r.index)
        out[name] = stats(e.pct_change().fillna(e.iloc[0] - 1))
    print(fmt(pd.DataFrame(out).T[["CAGR", "MaxDD", "Vol"]]).to_string())


if __name__ == "__main__":
    main()
