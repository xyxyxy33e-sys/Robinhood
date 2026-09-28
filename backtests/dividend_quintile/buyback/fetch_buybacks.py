import json, concurrent.futures as cf
import pandas as pd, yfinance as yf
from backtest import load_data

close, adj, div, spy_adj = load_data()
tickers = list(close.columns)
caps = json.load(open("market_caps.json"))

def fetch(t):
    try:
        tk = yf.Ticker(t)
        q = tk.quarterly_cashflow
        a = tk.cashflow
        def row(df, name):
            if df is None or df.empty or name not in df.index: return {}
            s = df.loc[name].dropna()
            return {str(k.date()): float(v) for k, v in s.items()}
        return t, {
            "q_rep": row(q, "Repurchase Of Capital Stock"),
            "q_net": row(q, "Net Common Stock Issuance"),
            "a_rep": row(a, "Repurchase Of Capital Stock"),
            "a_net": row(a, "Net Common Stock Issuance"),
        }
    except Exception as e:
        return t, {"error": str(e)}

out = {}
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    for t, d in ex.map(fetch, tickers):
        out[t] = d
json.dump(out, open("buybacks.json", "w"))
ok = sum(1 for d in out.values() if d.get("q_rep"))
print("fetched", len(out), "with quarterly repurchase data:", ok)
