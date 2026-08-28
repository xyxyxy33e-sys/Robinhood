#!/usr/bin/env python3
"""Screen for the one-day reversal signal, and score a completed day.

The signal (from tools/swing_study.py, 15,600 name-days):
    yesterday's close <= -2% vs the prior close
    AND yesterday closed below its own open
    AND yesterday closed below its own mid-range (h+l)/2
Buy at TODAY's open, sell at TODAY's close. No overnight hold.

In-sample edge: +0.436% mean next-day return vs +0.149% unconditional,
i.e. +0.287% excess, t=+5.00; the excess sits in the regular session
(open->close +0.303%) not the overnight gap (+0.038%).

THIS IS A PORTFOLIO SIGNAL, NOT A STOCK PICK. Per-trade sd is 4.01%
against a +0.436% mean — roughly a 0.11 Sharpe per trade. A single name
is noise. Take EVERY qualifying name, equal-weighted, or take none.

Usage:
  python3 tools/reversal_screen.py screen <YYYY-MM-DD>
      list the names whose PRIOR session fired the signal (i.e. the basket
      to buy at that date's open), from data/daily/.
  python3 tools/reversal_screen.py score <YYYY-MM-DD>
      score that basket's open->close return for the named date.
"""
import csv, glob, os, statistics as st, sys

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'daily')
MIN_DROP = 2.0


def load(p):
    return [{'d': r['d'], **{k: float(r[k]) for k in 'ohlcv'}}
            for r in csv.DictReader(open(p))]


def fired(bars, i):
    """Did bar i fire the reversal signal?"""
    if i < 1:
        return False
    chg = (bars[i]['c'] / bars[i - 1]['c'] - 1) * 100
    mid = (bars[i]['h'] + bars[i]['l']) / 2
    return chg <= -MIN_DROP and bars[i]['c'] < bars[i]['o'] and bars[i]['c'] < mid


def basket(date):
    """Names to buy at `date`'s open, because their PRIOR session fired.

    `date` need NOT be present in the data. Pre-market on the morning of the
    trade there is no bar for that day yet, so the signal day is simply the
    last completed session on file. When `date` IS present (scoring a past
    day) the signal day is the bar immediately before it. Getting this wrong
    is how a pre-market screen silently returns an empty basket every day."""
    out = []
    for p in sorted(glob.glob(os.path.join(D, '*.csv'))):
        sym = os.path.basename(p)[:-4]
        bars = load(p)
        idx = {b['d']: k for k, b in enumerate(bars)}
        if date in idx:
            i = idx[date]              # scoring: signal day is i-1, trade bar is i
            sig, trade = i - 1, bars[i]
        elif date > bars[-1]['d']:
            sig, trade = len(bars) - 1, None   # screening ahead of the session
        else:
            continue                   # a gap in the series, not a future date
        if sig < 1 or not fired(bars, sig):
            continue
        drop = (bars[sig]['c'] / bars[sig - 1]['c'] - 1) * 100
        out.append((sym, bars[sig]['d'], drop, trade))
    return out


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); raise SystemExit(2)
    mode, date = sys.argv[1], sys.argv[2]
    b = basket(date)
    if not b:
        print(f"{date}: no qualifying names. A no-trade day is a valid outcome — "
              f"do not relax MIN_DROP to fill the basket.")
        raise SystemExit
    if mode == 'screen':
        print(f"{date}: buy at the open, equal-weighted, sell at the close\n")
        print(f"{'sym':6}{'signal day':>12}{'drop':>9}")
        for sym, sd, drop, _ in b:
            print(f"{sym:6}{sd:>12}{drop:>8.2f}%")
        print(f"\n{len(b)} names, {100.0 / len(b):.1f}% of the day's allocation each.")
    elif mode == 'score':
        if any(bar is None for *_, bar in b):
            print(f"{date} has not traded yet — nothing to score.")
            raise SystemExit(1)
        rs = [(sym, (bar['c'] / bar['o'] - 1) * 100) for sym, _, _, bar in b]
        for sym, r in sorted(rs, key=lambda x: -x[1]):
            print(f"  {sym:6}{r:+7.2f}%")
        m = st.mean(r for _, r in rs)
        print(f"\nbasket open->close: {m:+.3f}%  ({len(rs)} names, "
              f"{sum(1 for _, r in rs if r > 0)} positive)")
        print(f"in-sample expectation was +0.303% excess; one day proves nothing.")
    else:
        print(__doc__); raise SystemExit(2)
