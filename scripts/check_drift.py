#!/usr/bin/env python3
"""Drift check and rebalance proposal, run after the close.

Usage: python3 scripts/check_drift.py [YYYY-MM-DD]   (defaults to latest snapshot)

Flags a position when |drift| exceeds EITHER the relative band (25% of target)
OR the absolute band (3.0pp). Proposes a trade only when the required notional
clears MIN_TRADE ($75) — the drift-vs-churn guard from the IPS.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

REL_BAND = 25.0      # percent of target weight
ABS_BAND = 3.0       # percentage points
MIN_TRADE = 75.00    # dollars — below this, drift is noted but not traded
MAX_POS_MKT = 0.15   # forced-trim ceiling at market
STOP_ABS = -20.0     # percent from cost basis -> thesis review
STOP_REL = -15.0     # percent vs SPY since entry -> thesis review


def latest_date():
    files = sorted(glob.glob(os.path.join(lib.PRICES, "*.json")))
    if not files:
        sys.exit("no price snapshots in data/prices/")
    return os.path.basename(files[-1])[:-5]


def analyse(date):
    """Return (h, closes, nav, equity, detail, spy_cum, proposals, reviews)."""
    h = lib.load_holdings()
    closes = lib.load_prices(date)["closes"]
    equity, nav, detail = lib.valuation(h, closes)
    hist = lib.read_history()
    spy_cum = 0.0
    if hist:
        spy_cum = (float(closes["SPY"]) / float(hist[0]["spy_close"]) - 1) * 100

    proposals, reviews = [], []
    for sym, d in sorted(detail.items(), key=lambda kv: -kv[1]["weight"]):
        breached = abs(d["drift_rel"]) > REL_BAND or abs(d["drift_pp"]) > ABS_BAND
        over_cap = d["weight"] > MAX_POS_MKT
        vs_spy = d["unrealized_pct"] - spy_cum
        if d["unrealized_pct"] <= STOP_ABS:
            reviews.append((sym, f"{d['unrealized_pct']:.1f}% from cost"))
        if vs_spy <= STOP_REL:
            reviews.append((sym, f"{vs_spy:.1f}pp vs SPY"))
        if breached or over_cap:
            target_value = min(d["target_weight"], MAX_POS_MKT) * nav
            delta = target_value - d["value"]
            if abs(delta) >= MIN_TRADE:
                proposals.append({
                    "symbol": sym,
                    "side": "buy" if delta > 0 else "sell",
                    "shares": round(abs(delta) / d["price"], 6),
                    "price": d["price"],
                    "notional": round(abs(delta), 2),
                    "reason": "over-cap trim" if over_cap else
                              f"drift {d['drift_pp']:+.2f}pp / {d['drift_rel']:+.1f}%",
                })
    return h, closes, nav, equity, detail, spy_cum, proposals, reviews


def main(date):
    h, closes, nav, equity, detail, spy_cum, proposals, reviews = analyse(date)

    print(f"\n=== Drift check {date} ===")
    print(f"NAV ${nav:,.2f}   equity ${equity:,.2f}   cash ${h['cash']:,.2f} "
          f"({h['cash'] / nav * 100:.1f}%)\n")
    print(f"{'SYM':6}{'WEIGHT':>9}{'TARGET':>9}{'DRIFT_pp':>10}{'DRIFT_%':>9}"
          f"{'P/L%':>8}{'vsSPY':>8}  FLAG")

    flagged = {p["symbol"] for p in proposals}
    review_syms = {s for s, _ in reviews}
    for sym, d in sorted(detail.items(), key=lambda kv: -kv[1]["weight"]):
        breached = abs(d["drift_rel"]) > REL_BAND or abs(d["drift_pp"]) > ABS_BAND
        over_cap = d["weight"] > MAX_POS_MKT
        flags = []
        if over_cap:
            flags.append("OVER-CAP")
        elif breached:
            flags.append("DRIFT" if sym in flagged else "drift<floor")
        if sym in review_syms:
            flags.append("REVIEW")
        print(f"{sym:6}{d['weight'] * 100:>8.2f}%{d['target_weight'] * 100:>8.1f}%"
              f"{d['drift_pp']:>+10.2f}{d['drift_rel']:>+9.1f}"
              f"{d['unrealized_pct']:>+8.1f}"
              f"{d['unrealized_pct'] - spy_cum:>+8.1f}  {','.join(flags)}")

    print()
    if reviews:
        print("Thesis reviews required (IPS 4):")
        for sym, why in reviews:
            print(f"  - {sym}: {why}")
        print()

    if not proposals:
        print("No rebalance required - all positions inside bands, or drift below "
              f"the ${MIN_TRADE:.0f} churn floor.")
        return

    net = sum(p["notional"] if p["side"] == "buy" else -p["notional"] for p in proposals)
    print(f"Proposed trades ({len(proposals)}), net cash impact ${-net:,.2f}:")
    for p in proposals:
        print(f"  {p['side'].upper():4} {p['shares']:>10.6f} {p['symbol']:6} "
              f"@ ${p['price']:.2f} = ${p['notional']:,.2f}   ({p['reason']})")
    print(f"\nCash after: ${h['cash'] - net:,.2f}")
    if h["cash"] - net < 0:
        print("  WARNING: proposal overdraws cash - sells must settle first or "
              "buy sizes must be scaled down.")
    print("\nApply with: python3 scripts/apply_trades.py " + date)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else latest_date())
