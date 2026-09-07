"""Shared state handling for the Model Alpha-12 paper portfolio."""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLDINGS = os.path.join(ROOT, "portfolio", "holdings.json")
HISTORY = os.path.join(ROOT, "portfolio", "history.csv")
TRADES = os.path.join(ROOT, "portfolio", "trades.csv")
PRICES = os.path.join(ROOT, "data", "prices")

HISTORY_FIELDS = [
    "date", "nav", "cash", "equity", "day_return_pct", "cum_return_pct",
    "spy_close", "spy_cum_return_pct", "excess_return_pct", "holdings_json",
]
TRADE_FIELDS = ["date", "symbol", "side", "shares", "price", "notional", "reason"]


def load_holdings():
    with open(HOLDINGS) as f:
        return json.load(f)


def save_holdings(h):
    with open(HOLDINGS, "w") as f:
        json.dump(h, f, indent=2)
        f.write("\n")


def load_prices(date):
    """Load a daily close snapshot: {"date":..., "closes": {"SPY": 770.23, ...}}"""
    path = os.path.join(PRICES, f"{date}.json")
    with open(path) as f:
        return json.load(f)


def save_prices(date, closes, source="robinhood-mcp"):
    os.makedirs(PRICES, exist_ok=True)
    path = os.path.join(PRICES, f"{date}.json")
    with open(path, "w") as f:
        json.dump({"date": date, "source": source, "closes": closes}, f, indent=2)
        f.write("\n")
    return path


def read_history():
    if not os.path.exists(HISTORY):
        return []
    with open(HISTORY) as f:
        return list(csv.DictReader(f))


def append_history(row):
    """Append a row, replacing any existing row for the same date (idempotent re-runs)."""
    rows = [r for r in read_history() if r["date"] != row["date"]]
    rows.append(row)
    rows.sort(key=lambda r: r["date"])
    with open(HISTORY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        w.writeheader()
        w.writerows(rows)


def read_trades():
    if not os.path.exists(TRADES):
        return []
    with open(TRADES) as f:
        return list(csv.DictReader(f))


def append_trades(new_rows):
    rows = read_trades() + new_rows
    with open(TRADES, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDS)
        w.writeheader()
        w.writerows(rows)


def valuation(holdings, closes):
    """Return (equity, nav, {symbol: {shares, price, value, weight, ...}})."""
    detail, equity = {}, 0.0
    for p in holdings["positions"]:
        sym = p["symbol"]
        if sym not in closes:
            raise KeyError(f"no close price for held position {sym}")
        price = float(closes[sym])
        value = p["shares"] * price
        equity += value
        detail[sym] = {
            "shares": p["shares"], "price": price, "value": value,
            "cost_basis": p["cost_basis"], "target_weight": p["target_weight"],
            "sector": p.get("sector", ""),
            "unrealized_pct": (price / p["cost_basis"] - 1) * 100,
        }
    nav = equity + holdings["cash"]
    for d in detail.values():
        d["weight"] = d["value"] / nav
        d["drift_pp"] = (d["weight"] - d["target_weight"]) * 100
        d["drift_rel"] = ((d["weight"] - d["target_weight"]) / d["target_weight"]) * 100
    return equity, nav, detail
