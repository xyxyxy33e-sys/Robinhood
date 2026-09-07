#!/usr/bin/env python3
"""Record one trading day's close into portfolio/history.csv.

Usage: python3 scripts/record_close.py YYYY-MM-DD
Expects data/prices/YYYY-MM-DD.json to already exist (written by the daily
check-in from Robinhood MCP quotes).
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def main(date):
    h = lib.load_holdings()
    closes = lib.load_prices(date)["closes"]
    equity, nav, detail = lib.valuation(h, closes)

    spy = float(closes["SPY"])
    hist = [r for r in lib.read_history() if r["date"] < date]

    if hist:
        prev_nav = float(hist[-1]["nav"])
        day_ret = (nav / prev_nav - 1) * 100
        spy0 = float(hist[0]["spy_close"])
        nav0 = float(hist[0]["nav"])
        # first history row is inception, so base off inception values
        cum = (nav / nav0 - 1) * 100
        spy_cum = (spy / spy0 - 1) * 100
    else:
        day_ret = 0.0
        cum = (nav / h["inception_capital"] - 1) * 100
        spy_cum = 0.0

    row = {
        "date": date,
        "nav": f"{nav:.2f}",
        "cash": f"{h['cash']:.2f}",
        "equity": f"{equity:.2f}",
        "day_return_pct": f"{day_ret:.4f}",
        "cum_return_pct": f"{cum:.4f}",
        "spy_close": f"{spy:.2f}",
        "spy_cum_return_pct": f"{spy_cum:.4f}",
        "excess_return_pct": f"{cum - spy_cum:.4f}",
        "holdings_json": json.dumps(
            {s: round(d["value"], 2) for s, d in sorted(detail.items())},
            separators=(",", ":"),
        ),
    }
    lib.append_history(row)
    print(f"{date}  NAV ${nav:,.2f}  day {day_ret:+.2f}%  "
          f"cum {cum:+.2f}%  SPY {spy_cum:+.2f}%  excess {cum - spy_cum:+.2f}pp")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: record_close.py YYYY-MM-DD")
    main(sys.argv[1])
