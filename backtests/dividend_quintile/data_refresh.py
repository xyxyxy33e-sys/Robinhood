"""
Keeps the local price/dividend cache (.cache/sp500_data.parquet) current so the
monthly rebalance never trades off stale signals, and rebuilds it from scratch
if the cache is missing (e.g. a fresh container).

  python3 data_refresh.py          # incremental refresh (or full rebuild if no cache)
  python3 data_refresh.py --full   # force full rebuild

Also writes .cache/universe.json = current S&P 500 constituents (Wikipedia),
which live-signal code uses to restrict to today's members. Names newly added
to the index are downloaded in full; the cache keeps old members (harmless).
"""
import io
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

CACHE = Path(__file__).resolve().parent / ".cache"
PARQUET = CACHE / "sp500_data.parquet"
UNIVERSE = CACHE / "universe.json"
FIELDS = ["Close", "Adj Close", "Dividends"]
START = "2005-09-01"


def current_constituents():
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    df = pd.read_html(io.StringIO(r.text))[0]
    return df["Symbol"].str.replace(".", "-", regex=False).tolist()


def download(tickers, start, end=None, batch=50):
    end = end or (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    frames = {}
    for i in range(0, len(tickers), batch):
        b = tickers[i:i + batch]
        for _ in range(3):
            try:
                d = yf.download(b, start=start, end=end, group_by="ticker", actions=True,
                                auto_adjust=False, progress=False, threads=True)
                break
            except Exception:
                time.sleep(3)
        else:
            continue
        for t in b:
            try:
                sub = d[t] if len(b) > 1 else d
                sub = sub.dropna(how="all")
                if not sub.empty and sub["Close"].dropna().size:
                    frames[t] = sub[FIELDS]
            except Exception:
                pass
    return pd.concat(frames, axis=1, names=["Ticker", "Field"]) if frames else pd.DataFrame()


def refresh(force_full=False):
    CACHE.mkdir(exist_ok=True)
    members = current_constituents()
    UNIVERSE.write_text(json.dumps(members))
    tickers = sorted(set(members + ["SPY"]))
    if force_full or not PARQUET.exists():
        print(f"Full download of {len(tickers)} tickers from {START}...")
        store = download(tickers, START)
    else:
        store = pd.read_parquet(PARQUET)
        store.index = pd.to_datetime(store.index)
        have = set(store.columns.get_level_values(0))
        last = store.index.max()
        start = (last - timedelta(days=10)).strftime("%Y-%m-%d")
        print(f"Incremental refresh from {start} (cache ends {last.date()})")
        new = download([t for t in tickers if t in have], start)
        new_names = [t for t in tickers if t not in have]
        if new_names:
            print("New index members, full history:", new_names)
            new = pd.concat([new, download(new_names, START)], axis=1) if not new.empty else download(new_names, START)
        store = new.combine_first(store) if not new.empty else store
        # incremental rows override overlapping old rows (new data wins)
        if not new.empty:
            overlap = new.index.intersection(store.index)
            store.loc[overlap, new.columns] = new.loc[overlap, new.columns]
    store = store.sort_index()
    store.to_parquet(PARQUET)
    cov = store.xs("Close", axis=1, level="Field").notna().sum(axis=1)
    print(f"Cache saved: {store.shape}, last date {store.index.max().date()}, "
          f"tickers priced on last date: {int(cov.iloc[-1])}/{len(tickers)}")
    return store


if __name__ == "__main__":
    refresh(force_full="--full" in sys.argv)
