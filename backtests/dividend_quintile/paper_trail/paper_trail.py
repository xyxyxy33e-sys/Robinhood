"""
Self-contained paper-trading ledger for the 30-stock dividend-yield barbell
strategy (see ../BARBELL_30.md).

This does NOT touch any real or connected brokerage account. It's a local
simulation: buys/sells are recorded against live market prices pulled from
Yahoo Finance, cash and share counts are tracked in state.json, and every
init/rebalance/mark-to-market is appended to ledger.csv for a full history.
Fractional shares are allowed, so equal-weighting is exact every time --
no whole-share rounding/skipping.

Usage:
  python3 paper_trail.py init                 # one-time: buy the barbell with $10,000
  python3 paper_trail.py rebalance             # rebalance to the current 30-name list
  python3 paper_trail.py mark                  # mark-to-market only, no trades (for daily/weekly check-ins)
  python3 paper_trail.py status                # print current holdings + P&L

Rebalance logic: sell everything not in the new target list, then equal-weight
the new target list exactly (fractional shares) against total account value
(cash + prior holdings' value).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from barbell_30 import build_current_portfolio  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE_PATH = HERE / "state.json"
LEDGER_PATH = HERE / "ledger.csv"
STARTING_CASH = 10_000.0


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"cash": STARTING_CASH, "shares": {}, "inception_date": None, "last_rebalance": None}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


def append_ledger(rows):
    if not rows:
        return
    df = pd.DataFrame(rows)
    if LEDGER_PATH.exists():
        df.to_csv(LEDGER_PATH, mode="a", header=False, index=False)
    else:
        df.to_csv(LEDGER_PATH, index=False)


def get_live_prices(tickers):
    data = yf.download(tickers, period="5d", auto_adjust=False, progress=False, threads=True)
    last_close = data["Close"].ffill().iloc[-1]
    asof = data["Close"].ffill().index[-1]
    return last_close.to_dict(), asof


def target_list():
    dt, hy_leg, growth_leg = build_current_portfolio()
    tickers = list(hy_leg.index) + list(growth_leg.index)
    return dt, tickers


def portfolio_value(state, prices):
    equity = sum(state["shares"].get(t, 0) * prices.get(t, 0.0) for t in state["shares"])
    return state["cash"] + equity


def do_init():
    if STATE_PATH.exists():
        print("Paper trail already initialized. Use 'rebalance' or 'status' instead, "
              "or delete state.json/ledger.csv first if you really want to restart.")
        return
    signal_dt, tickers = target_list()
    prices, price_asof = get_live_prices(tickers)

    target_per_name = STARTING_CASH / len(tickers)
    shares = {}
    cash = STARTING_CASH
    rows = []
    for t in tickers:
        px = prices.get(t)
        if px is None or pd.isna(px) or px <= 0:
            print(f"WARNING: no price for {t}, skipping")
            continue
        qty = target_per_name / px
        cost = qty * px
        shares[t] = qty
        cash -= cost
        rows.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "BUY", "ticker": t, "shares": round(qty, 6), "price": round(px, 4),
            "notional": round(cost, 2), "cash_after": round(cash, 2),
            "signal_asof": str(signal_dt.date()), "price_asof": str(price_asof.date()),
        })

    state = {
        "cash": round(cash, 2),
        "shares": shares,
        "inception_date": datetime.now(timezone.utc).date().isoformat(),
        "last_rebalance": datetime.now(timezone.utc).date().isoformat(),
        "starting_value": STARTING_CASH,
    }
    save_state(state)
    append_ledger(rows)

    total = portfolio_value(state, prices)
    print(f"Initialized paper trail with ${STARTING_CASH:,.2f} as of {price_asof.date()}")
    print(f"Bought {len(shares)} of {len(tickers)} target names, equal-weighted (fractional shares)")
    print(f"Ending cash: ${cash:,.2f}   Total account value: ${total:,.2f}")


def do_rebalance():
    state = load_state()
    if not state.get("inception_date"):
        print("Not initialized yet. Run 'init' first.")
        return

    signal_dt, tickers = target_list()
    all_relevant = sorted(set(tickers) | set(state["shares"].keys()))
    prices, price_asof = get_live_prices(all_relevant)

    pre_value = portfolio_value(state, prices)

    rows = []
    # sell everything not in the new target list
    for t in list(state["shares"].keys()):
        if t not in tickers and state["shares"][t] > 0:
            px = prices.get(t)
            if px is None or pd.isna(px):
                print(f"WARNING: no price for {t} to sell, holding over")
                continue
            qty = state["shares"][t]
            proceeds = qty * px
            state["cash"] += proceeds
            state["shares"][t] = 0
            rows.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "SELL", "ticker": t, "shares": round(qty, 6), "price": round(px, 4),
                "notional": round(proceeds, 2), "cash_after": round(state["cash"], 2),
                "signal_asof": str(signal_dt.date()), "price_asof": str(price_asof.date()),
            })

    # equal-weight the new target list exactly (fractional shares) against
    # total account value
    total_value = portfolio_value(state, prices)
    target_per_name = total_value / len(tickers)

    for t in tickers:
        px = prices.get(t)
        if px is None or pd.isna(px) or px <= 0:
            print(f"WARNING: no price for {t}, skipping")
            continue
        cur_qty = state["shares"].get(t, 0.0)
        target_qty = target_per_name / px
        delta = target_qty - cur_qty
        if abs(delta) < 1e-9:
            continue
        notional = delta * px
        state["cash"] -= notional
        state["shares"][t] = target_qty
        rows.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "BUY" if delta > 0 else "SELL", "ticker": t, "shares": round(delta, 6),
            "price": round(px, 4), "notional": round(notional, 2), "cash_after": round(state["cash"], 2),
            "signal_asof": str(signal_dt.date()), "price_asof": str(price_asof.date()),
        })

    state["shares"] = {t: q for t, q in state["shares"].items() if q > 1e-9}
    state["last_rebalance"] = datetime.now(timezone.utc).date().isoformat()
    save_state(state)
    append_ledger(rows)

    post_value = portfolio_value(state, prices)
    print(f"Rebalanced as of {price_asof.date()} (signal as of {signal_dt.date()})")
    print(f"Value before rebalance: ${pre_value:,.2f}   after: ${post_value:,.2f}")
    print(f"Now holding {len(state['shares'])} names, cash: ${state['cash']:,.2f}")


def do_status(mark_only=False):
    state = load_state()
    if not state.get("inception_date"):
        print("Not initialized yet. Run 'init' first.")
        return
    tickers = list(state["shares"].keys())
    prices, price_asof = get_live_prices(tickers) if tickers else ({}, None)
    total = portfolio_value(state, prices)
    ret = total / state["starting_value"] - 1

    print(f"Paper Trail -- inception {state['inception_date']}, last rebalance {state['last_rebalance']}")
    print(f"As of {price_asof.date() if price_asof is not None else 'n/a'}")
    print(f"Cash: ${state['cash']:,.2f}")
    print(f"{'Ticker':8s}{'Shares':>10s}{'Price':>12s}{'Value':>14s}{'Weight':>9s}")
    for t in sorted(tickers):
        px = prices.get(t, float("nan"))
        val = state["shares"][t] * px
        w = val / total * 100 if total else 0
        print(f"{t:8s}{state['shares'][t]:10.3f}{px:12.2f}{val:14,.2f}{w:8.1f}%")
    print(f"\nTotal account value: ${total:,.2f}   Return since inception: {ret*100:+.2f}%")

    if not mark_only:
        return
    append_ledger([{
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "MARK", "ticker": "", "shares": "", "price": "",
        "notional": "", "cash_after": state["cash"],
        "signal_asof": "", "price_asof": str(price_asof.date()) if price_asof is not None else "",
        "total_value": round(total, 2),
    }])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "init":
        do_init()
    elif cmd == "rebalance":
        do_rebalance()
    elif cmd == "mark":
        do_status(mark_only=True)
    elif cmd == "status":
        do_status(mark_only=False)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
