"""
One-command monthly job for all paper portfolios.

  python3 monthly_run.py            # rebalance everything IF today is the first NYSE trading day of the month
  python3 monthly_run.py --force    # rebalance everything now
  python3 monthly_run.py mark       # log a mark-to-market row for every portfolio (weekly check-in)

Steps for a rebalance: refresh price cache -> refresh SEC EDGAR facts (rebuilds
from scratch if the cache is missing, ~20 min) -> barbell rebalance -> shadow rebalances.
Commit/push of state.json, ledger.csv and shadow_* files is left to the caller.
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def is_first_trading_day():
    today = datetime.now(timezone.utc).date()
    h = yf.download("SPY", start=today.replace(day=1).isoformat(), progress=False, auto_adjust=False)
    days = [d.date() for d in h.index]
    return bool(days) and days[0] == today


def sh(*args):
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True, cwd=HERE)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "mark":
        sh(sys.executable, "paper_trail.py", "mark")
        sh(sys.executable, "shadow_trail.py", "mark")
        return
    if mode != "--force" and not is_first_trading_day():
        print("Not the first trading day of the month - nothing to do.")
        return
    sh(sys.executable, str(ROOT / "data_refresh.py"))
    sh(sys.executable, str(ROOT / "buyback" / "fetch_edgar.py"))
    sh(sys.executable, "paper_trail.py", "rebalance")
    sh(sys.executable, "shadow_trail.py", "rebalance")
    sh(sys.executable, "paper_trail.py", "status")
    sh(sys.executable, "shadow_trail.py", "status")


if __name__ == "__main__":
    main()
