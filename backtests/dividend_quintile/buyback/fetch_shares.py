import concurrent.futures as cf
import pandas as pd, yfinance as yf
from backtest import load_data

close, adj, div, spy_adj = load_data()
tickers = list(close.columns)

def fetch(t):
    try:
        s = yf.Ticker(t).get_shares_full(start="2004-01-01", end="2026-09-28")
        if s is None or len(s) == 0: return t, None
        s = s[~s.index.duplicated(keep="last")]
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        return t, s.sort_index()
    except Exception as e:
        return t, None

out = {}
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    for t, s in ex.map(fetch, tickers):
        if s is not None: out[t] = s
df = pd.concat(out, axis=1)
df.to_parquet("shares.parquet")
print("tickers with share data:", df.shape[1], "of", len(tickers))
print("first obs per ticker (median):", df.apply(lambda c: c.first_valid_index()).median())
print(df.apply(lambda c: c.first_valid_index()).describe())
