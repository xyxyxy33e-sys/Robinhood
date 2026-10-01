"""Market data via yfinance (free, no account needed)."""
from datetime import date, datetime
from typing import Optional

import pandas as pd
import yfinance as yf

ET = "America/New_York"


def minute_bars(symbol: str, period: str = "7d", interval: str = "1m") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval, prepost=True, progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = df.index.tz_convert(ET) if df.index.tz else df.index.tz_localize("UTC").tz_convert(ET)
    return df


class Chain:
    """Thin cache over yfinance option chains, used for real expiries and implied vol."""

    def __init__(self, symbol: str):
        self.t = yf.Ticker(symbol)
        self.expiries = [date.fromisoformat(s) for s in self.t.options]
        self._cache: dict = {}

    def pick_expiry(self, min_days: int):
        def pick(now: datetime, window: str) -> date:
            need = 0 if window == "0DTE" else min_days
            for e in self.expiries:
                if (e - now.date()).days >= need:
                    return e
            raise RuntimeError("no suitable expiry listed")

        return pick

    def quote(self, expiry: date, strike: float, right: str) -> Optional[pd.Series]:
        key = expiry.isoformat()
        oc = self.t.option_chain(key)  # refetch every call: we want fresh numbers
        tbl = oc.calls if right == "C" else oc.puts
        row = tbl[tbl["strike"] == strike]
        return None if row.empty else row.iloc[0]

    def iv(self, now: datetime, expiry: date, strike: float, right: str) -> Optional[float]:
        try:
            q = self.quote(expiry, strike, right)
        except Exception:
            return None
        if q is None:
            return None
        iv = float(q.get("impliedVolatility", 0) or 0)
        # yfinance reports junk IVs (e.g. 0.00001 or >3) on some 0DTE strikes; let the engine fall back.
        return iv if 0.05 < iv < 1.5 else None
