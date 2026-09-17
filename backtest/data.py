"""Historical adjusted-close price fetching, with local CSV caching."""
from __future__ import annotations

import pathlib
import time

import pandas as pd
import yfinance as yf

DATA_DIR = pathlib.Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def get_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Return a DataFrame of daily adjusted close prices, columns=tickers.

    Caches each ticker's full history to backtest/data/<ticker>.csv so repeat
    runs don't re-hit the network.
    """
    tickers = sorted(set(tickers))
    frames = {}
    missing = []
    for t in tickers:
        cache_file = DATA_DIR / f"{t}.csv"
        if cache_file.exists():
            s = pd.read_csv(cache_file, index_col=0, parse_dates=True)["Close"]
        else:
            missing.append(t)
            continue
        frames[t] = s

    for t in missing:
        for attempt in range(3):
            try:
                df = yf.download(
                    t, start="2010-01-01", auto_adjust=True, progress=False
                )
                if df.empty:
                    print(f"WARNING: no data for {t}")
                    break
                s = df["Close"]
                if hasattr(s, "columns"):
                    s = s.iloc[:, 0]
                s.name = "Close"
                s.to_frame().to_csv(DATA_DIR / f"{t}.csv")
                frames[t] = s
                break
            except Exception as e:  # noqa: BLE001
                print(f"retry {t}: {e}")
                time.sleep(2)

    prices = pd.DataFrame(frames)
    prices = prices.loc[(prices.index >= start) & (prices.index <= end)]
    prices = prices.sort_index()
    return prices
