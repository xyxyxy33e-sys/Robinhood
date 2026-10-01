"""Replay recent SPY 1-minute bars through the engine.

Option prices are simulated with Black-Scholes at a fixed IV (free 1-minute option
history is not available), so treat results as a sanity check of the rules,
not as an estimate of real fills.

    python -m scalper.backtest --days 5 --iv 0.16
"""
import argparse
import json

import pandas as pd

from .config import Config
from .data import minute_bars
from .engine import Engine
from .levels import compute_levels


def run_day(bars: pd.DataFrame, day, cfg: Config, verbose: bool = False) -> Engine:
    levels = compute_levels(bars, day, cfg)
    log = (lambda s: print("   ", s)) if verbose else (lambda s: None)
    eng = Engine(cfg, levels, log=log)
    rth = bars[bars.index.date == day].between_time("09:30", "15:59")
    for ts, r in rth.iterrows():
        eng.on_bar(ts, r.Open, r.High, r.Low, r.Close)
    if eng.open:
        last = rth.iloc[-1]
        eng.force_flat(rth.index[-1].to_pydatetime(), last.Close)
    return eng


def run(bars: pd.DataFrame, cfg: Config, days: int, verbose: bool = False) -> list[dict]:
    all_days = sorted(set(bars.between_time("09:30", "15:59").index.date))
    out = []
    for day in all_days[1:][-days:]:  # first day only seeds levels
        eng = run_day(bars, day, cfg, verbose)
        if verbose:
            print(f"{day}: levels {', '.join(map(str, eng.levels))}")
        out += [dict(t.as_dict(), day=str(day)) for t in eng.trades]
        pnl = eng.realized
        print(f"{day}  trades {len(eng.trades):2d}  pnl ${pnl:+9.2f}  {eng.halted}")
    return out


def summarize(trades: list[dict]) -> None:
    if not trades:
        print("no trades")
        return
    df = pd.DataFrame(trades)
    wins = (df.pnl > 0).sum()
    print(f"\ntrades {len(df)}  wins {wins}  losses {len(df) - wins}  win% {wins / len(df):.0%}")
    print(f"gross pnl ${df.pnl.sum():+.2f}  avg ${df.pnl.mean():+.2f}  "
          f"avg win ${df[df.pnl > 0].pnl.mean():+.2f}  avg loss ${df[df.pnl <= 0].pnl.mean():+.2f}")
    print(df.groupby("window").pnl.agg(["count", "sum", "mean"]).round(2))
    print(df.groupby("exit_reason").pnl.agg(["count", "sum", "mean"]).round(2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--iv", type=float, default=None)
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--out", default=None, help="write trades to this JSON file")
    a = ap.parse_args()
    cfg = Config()
    if a.iv:
        cfg.default_iv = a.iv
    bars = minute_bars(cfg.symbol, period="8d", interval=a.interval)
    trades = run(bars, cfg, a.days, a.verbose)
    summarize(trades)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(trades, f, indent=2)


if __name__ == "__main__":
    main()
