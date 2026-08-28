#!/usr/bin/env python3
"""Convert persisted get_equity_historicals tool-result JSON dumps into
data/sp500_daily/SYM.csv with header d,o,h,l,c,v.

Interpolated bars (server-synthesized gap fillers, volume 0) are DROPPED — they
carry no information and would otherwise inject fake 0% return days.
"""
import glob, json, os, sys, csv

DUMP_DIR = "/root/.claude/projects/-home-user-Robinhood/95ab5d51-ca02-5343-b90e-149d7fffd134/tool-results"
OUT = "/home/user/Robinhood/data/sp500_daily"

def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(DUMP_DIR, "mcp-robinhood-get_equity_historicals-*.txt")))
    wrote, empty, interp = [], [], 0
    for f in files:
        try:
            j = json.load(open(f))
        except Exception as e:
            print(f"SKIP {f}: {e}"); continue
        for res in (j.get("data") or {}).get("results") or []:
            sym = res.get("symbol")
            if res.get("interval") != "day":
                continue          # older dumps in this dir are intraday; ignore them
            bars = res.get("bars") or []
            rows = []
            for b in bars:
                if b.get("interpolated"):
                    interp += 1; continue
                rows.append([b["begins_at"][:10], b["open_price"], b["high_price"],
                             b["low_price"], b["close_price"], b["volume"]])
            rows = [r for r in rows if r[0] >= "2025-07-01"]
            if len(rows) < 200:
                empty.append(sym); continue
            rows.sort(key=lambda r: r[0])
            # de-dupe by date, last wins
            ded = {}
            for r in rows: ded[r[0]] = r
            rows = [ded[k] for k in sorted(ded)]
            dst = os.path.join(OUT, f"{sym}.csv")
            if os.path.exists(dst) and sum(1 for _ in open(dst)) - 1 > len(rows):
                wrote.append(sym); continue   # keep the longer existing series
            with open(os.path.join(OUT, f"{sym}.csv"), "w", newline="") as fh:
                w = csv.writer(fh); w.writerow(["d","o","h","l","c","v"]); w.writerows(rows)
            wrote.append(sym)
    print(f"files={len(files)} symbols_written={len(wrote)} empty={len(empty)} interpolated_dropped={interp}")
    if empty: print("EMPTY:", " ".join(sorted(set(empty))))

if __name__ == "__main__":
    main()
