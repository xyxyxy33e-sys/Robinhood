#!/usr/bin/env python3
"""Monthly momentum screen for the v2 (aggressive) book.

Usage: python3 scripts/screen.py data/screens/YYYY-MM-DD.json [--write EFFECTIVE_DATE]

Rules (portfolio/strategy.md §v2):
  1. Excess return vs SPY over 12m, 6m, 3m, 1m (from month-open prices).
  2. Eligible only if 12m excess > 0 AND 6m excess > 0 (dual momentum)
     AND close within 15% of the 12-month high (trend intact).
  3. Rank eligible names by blend = .20*x12 + .35*x6 + .30*x3 + .15*x1.
  4. Book = top 8. A name already in the book stays if it is still eligible
     and ranks in the top 12 (turnover buffer).
  5. Equal weight across the book, 2% cash.
--write stages portfolio/pending_reconstitution.json for the next check-in.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

N_BOOK, N_BUFFER, TREND_LIMIT, CASH = 8, 12, -15.0, 0.02
BLEND = (0.20, 0.35, 0.30, 0.15)
PENDING = os.path.join(lib.ROOT, "portfolio", "pending_reconstitution.json")


def rank(path):
    d = json.load(open(path))
    u = d["universe"]
    spy = u.pop("SPY")
    spy_r = [(spy["close"] / o - 1) * 100 for o in spy["opens"]]
    rows = []
    for sym, v in u.items():
        x = [(v["close"] / o - 1) * 100 - spy_r[i] for i, o in enumerate(v["opens"])]
        blend = sum(w * xi for w, xi in zip(BLEND, x))
        vs_hi = (v["close"] / v["hi12"] - 1) * 100
        why = []
        if x[0] <= 0: why.append("12m<SPY")
        if x[1] <= 0: why.append("6m<SPY")
        if vs_hi < TREND_LIMIT: why.append(f"{vs_hi:.0f}% off high")
        rows.append({"symbol": sym, "x": x, "blend": blend, "vs_hi": vs_hi,
                     "eligible": not why, "why": ", ".join(why)})
    rows.sort(key=lambda r: -r["blend"])
    return d["asof"], rows


def select(rows, held):
    elig = [r for r in rows if r["eligible"]]
    book = [r["symbol"] for r in elig[:N_BOOK]]
    for r in elig[N_BOOK:N_BUFFER]:
        if r["symbol"] in held and r["symbol"] not in book:
            book.append(r["symbol"])
    return book


def main():
    path = sys.argv[1]
    asof, rows = rank(path)
    held = set()
    if os.path.exists(lib.HOLDINGS):
        h = lib.load_holdings()
        if h.get("strategy_version") == 2:
            held = {p["symbol"] for p in h["positions"]}
    book = select(rows, held)
    w = round((1 - CASH) / len(book), 4)

    print(f"Screen as of {asof}  (eligible = 12m & 6m excess > 0, within {-TREND_LIMIT:.0f}% of 12m high)\n")
    print(f"{'#':>3} {'SYM':6}{'x12':>8}{'x6':>8}{'x3':>8}{'x1':>8}{'BLEND':>8}{'vsHi':>7}  STATUS")
    for i, r in enumerate(rows, 1):
        st = "BOOK" if r["symbol"] in book else ("eligible" if r["eligible"] else "out: " + r["why"])
        print(f"{i:>3} {r['symbol']:6}" + "".join(f"{v:+8.1f}" for v in r["x"])
              + f"{r['blend']:+8.1f}{r['vs_hi']:+7.1f}  {st}")
    print(f"\nBook ({len(book)} names, {w*100:.2f}% each, {CASH*100:.0f}% cash): {', '.join(book)}")

    if "--write" in sys.argv:
        eff = sys.argv[sys.argv.index("--write") + 1]
        json.dump({"effective": eff, "screen": os.path.relpath(path, lib.ROOT),
                   "cash_target": CASH, "targets": {s: w for s in book}},
                  open(PENDING, "w"), indent=2)
        print(f"Staged {os.path.relpath(PENDING, lib.ROOT)} — executes at the {eff} close.")


if __name__ == "__main__":
    main()
