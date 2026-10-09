"""Was there an early warning before the live design's worst falls? (owner, 2026-10-09)

Events: the peaks of the five worst drawdowns on real ETFs and on the 2001-2026 proxy
(research/drawdown_anatomy.py), plus four well-known QQQ shocks the design came through with
smaller losses. For each event, ~20 market readings are taken at the peak and over the 10 sessions
before it, ranked as percentiles of the same reading on ALL effective-A days (the state the book is
in at every peak). A useful trigger must be extreme before most events AND rare on A days in
general; the second half measures that hit rate and what followed.

    python -m research.dd_early_warning
"""
import numpy as np
import pandas as pd
import yfinance as yf

from research.a_ratio_live_rules import load, prepare, S

EVENTS = {
    "2025-02-19": "real #1 (-18.7%)", "2023-10-11": "real #2 (-15.4%)", "2015-11-04": "real #3 / proxy #5",
    "2019-07-26": "real #4 (-14.9%)", "2021-09-07": "real #5 (-14.5%)", "2011-04-27": "proxy #1 (-23.5%)",
    "2004-12-14": "proxy #2 (-22.2%)", "2021-11-19": "proxy #3 (-21.9%)", "2007-07-19": "proxy #4 (-21.3%)",
    "2018-01-26": "shock: Feb 2018", "2018-10-01": "shock: Q4 2018", "2020-02-19": "shock: COVID",
    "2024-07-10": "shock: Jul-Aug 2024",
}
TICK = ["QQQ", "QQEW", "SPY", "RSP", "IWM", "SOXX", "SPHB", "SPLV", "HYG", "IEF", "TLT", "GLD", "^VIX", "^VIX3M",
        "^VIX9D", "^VVIX", "^SKEW", "^MOVE", "^TNX", "DX-Y.NYB", "CL=F", "HG=F", "SPMO", "XLU"]


def features():
    px = yf.download(TICK, start="2000-01-01", end="2026-10-08", progress=False, auto_adjust=False)["Close"].ffill()
    r = lambda a, n: px[a] / px[a].shift(n) - 1
    rel = lambda a, b, n: r(a, n) - r(b, n)
    q = px.QQQ
    lr = np.log(q).diff()
    f = pd.DataFrame(index=px.index)
    f["VIX"] = px["^VIX"]
    f["VIX 5d chg"] = px["^VIX"] - px["^VIX"].shift(5)
    f["VIX/VIX3M"] = px["^VIX"] / px["^VIX3M"]
    f["VIX9D/VIX"] = px["^VIX9D"] / px["^VIX"]
    f["VVIX"] = px["^VVIX"]
    f["SKEW"] = px["^SKEW"]
    f["MOVE"] = px["^MOVE"]
    f["10y yld 20d chg (bp)"] = (px["^TNX"] - px["^TNX"].shift(20)) * 10
    f["dollar 20d"] = r("DX-Y.NYB", 20)
    f["credit HYG-IEF 20d"] = rel("HYG", "IEF", 20)
    f["breadth RSP-SPY 20d"] = rel("RSP", "SPY", 20)
    f["breadth QQEW-QQQ 20d"] = rel("QQEW", "QQQ", 20)
    f["small caps IWM-SPY 20d"] = rel("IWM", "SPY", 20)
    f["semis SOXX-QQQ 20d"] = rel("SOXX", "QQQ", 20)
    f["hi-beta SPHB-SPLV 20d"] = rel("SPHB", "SPLV", 20)
    f["momentum SPMO-SPY 20d"] = rel("SPMO", "SPY", 20)
    f["defensive XLU-SPY 20d"] = rel("XLU", "SPY", 20)
    f["gold 20d"] = r("GLD", 20)
    f["oil 20d"] = r("CL=F", 20)
    f["copper/gold 20d"] = r("HG=F", 20) - r("GLD", 20)
    f["QQQ 20d"] = r("QQQ", 20)
    f["QQQ 5d"] = r("QQQ", 5)
    f["QQQ vs 20d high"] = q / q.rolling(20).max() - 1
    f["QQQ vol10/vol30"] = lr.rolling(10).std() / lr.rolling(30).std()
    f["QQQ up days of last 10"] = (lr > 0).rolling(10).sum()
    f.index = [d.strftime("%Y-%m-%d") for d in f.index]
    return f, px


if __name__ == "__main__":
    f, px = features()
    P = prepare(load())
    adays = [d for d in P["dates"] if d >= "2004-01-01" and S.effective_state(P["st"][d], P["fa"][d]) == "A" and d in f.index]
    FA = f.loc[adays]
    pct = lambda col, v: float((FA[col].dropna() < v).mean() * 100) if pd.notna(v) else np.nan
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
    at, ext = {}, {}
    for d, lab in EVENTS.items():
        i = f.index.get_loc(d)
        win = f.iloc[i - 10:i + 1]
        at[lab] = {c: pct(c, f.iloc[i][c]) for c in f.columns}
        ext[lab] = {c: (pct(c, win[c].max()) if pct(c, f.iloc[i][c]) >= 50 else pct(c, win[c].min())) for c in f.columns}
    A = pd.DataFrame(at).round(0)
    print("Percentile of each reading AT THE PEAK, versus all A days 2004-2026 (50 = typical; <10 or >90 = unusual)")
    print(A.to_string())
    E = pd.DataFrame(ext).round(0)
    print("\nMost extreme percentile over the 10 sessions up to the peak (in the direction of the peak reading)")
    print(E.to_string())
    n = len(EVENTS)
    print("\nHow many of the", n, "events had each reading beyond the 90th or below the 10th percentile in the 10 days before the peak:")
    hi = (E >= 90).sum(axis=1); lo = (E <= 10).sum(axis=1)
    print(pd.DataFrame({"high (>=90th)": hi, "low (<=10th)": lo}).sort_values(["high (>=90th)", "low (<=10th)"], ascending=False).to_string())
    f.to_csv("/tmp/dd_features.csv")
