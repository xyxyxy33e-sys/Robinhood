"""
Shadow paper portfolios ($10,000 each, fractional shares, monthly rebalance) run
alongside the barbell so real out-of-sample evidence accumulates from today:

  buyback : top-30 buyback-yield names (rank blend of latest-quarter and TTM,
            point-in-time SEC EDGAR data) with positive 12-month momentum
  spy     : SPY buy & hold
  ew      : equal-weight all current S&P 500 members

Reuses the barbell paper-trail engine (paper_trail.py) with per-strategy
state/ledger files: shadow_<name>.json / shadow_<name>_ledger.csv.
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import paper_trail as PT  # noqa: E402
import buyback_signal as BS  # noqa: E402
import data_refresh  # noqa: E402
from backtest import load_data  # noqa: E402
import json  # noqa: E402

NAMES = ["buyback", "spy", "ew"]


def _last_complete(close):
    cov = close.notna().sum(axis=1)
    return cov[cov > 0.95 * close.shape[1]].index.max()


def target_buyback(n=30):
    close, *_ = load_data()
    members = [t for t in json.load(open(data_refresh.UNIVERSE)) if t in close.columns]
    close = close[members]
    dt = _last_complete(close)
    q0, q1, q2, q3, cap = BS.panels(close, [dt])
    sc = BS.scores(q0, q1, q2, q3, cap)
    mom = close.pct_change(252).loc[dt].reindex(sc["blend"].columns)
    s = sc["blend"].loc[dt].where(mom > 0).dropna().sort_values(ascending=False)
    return dt, list(s.head(n).index)


def target_spy():
    close, *_ = load_data()
    return _last_complete(close), ["SPY"]


def target_ew():
    close, *_ = load_data()
    members = [t for t in json.load(open(data_refresh.UNIVERSE)) if t in close.columns]
    return _last_complete(close[members]), members


TARGETS = {"buyback": target_buyback, "spy": target_spy, "ew": target_ew}


def run(name, cmd):
    PT.STATE_PATH = HERE / f"shadow_{name}.json"
    PT.LEDGER_PATH = HERE / f"shadow_{name}_ledger.csv"
    PT.target_list = TARGETS[name]
    print(f"\n===== shadow: {name} ({cmd}) =====")
    {"init": PT.do_init, "rebalance": PT.do_rebalance,
     "status": lambda: PT.do_status(False), "mark": lambda: PT.do_status(True)}[cmd]()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    for n in (sys.argv[2:] or NAMES):
        run(n, cmd)
