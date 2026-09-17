"""Compute the 'Dogs of the Dow' (10 highest-yielding Dow stocks) for each
year, using trailing-12-month dividends / year-end close price, applied to
the actual Dow-30 membership at that year-end (see djia_constituents.py).

This reconstructs the standard Dogs-of-the-Dow methodology directly from
price/dividend data rather than scraping a third-party list site.
"""
from __future__ import annotations

import json
import time

import pandas as pd
import yfinance as yf

from djia_constituents import constituents_at_year_end

ALL_TICKERS = sorted({t for y in range(2013, 2026) for t in constituents_at_year_end(y)})


def yield_at_year_end(ticker: str, year: int) -> float | None:
    t = yf.Ticker(ticker)
    for attempt in range(3):
        try:
            divs = t.dividends
            hist = t.history(start=f"{year}-12-15", end=f"{year + 1}-01-10", auto_adjust=False)
            break
        except Exception:
            time.sleep(2)
    else:
        return None
    if hist.empty:
        return None
    hist.index = hist.index.tz_localize(None)
    close_row = hist[hist.index <= f"{year}-12-31"]
    if close_row.empty:
        return None
    year_end_close = close_row["Close"].iloc[-1]

    if divs.empty:
        return 0.0
    divs = divs.copy()
    divs.index = divs.index.tz_localize(None)
    ttm = divs[(divs.index > f"{year - 1}-12-31") & (divs.index <= f"{year}-12-31")].sum()
    return float(ttm / year_end_close)


def dogs_for_year(year: int) -> list[str]:
    """The Dogs-of-the-Dow list to HOLD during `year`, i.e. top-10 yield of
    the Dow-30 membership as of Dec 31 of `year - 1`."""
    members = constituents_at_year_end(year - 1)
    yields = {}
    for tkr in members:
        y = yield_at_year_end(tkr, year - 1)
        if y is not None:
            yields[tkr] = y
    top10 = sorted(yields.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return [t for t, _ in top10], yields


if __name__ == "__main__":
    result = {}
    for year in range(2015, 2027):
        tickers, yields = dogs_for_year(year)
        result[year] = tickers
        print(year, tickers)
    with open("dogs_of_the_dow.json", "w") as f:
        json.dump(result, f, indent=2)
