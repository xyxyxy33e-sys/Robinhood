#!/usr/bin/env python3
"""Apply the rebalance proposal from check_drift.py to the portfolio state.

Usage: python3 scripts/apply_trades.py YYYY-MM-DD [--yes]

Sells are applied before buys so cash never goes negative mid-run. Buys are
scaled down proportionally if cash is still insufficient. Updates
portfolio/holdings.json (shares, cash, weighted-average cost basis) and appends
to portfolio/trades.csv.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import check_drift


def main(date, assume_yes=False):
    h, closes, nav, equity, detail, spy_cum, proposals, reviews = check_drift.analyse(date)
    if not proposals:
        print("Nothing to apply — no proposals for", date)
        return

    sells = [p for p in proposals if p["side"] == "sell"]
    buys = [p for p in proposals if p["side"] == "buy"]

    cash = h["cash"] + sum(p["notional"] for p in sells)
    want = sum(p["notional"] for p in buys)
    scale = 1.0
    if want > cash:
        scale = cash / want if want else 0.0
        print(f"Scaling buys to {scale:.3f} of proposal — only ${cash:,.2f} available "
              f"against ${want:,.2f} requested.")

    print(f"\nApplying {len(proposals)} trade(s) for {date}:")
    for p in sells + buys:
        s = scale if p["side"] == "buy" else 1.0
        print(f"  {p['side'].upper():4} {p['shares'] * s:>10.6f} {p['symbol']:6} "
              f"@ ${p['price']:.2f} = ${p['notional'] * s:,.2f}")
    if not assume_yes:
        if input("\nProceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted — no state written.")
            return

    by_sym = {p["symbol"]: p for p in h["positions"]}
    rows = []
    for p in sells + buys:
        s = scale if p["side"] == "buy" else 1.0
        shares = round(p["shares"] * s, 6)
        notional = round(shares * p["price"], 2)
        if shares <= 0:
            continue
        pos = by_sym[p["symbol"]]
        if p["side"] == "sell":
            pos["shares"] = round(pos["shares"] - shares, 6)
            h["cash"] = round(h["cash"] + notional, 2)
            # cost basis per share is unchanged on a partial sale
        else:
            old_cost = pos["cost_basis"] * pos["shares"]
            pos["shares"] = round(pos["shares"] + shares, 6)
            pos["cost_basis"] = round((old_cost + notional) / pos["shares"], 4)
            h["cash"] = round(h["cash"] - notional, 2)
        rows.append({
            "date": date, "symbol": p["symbol"], "side": p["side"],
            "shares": f"{shares:.6f}", "price": f"{p['price']:.4f}",
            "notional": f"{notional:.2f}", "reason": p["reason"],
        })

    lib.save_holdings(h)
    lib.append_trades(rows)
    print(f"\nApplied. Cash now ${h['cash']:,.2f}. "
          f"Re-run record_close.py {date} to refresh history, then build_dashboard.py.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: apply_trades.py YYYY-MM-DD [--yes]")
    main(sys.argv[1], "--yes" in sys.argv)
