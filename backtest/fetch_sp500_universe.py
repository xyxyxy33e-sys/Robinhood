"""Fetch current S&P 500 constituent list and their daily close price
history, used as the universe for the random-momentum baseline. Writes
sp500_list.csv and sp500_close.csv (both gitignored; regenerate on demand).
"""
from __future__ import annotations

import io

import pandas as pd
import requests
import yfinance as yf

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def main():
    r = requests.get(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    table = pd.read_html(io.StringIO(r.text))[0]
    table.to_csv("sp500_list.csv", index=False)

    symbols = table["Symbol"].str.replace(".", "-", regex=False).tolist()
    symbols = sorted(set(symbols + ["SPY"]))

    df = yf.download(
        symbols, start="2021-06-01", auto_adjust=True, progress=False,
        group_by="ticker", threads=True,
    )
    close = df.xs("Close", axis=1, level=1)
    close.to_csv("sp500_close.csv")
    print(f"Saved {len(symbols)} tickers, {close.shape[0]} trading days -> sp500_close.csv")


if __name__ == "__main__":
    main()
