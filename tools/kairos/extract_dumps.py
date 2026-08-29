#!/usr/bin/env python3
"""Convert raw mcp__robinhood__get_equity_historicals tool-result dumps into compact
per-symbol close-price CSVs under data/kairos/universe/.

The MCP tool persists large responses to JSON files rather than returning them inline.
This script sweeps that directory, extracts (date, close) for every symbol found, and
writes one CSV per symbol. Bars flagged `interpolated` are DROPPED -- the tool documents
them as synthesised gap-fill that "carry no new information", and for TQQQ they are
pre-inception padding (TQQQ's first real bar is 2010-02-11) which would otherwise
fabricate a flat price history back to 2009.

Idempotent: re-running merges new dumps into existing CSVs, keeping the latest value
for any duplicated date.
"""
import json
import os
import sys
import glob
import csv

DUMP_DIR = "/root/.claude/projects/-home-user-Robinhood/95ab5d51-ca02-5343-b90e-149d7fffd134/tool-results"
OUT_DIR = "/home/user/Robinhood/data/kairos/universe"
ETF_DIR = "/home/user/Robinhood/data/kairos/etf"

# Instruments the backtest actually trades / benchmarks against. For these we keep
# OPEN as well as CLOSE, because the primary (lookahead-free) execution assumption is
# "decide on day t's close, fill at day t+1's OPEN", which needs the open price.
ETFS = {"TQQQ", "QQQ", "SPY", "XLU", "BIL"}


def load_existing(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        r = csv.reader(f)
        next(r, None)
        return {row[0]: row[1] for row in r if len(row) >= 2}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(ETF_DIR, exist_ok=True)
    dumps = sorted(glob.glob(os.path.join(DUMP_DIR, "mcp-robinhood-get_equity_historicals-*.txt")))
    per_symbol = {}
    etf_ohlc = {}
    n_interp = 0
    not_found = set()

    for d in dumps:
        try:
            with open(d) as f:
                blob = json.load(f)
        except Exception as e:
            print(f"  skip unparseable {os.path.basename(d)}: {e}", file=sys.stderr)
            continue
        data = blob.get("data", {})
        for nf in data.get("not_found", []) or []:
            not_found.add(nf)
        for res in data.get("results", []) or []:
            sym = res.get("symbol")
            if not sym or res.get("interval") != "day":
                continue
            acc = per_symbol.setdefault(sym, {})
            eacc = etf_ohlc.setdefault(sym, {}) if sym in ETFS else None
            for b in res.get("bars", []) or []:
                if b.get("interpolated"):
                    n_interp += 1
                    continue
                day = b["begins_at"][:10]
                acc[day] = b["close_price"]
                if eacc is not None:
                    eacc[day] = (b["open_price"], b["close_price"])

    for sym, series in sorted(per_symbol.items()):
        path = os.path.join(OUT_DIR, f"{sym}.csv")
        merged = load_existing(path)
        merged.update(series)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["d", "c"])
            for day in sorted(merged):
                w.writerow([day, merged[day]])

    for sym, series in sorted(etf_ohlc.items()):
        path = os.path.join(ETF_DIR, f"{sym}.csv")
        merged = {}
        if os.path.exists(path):
            with open(path) as f:
                r = csv.reader(f)
                next(r, None)
                merged = {row[0]: (row[1], row[2]) for row in r if len(row) >= 3}
        merged.update(series)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["d", "o", "c"])
            for day in sorted(merged):
                w.writerow([day, merged[day][0], merged[day][1]])
        print(f"  etf {sym}: {len(merged)} bars {min(merged)} .. {max(merged)}")

    print(f"dumps scanned      : {len(dumps)}")
    print(f"symbols written    : {len(per_symbol)}")
    print(f"interpolated bars dropped: {n_interp}")
    if not_found:
        print(f"not_found symbols  : {sorted(not_found)}")
    total = len(glob.glob(os.path.join(OUT_DIR, '*.csv')))
    print(f"total CSVs on disk : {total}")


if __name__ == "__main__":
    main()
