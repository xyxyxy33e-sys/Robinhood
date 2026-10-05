#!/usr/bin/env python3
"""Execute a staged reconstitution at a given day's close.

Usage: python3 scripts/reconstitute.py YYYY-MM-DD

Reads portfolio/pending_reconstitution.json (written by screen.py --write or by
hand), sells every holding not in the target book, then resizes / buys to the
target weights at that date's closes. Sells settle before buys. Logs every leg
to trades.csv, archives the plan to portfolio/reconstitutions/<date>.json and
removes the pending file. Exempt from the 4-trades-per-5-sessions drift limit.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
from screen import PENDING

MIN_LEG = 1.00  # dollars; resizes smaller than this are skipped as noise


def main(date):
    if not os.path.exists(PENDING):
        sys.exit("no pending reconstitution")
    plan = json.load(open(PENDING))
    if plan["effective"] > date:
        sys.exit(f"plan is effective {plan['effective']}, not yet")
    meta = plan.get("meta", {})
    h = lib.load_holdings()
    closes = lib.load_prices(date)["closes"]
    targets = plan["targets"]
    missing = [s for s in targets if s not in closes]
    if missing:
        sys.exit(f"no close for target(s) {missing} in data/prices/{date}.json")

    equity, nav, detail = lib.valuation(h, closes)
    by_sym = {p["symbol"]: p for p in h["positions"]}
    legs = []
    for sym, d in detail.items():                       # exits and trims
        tgt = targets.get(sym, 0.0) * nav
        if d["value"] - tgt >= MIN_LEG:
            legs.append(("sell", sym, (d["value"] - tgt) / d["price"], d["price"],
                         "v2 reconstitution: exit" if sym not in targets else "v2 reconstitution: resize"))
    for sym, w in targets.items():                      # entries and top-ups
        cur = detail[sym]["value"] if sym in detail else 0.0
        if w * nav - cur >= MIN_LEG:
            legs.append(("buy", sym, (w * nav - cur) / float(closes[sym]), float(closes[sym]),
                         "v2 reconstitution: entry" if sym not in detail else "v2 reconstitution: resize"))

    rows, cash = [], h["cash"]
    for side, sym, sh, px, why in sorted(legs, key=lambda l: l[0] != "sell"):
        sh = round(sh, 6)
        notional = round(sh * px, 2)
        if side == "sell":
            p = by_sym[sym]
            p["shares"] = round(p["shares"] - sh, 6)
            cash += notional
        else:
            notional = min(notional, round(cash, 2))
            sh = round(notional / px, 6)
            if sym in by_sym:
                p = by_sym[sym]
                cost = p["cost_basis"] * p["shares"] + notional
                p["shares"] = round(p["shares"] + sh, 6)
                p["cost_basis"] = round(cost / p["shares"], 4)
            else:
                m = meta.get(sym, {})
                p = {"symbol": sym, "shares": sh, "cost_basis": px, "target_weight": 0,
                     "sector": m.get("sector", ""), "thesis": m.get("thesis", "")}
                h["positions"].append(p)
                by_sym[sym] = p
            cash -= notional
        rows.append({"date": date, "symbol": sym, "side": side, "shares": f"{sh:.6f}",
                     "price": f"{px:.4f}", "notional": f"{notional:.2f}", "reason": why})

    h["positions"] = [p for p in h["positions"] if p["shares"] > 1e-6]
    for p in h["positions"]:
        p["target_weight"] = targets.get(p["symbol"], 0.0)
        if p["symbol"] in meta:
            p["sector"] = meta[p["symbol"]].get("sector", p.get("sector", ""))
            p["thesis"] = meta[p["symbol"]].get("thesis", p.get("thesis", ""))
    h["positions"].sort(key=lambda p: -p["target_weight"])
    h["cash"] = round(cash, 2)
    for k, v in plan.get("holdings_update", {}).items():
        h[k] = v

    lib.save_holdings(h)
    lib.append_trades(rows)
    plan["executed"] = {"date": date, "nav": round(nav, 2), "trades": rows}
    os.makedirs(os.path.join(lib.ROOT, "portfolio", "reconstitutions"), exist_ok=True)
    json.dump(plan, open(os.path.join(lib.ROOT, "portfolio", "reconstitutions", f"{date}.json"), "w"), indent=2)
    os.remove(PENDING)

    sells = sum(float(r["notional"]) for r in rows if r["side"] == "sell")
    buys = sum(float(r["notional"]) for r in rows if r["side"] == "buy")
    print(f"Reconstituted at {date} close: NAV ${nav:,.2f}, {len(rows)} legs, "
          f"sold ${sells:,.2f}, bought ${buys:,.2f}, cash now ${h['cash']:,.2f}")
    for r in rows:
        print(f"  {r['side'].upper():4} {float(r['shares']):>11.6f} {r['symbol']:5} @ {float(r['price']):>9.2f} "
              f"= ${float(r['notional']):>9,.2f}  {r['reason']}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: reconstitute.py YYYY-MM-DD")
    main(sys.argv[1])
