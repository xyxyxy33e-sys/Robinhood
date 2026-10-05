#!/usr/bin/env python3
"""v3 daily signal: short-term reversal, re-ranked at every close.

Usage: python3 scripts/daily_signal.py YYYY-MM-DD

1. Appends that day's closes (from data/prices/<date>.json) for the whole
   universe + SPY to data/daily/closes.csv (idempotent per date).
2. Scores each universe name by its average return over the last 4, 5, 6, 7
   and 8 sessions. Lowest = most oversold.
3. Book = 8 most oversold names, equal weight (12.25% each, 2% cash). A held
   name stays while it remains among the 12 most oversold (turnover buffer).
4. Stages portfolio/pending_reconstitution.json for reconstitute.py, which
   executes at the same close with a 5 bp/side cost charge.

Backtest and rationale: portfolio/strategy.md section v3, scripts/backtest.py.
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

N_BOOK, N_BUFFER, LOOKBACKS, CASH = 8, 12, (4, 5, 6, 7, 8), 0.02
CLOSES = os.path.join(lib.ROOT, "data", "daily", "closes.csv")
UNIVERSE = os.path.join(lib.ROOT, "data", "universe.json")
PENDING = os.path.join(lib.ROOT, "portfolio", "pending_reconstitution.json")


def load():
    rows = list(csv.reader(open(CLOSES)))
    return rows[0], rows[1:]


def append_close(date):
    hdr, rows = load()
    snap = lib.load_prices(date)["closes"]
    missing = [s for s in hdr[1:] if s not in snap]
    if missing:
        sys.exit(f"snapshot {date} is missing universe symbols: {missing}")
    rows = [r for r in rows if r[0] != date] + [[date] + [str(snap[s]) for s in hdr[1:]]]
    rows.sort(key=lambda r: r[0])
    with open(CLOSES, "w", newline="") as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(rows)
    return hdr, rows


def rank(hdr, rows, date):
    t = [r[0] for r in rows].index(date)
    if t < max(LOOKBACKS):
        sys.exit("not enough history")
    uni = json.load(open(UNIVERSE))["symbols"]
    col = {s: i + 1 for i, s in enumerate(hdr[1:])}
    px = lambda k, s: float(rows[t - k][col[s]])
    out = []
    for s in uni:
        rets = [(px(0, s) / px(k, s) - 1) * 100 for k in LOOKBACKS]
        out.append({"symbol": s, "score": sum(rets) / len(rets), "r5": rets[1], "sector": uni[s]})
    out.sort(key=lambda r: r["score"])          # most oversold first
    return out


def main(date):
    hdr, rows = append_close(date)
    ranked = rank(hdr, rows, date)
    held = {p["symbol"] for p in lib.load_holdings()["positions"]}
    pos = {r["symbol"]: i + 1 for i, r in enumerate(ranked)}
    keep = [s for s in sorted(held, key=lambda s: pos.get(s, 99)) if pos.get(s, 99) <= N_BUFFER][:N_BOOK]
    book = keep + [r["symbol"] for r in ranked if r["symbol"] not in keep][:N_BOOK - len(keep)]
    w = round((1 - CASH) / N_BOOK, 4)

    print(f"Reversal ranking at {date} close (avg return over {LOOKBACKS} sessions):")
    for i, r in enumerate(ranked[:14], 1):
        tag = ("HOLD" if r["symbol"] in held else "BUY ") if r["symbol"] in book else ""
        print(f"  {i:>2} {r['symbol']:5} {r['score']:+7.2f}%  5d {r['r5']:+6.1f}%  {tag}")
    exits = sorted(held - set(book))
    print(f"\nBook: {', '.join(book)}\nExits: {', '.join(exits) or 'none'}")

    meta = {r["symbol"]: {"sector": r["sector"],
            "thesis": f"Reversal pick {date}: rank {pos[r['symbol']]} of {len(ranked)}, "
                      f"avg {r['score']:+.1f}% over 4-8 sessions. Held while in the 12 most oversold."}
            for r in ranked if r["symbol"] in book and r["symbol"] not in held}
    json.dump({"effective": date, "strategy": "v3 daily reversal", "cash_target": CASH,
               "min_leg": 50.0, "cost_bps": 5.0, "targets": {s: w for s in book}, "meta": meta,
               "ranking": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in ranked]},
              open(PENDING, "w"), indent=2)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: daily_signal.py YYYY-MM-DD")
    main(sys.argv[1])
