"""
Fast monthly backtest engine shared by the research scripts.

All signals are computed on DAILY data (true 6/12-month windows in trading
days) and looked up at month-end rebalance dates, so they are frequency-safe.
Portfolios are equal-weight, rebalanced monthly; returns use adjusted close
(dividends reinvested).  Return at index t+1 = mean over names held at t.
"""
import numpy as np
import pandas as pd
import yfinance as yf

from backtest import load_data, month_end_dates

END = "2026-09-23"


class Engine:
    def __init__(self, end=END):
        self.close, self.adj, self.div, self.spy = load_data()
        idx = self.close.index
        self.mes = month_end_dates(idx, idx.min(), end)
        m = self.mes
        self.px = self.close.reindex(m)
        adjm = self.adj.reindex(m)
        try:                                                  # 'CASH' = SHY (1-3y Treasuries) total return
            shy = yf.download("SHY", start="2005-09-01", end="2026-10-05", auto_adjust=False, progress=False)["Adj Close"].squeeze()
            adjm["CASH"] = shy.reindex(m, method="ffill")
        except Exception:
            adjm["CASH"] = 1.0
        self.adjm = adjm
        self.ret_next = adjm.shift(-1) / adjm - 1            # return earned from t to t+1
        ttm_d = self.div.fillna(0).rolling("365D").sum()
        self.ttm = ttm_d.reindex(m)
        self.ttm_prior = ttm_d.shift(252).reindex(m)
        self.mom = {lb: self.close.pct_change(lb).reindex(m) for lb in (21, 126, 252)}
        self.yld = (self.ttm / self.px).replace([np.inf, -np.inf], np.nan)
        self.spy_ret = self.spy.reindex(m).pct_change()      # return ending at t
        self.n = len(m)

    # ---- barbell candidate lists (ranked), computed once per config family
    def hy_ranked(self, screens=True):
        out = {}
        for d in self.mes:
            row = self.yld.loc[d].dropna()
            row = row[self.px.loc[d, row.index].notna()]
            if screens:
                prior, cur = self.ttm_prior.loc[d], self.ttm.loc[d]
                cut = (cur < prior) & prior.notna() & (prior > 0)
                row = row.drop(index=[t for t in cut[cut].index if t in row.index])
                m6 = self.mom[126].loc[d]
                row = row.drop(index=[t for t in m6[m6 < -0.25].index if t in row.index])
            out[d] = list(row.sort_values(ascending=False).index)
        return out

    def growth_ranked(self, abs_mom=True, lookback=252):
        out = {}
        for d in self.mes:
            row = self.yld.loc[d].dropna()
            row = row[self.px.loc[d, row.index].notna()]
            zy = row[row <= 1e-9].index
            m = self.mom[lookback].loc[d].reindex(zy).dropna()
            if abs_mom:
                m = m[m > 0]
            out[d] = list(m.sort_values(ascending=False).index)
        return out

    # ---- returns
    def port_returns(self, holdings, start=None, end=None):
        """holdings: {date: [tickers]} -> monthly return series indexed by the NEXT month-end."""
        pos = {d: i for i, d in enumerate(self.mes)}
        rets, idx = [], []
        for d in sorted(holdings):
            i = pos.get(d)
            if i is None or i + 1 >= self.n or not holdings[d]:
                continue
            r = self.ret_next.loc[d, holdings[d]].mean(skipna=True)
            if np.isfinite(r):
                rets.append(r)
                idx.append(self.mes[i + 1])
        s = pd.Series(rets, index=pd.DatetimeIndex(idx))
        if start is not None:
            s = s[s.index >= pd.Timestamp(start)]
        if end is not None:
            s = s[s.index <= pd.Timestamp(end)]
        return s

    def barbell(self, hy_n=10, gr_n=20, hy=None, gr=None, cap_fn=None, mode="cash_slots", start=None):
        """mode: 'skip'       - if either leg is short, hold 100% cash that month (what early backtests did implicitly)
                 'cash_slots' - hold what qualifies, fill missing slots with cash (absolute-momentum de-risking)
                 'shrink'     - hold what qualifies, fully invested in fewer names (what the live paper trail does)"""
        h = {}
        for d in self.mes:
            if start is not None and d < pd.Timestamp(start):
                continue
            a = hy[d][:hy_n]
            b = cap_fn(gr[d], d, gr_n) if cap_fn else gr[d][:gr_n]
            short = (hy_n - len(a)) + (gr_n - len(b))
            if mode == "skip":
                h[d] = a + b if short == 0 else ["CASH"] * (hy_n + gr_n)
            elif mode == "cash_slots":
                h[d] = a + b + ["CASH"] * short
            else:
                if a + b:
                    h[d] = a + b
        return h


def stats(r, ppy=12):
    if len(r) < 12:
        return (np.nan,) * 4
    n_years = len(r) / ppy                                   # r must be a contiguous monthly series
    cum = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (1 / n_years) - 1
    vol = r.std() * np.sqrt(ppy)
    sharpe = r.mean() * ppy / vol if vol > 0 else np.nan
    return cagr, vol, sharpe, (cum / cum.cummax() - 1).min()
