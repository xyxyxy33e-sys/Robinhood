#!/usr/bin/env python3
"""Merge persisted get_equity_historicals daily dumps into data/sp500_daily/SYM.csv.

Unlike tools/parse_historicals_dump.py (which WROTE whole files for the initial
1-year pull), this MERGES: it reads the existing CSV, unions in any new dates
from the dumps, and rewrites sorted with no duplicate dates. Existing rows win
on a date collision, so a backfill can never silently rewrite already-audited
history. Interpolated bars (server-synthesized gap fillers) are dropped.

Usage: python3 tools/merge_historicals_backfill.py <dump-file-glob> [more globs]
"""
import glob, json, os, sys, csv

OUT = "/home/user/Robinhood/data/sp500_daily"


def read_existing(sym):
    p = os.path.join(OUT, f"{sym}.csv")
    if not os.path.exists(p):
        return {}
    return {r['d']: [r['d'], r['o'], r['h'], r['l'], r['c'], r['v']]
            for r in csv.DictReader(open(p)) if r.get('d')}


def main():
    pats = sys.argv[1:]
    files = sorted({f for p in pats for f in glob.glob(p)})
    interp = 0
    added = {}
    for f in files:
        try:
            j = json.load(open(f))
        except Exception as e:
            print(f"SKIP {f}: {e}"); continue
        for res in (j.get("data") or {}).get("results") or []:
            if res.get("interval") != "day":
                continue
            sym = res.get("symbol")
            cur = read_existing(sym)
            n0 = len(cur)
            for b in res.get("bars") or []:
                if b.get("interpolated"):
                    interp += 1; continue
                d = b["begins_at"][:10]
                if d in cur:
                    continue                      # existing rows win
                cur[d] = [d, b["open_price"], b["high_price"],
                          b["low_price"], b["close_price"], b["volume"]]
            if not cur:
                continue
            with open(os.path.join(OUT, f"{sym}.csv"), "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["d", "o", "h", "l", "c", "v"])
                for d in sorted(cur):
                    w.writerow(cur[d])
            added[sym] = added.get(sym, 0) + (len(cur) - n0)
    tot = sum(added.values())
    print(f"dumps={len(files)} symbols_touched={len(added)} rows_added={tot} interpolated_dropped={interp}")
    zero = [s for s, n in added.items() if n == 0]
    if zero:
        print(f"no new rows for {len(zero)}: {' '.join(sorted(zero))}")


if __name__ == "__main__":
    main()
