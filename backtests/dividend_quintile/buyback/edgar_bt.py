"""
Backtest: rank S&P 500 by TTM buyback dollars / market cap using SEC EDGAR
facts, point-in-time (only facts with filed <= rebalance date are used).

TTM repurchases at date D:
  latest fact L (by period end, filed<=D). If L is a full year -> TTM = L.
  Else (YTD 10-Q, cumulative in fiscal year): TTM = FY_prev + L - L_prior_year,
  where FY_prev is the latest 10-K year ending before L.start and L_prior_year
  is the same YTD period one year earlier. Falls back to FY_prev if pieces missing.
Market cap = month-end price x latest shares outstanding filed<=D.
"""
import json
import numpy as np, pandas as pd
from backtest import load_data, month_end_dates, simulate_equal_weight, perf_stats

END = "2026-09-23"
close, adj, div, spy_adj = load_data()
all_dates = close.index
mes = month_end_dates(all_dates, all_dates.min(), END)
facts = json.load(open("edgar_facts.json"))

def prep_rep(rows):
    df = pd.DataFrame(rows)
    if df.empty: return df
    for c in ("start", "end", "filed"): df[c] = pd.to_datetime(df[c])
    df["dur"] = (df["end"] - df["start"]).dt.days
    df = df[(df["dur"] > 60) & (df["dur"] < 380)]
    # keep the earliest filing of each period (as first reported); later ones may be restated
    return df.sort_values("filed").drop_duplicates(["start", "end"], keep="first")

def ttm_at(df, dt):
    d = df[df["filed"] <= dt]
    if d.empty: return np.nan
    L = d.sort_values(["end", "filed"]).iloc[-1]
    if (dt - L["end"]).days > 500: return np.nan
    if L["dur"] >= 350: return L["val"]
    fy = d[(d["dur"] >= 350) & (d["end"] < L["start"] + pd.Timedelta(days=15))]
    if fy.empty: return np.nan
    FY = fy.sort_values("end").iloc[-1]
    prior = d[(abs(d["dur"] - L["dur"]) <= 12) & (abs((L["end"] - d["end"]).dt.days - 365) <= 12)]
    if prior.empty: return FY["val"]
    return FY["val"] + L["val"] - prior.sort_values("end").iloc[-1]["val"]

def shares_at(df, dt):
    d = df[df["filed"] <= dt]
    if d.empty or (dt - d["end"].max()).days > 200: return np.nan
    return d.sort_values(["end", "filed"]).iloc[-1]["val"]

bb = pd.DataFrame(np.nan, index=mes, columns=close.columns)      # buyback / market cap
sh_series = {}
for t, d in facts.items():
    if not d["rep"] or not d["shares"] or t not in close.columns: continue
    rep = prep_rep(d["rep"])
    sh = pd.DataFrame(d["shares"])
    for c in ("end", "filed"): sh[c] = pd.to_datetime(sh[c])
    sh_series[t] = sh
    if rep.empty: continue
    for dt in mes:
        px = close.at[dt, t] if dt in close.index else np.nan
        if not np.isfinite(px): continue
        ttm, s = ttm_at(rep, dt), shares_at(sh, dt)
        if np.isfinite(ttm) and np.isfinite(s) and s > 0:
            bb.at[dt, t] = ttm / (px * s)
bb = bb.where((bb > 0) & (bb < 0.5))
print("avg valid names/month by year:")
print(bb.notna().sum(axis=1).groupby(bb.index.year).mean().round(0).to_string())
bb.to_parquet("edgar_bb_yield.parquet")

def build(score, n, start):
    h = {}
    for dt in mes:
        if dt < start: continue
        s = score.loc[dt].dropna()
        if len(s) >= max(n, 50): h[dt] = list(s.sort_values(ascending=False).head(n).index)
    return h

START = pd.Timestamp("2011-01-01")
first = bb.dropna(how="all").index.min()
print("first signal:", first.date())
WINDOWS = {"5y": "2021-09-23", "10y": "2016-09-23", "full (2011+)": "2011-01-01"}
results = {}
for n in (20, 30, 50):
    h = build(bb, n, START)
    for w, st in WINDOWS.items():
        bt = month_end_dates(all_dates, st, END)
        results[(f"Buyback yield top {n}", w)] = simulate_equal_weight(adj, h, bt)
for w, st in WINDOWS.items():
    bt = month_end_dates(all_dates, st, END)
    results[("SPY", w)] = spy_adj.reindex(bt).pct_change().dropna()
for (name, w), r in results.items():
    if name == "SPY" or True:
        perf_stats(r, f"[{w}] {name}")
pd.to_pickle(results, "edgar_results.pkl")
