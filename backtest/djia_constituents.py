"""Dow Jones Industrial Average constituents at each year-end, reconstructed
from the documented index change history (Wikipedia: "Historical components
of the Dow Jones Industrial Average"). Used to compute "Dogs of the Dow"
(the 10 highest dividend-yield Dow stocks as of the prior year-end) without
depending on a scrapeable third-party list site.
"""
from __future__ import annotations

# Base list as of year-end 2014 (i.e. after the Sept 23, 2013 change: added
# NKE, GS, V; removed AA, BAC, HPQ. No changes again until Mar 2015).
_BASE_2014 = {
    "MMM", "AXP", "T", "BA", "CAT", "CVX", "CSCO", "KO", "DD", "XOM",
    "GE", "GS", "HD", "IBM", "INTC", "JNJ", "JPM", "MCD", "MRK", "MSFT",
    "NKE", "PFE", "PG", "TRV", "UNH", "UTX", "VZ", "V", "WMT", "DIS",
}

# (effective_date, {tickers added}, {tickers removed})
_CHANGES = [
    ("2015-03-19", {"AAPL"}, {"T"}),
    ("2017-09-01", {"DWDP"}, {"DD"}),
    ("2018-06-26", {"WBA"}, {"GE"}),
    ("2019-04-02", {"DOW"}, {"DWDP"}),
    ("2020-04-06", {"RTX"}, {"UTX"}),
    ("2020-08-31", {"AMGN", "HON", "CRM"}, {"XOM", "PFE", "RTX"}),
    ("2024-02-26", {"AMZN"}, {"WBA"}),
    ("2024-11-08", {"NVDA", "SHW"}, {"INTC", "DOW"}),
    ("2026-06-29", {"GOOGL"}, {"VZ"}),
]


def constituents_at_year_end(year: int) -> list[str]:
    """Dow 30 membership as of Dec 31 of `year`."""
    members = set(_BASE_2014)
    cutoff = f"{year}-12-31"
    for date, added, removed in _CHANGES:
        if date <= cutoff:
            members -= removed
            members |= added
    assert len(members) == 30, f"expected 30 members at {year}, got {len(members)}: {members}"
    return sorted(members)
