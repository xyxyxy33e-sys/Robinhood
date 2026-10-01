"""Live paper run: real-time SPY bars, real option expiries/IVs, simulated fills.

No orders are ever sent anywhere. Start any time before the open:

    python -m scalper.paper            # runs until 16:00 ET, logs to logs/
    python -m scalper.paper --contracts 2 --levels 760 772.5
"""
import argparse
from datetime import datetime, timedelta
import json
import os
import time as _time
from zoneinfo import ZoneInfo

from .config import Config
from .data import Chain, minute_bars
from .engine import Engine
from .levels import compute_levels

ET = ZoneInfo("America/New_York")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contracts", type=int, default=1)
    ap.add_argument("--levels", type=float, nargs="*", default=[], help="extra manual levels")
    ap.add_argument("--logdir", default="logs")
    a = ap.parse_args()

    cfg = Config(contracts=a.contracts, extra_levels=a.levels)
    os.makedirs(a.logdir, exist_ok=True)
    today = datetime.now(ET).date()
    logf = open(os.path.join(a.logdir, f"paper-{today}.log"), "a")

    def log(msg: str) -> None:
        line = f"{datetime.now(ET):%H:%M:%S}  {msg}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    if today.weekday() >= 5:
        log("market closed today (weekend)")
        return

    # Levels are fixed from pre-open data. Wait until 09:29 so premarket high/low is complete.
    open_at = datetime.combine(today, datetime.min.time(), ET).replace(hour=9, minute=29, second=30)
    while datetime.now(ET) < open_at:
        log(f"waiting for 09:29:30 ET to mark levels ({open_at - datetime.now(ET)} left)")
        _time.sleep(min(600, max(1, (open_at - datetime.now(ET)).total_seconds())))

    bars = minute_bars(cfg.symbol, period="7d")
    levels = compute_levels(bars, today, cfg)
    log("levels: " + ", ".join(map(str, levels)))

    chain = Chain(cfg.symbol)
    eng = Engine(cfg, levels, expiry_picker=chain.pick_expiry(cfg.afternoon_min_calendar_dte),
                 iv_lookup=chain.iv, log=log)
    seen = None
    n_logged = 0
    close_at = datetime.combine(today, datetime.min.time(), ET).replace(hour=16, minute=0, second=30)

    while True:
        now = datetime.now(ET)
        try:
            bars = minute_bars(cfg.symbol, period="1d")
        except Exception as e:  # network hiccup: try again next cycle
            log(f"data error: {e}")
            bars = None
        if bars is not None:
            minute = now.replace(second=0, microsecond=0)
            rth = bars[bars.index.date == today].between_time("09:30", "15:59")
            done = rth[rth.index < minute]  # only fully closed bars
            if seen is not None:
                done = done[done.index > seen]
            for ts, r in done.iterrows():
                eng.on_bar(ts, r.Open, r.High, r.Low, r.Close)
                seen = ts
            # Log the real market for each new fill so simulated prices can be compared later.
            for tr in eng.trades[n_logged:]:
                try:
                    q = chain.quote(tr.expiry, tr.strike, tr.right)
                    if q is not None:
                        log(f"   market {tr.strike:g}{tr.right}: bid {q['bid']} ask {q['ask']} last {q['lastPrice']} "
                            f"iv {q['impliedVolatility']:.3f}")
                except Exception as e:
                    log(f"   quote error: {e}")
            n_logged = len(eng.trades)

        if now >= close_at:
            if eng.open and bars is not None and not bars.empty:
                eng.force_flat(now, float(bars["Close"].iloc[-1]))
            break
        nxt = (now + timedelta(minutes=1)).replace(second=5, microsecond=0)
        _time.sleep(max(1.0, (nxt - datetime.now(ET)).total_seconds()))

    trades = [t.as_dict() for t in eng.trades]
    with open(os.path.join(a.logdir, f"paper-{today}.json"), "w") as f:
        json.dump(trades, f, indent=2)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    log(f"DONE  trades {len(trades)}  wins {wins}  net pnl ${eng.realized:+.2f}  {eng.halted}")


if __name__ == "__main__":
    main()
