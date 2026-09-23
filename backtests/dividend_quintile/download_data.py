"""Download 20y of daily OHLC + dividends for current S&P 500 constituents + SPY."""
import io
import time
import pandas as pd
import requests
import yfinance as yf

HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_sp500_tickers():
    r = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers=HEADERS, timeout=20,
    )
    tables = pd.read_html(io.StringIO(r.text))
    df = tables[0]
    tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
    return tickers

def main():
    tickers = get_sp500_tickers()
    print(f"Got {len(tickers)} tickers")
    all_tickers = tickers + ["SPY"]

    start = "2005-09-01"  # extra buffer before 20y window for TTM dividend calc
    end = "2026-09-23"

    batch_size = 50
    frames = {}
    failed = []
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i+batch_size]
        for attempt in range(3):
            try:
                d = yf.download(
                    batch, start=start, end=end, group_by="ticker",
                    actions=True, auto_adjust=False, progress=False,
                    threads=True,
                )
                break
            except Exception as e:
                print("retry", e)
                time.sleep(3)
        else:
            failed.extend(batch)
            continue

        for t in batch:
            try:
                if len(batch) == 1:
                    sub = d
                else:
                    sub = d[t]
                sub = sub.dropna(how="all")
                if sub.empty or sub["Close"].dropna().empty:
                    failed.append(t)
                    continue
                frames[t] = sub[["Close", "Adj Close", "Dividends"]]
            except Exception as e:
                failed.append(t)
        print(f"batch {i}-{i+batch_size} done, total collected={len(frames)}, failed={len(failed)}")

    print("Failed tickers:", failed)

    # Save to parquet: one file per ticker is slow; instead build a panel.
    store = pd.concat(frames, axis=1, names=["Ticker", "Field"])
    store.to_parquet("/tmp/claude-0/-home-user-Robinhood/9cd955bf-712e-5400-90f6-198dab301530/scratchpad/sp500_data.parquet")
    print("Saved parquet, shape:", store.shape)

if __name__ == "__main__":
    main()
