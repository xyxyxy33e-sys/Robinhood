#!/usr/bin/env python3
"""Does the momentum premise work at a MULTI-DAY horizon?

Written 2026-08-28 after the intraday 5-minute version was falsified: the
§1.3 leg rule could not fire (guard/seq contradiction) and, unblocked, was
worth +0.01% at 60 minutes against a ~0.9% option break-even.

The premise being retested is the same one, moved to daily bars:
  a large directional day, closing beyond its open, in the upper (lower)
  part of its own range, not fading the prior close.
That is the intraday "base tape" with the day as the bar.

THE CONFOUND THIS FILE ORIGINALLY HANDLED: this universe is tech- and
crypto-heavy over a rising two-year sample, so every signal return is
reported against an unconditional baseline. Only EXCESS is evidence.

*** THAT BASELINE WAS STILL WRONG. CORRECTED 2026-08-28. ***
Comparing a signal day's forward return to the average of ALL days does
not isolate stock selection, because signal days CLUSTER on market-wide
selloffs and the whole universe bounces the next day. The original
reading measured "the market rises after it falls", not "these names
beat other names". Two errors compounded:

  (1) 2,127 signal legs sit in only 430 distinct trading days (~4.95 per
      day). Pooling them as independent inflates t by roughly 2.2x.
  (2) The counterfactual must be what OTHER STOCKS DID THE SAME DAY, not
      the all-period average.

Decomposition of the original claim (next-day close-to-close):

  pooled legs vs all-day baseline .............. +0.289%  t=+5.01
  one obs per day, same baseline ............... +0.101%  t=+1.69
  one obs per day vs the SAME DAY's universe ... +0.037%  t=+0.34

The effect does not survive. Anything reported from this file must use
the day-clustered, same-day-benchmarked number as the headline.

Data: data/daily/SYM.csv (d,o,h,l,c,v) from get_equity_historicals(interval='day').
"""
import csv, glob, os, statistics as st

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'daily')
HORIZONS = (1, 3, 5, 10, 21)
OPTION_BREAKEVEN = 0.9   # % underlying move needed to clear a 7% round-trip


def load(p):
    return [{'d': r['d'], **{k: float(r[k]) for k in 'ohlcv'}}
            for r in csv.DictReader(open(p))]


def signals(bars, min_chg=2.0):
    """Yield (index, direction). Daily analog of the intraday base tape."""
    for i in range(1, len(bars) - 1):
        b, prev = bars[i], bars[i - 1]
        chg = (b['c'] / prev['c'] - 1) * 100
        if abs(chg) < min_chg:
            continue
        mid = (b['h'] + b['l']) / 2
        if chg > 0 and b['c'] > b['o'] and b['c'] > mid:
            yield i, 'long'
        elif chg < 0 and b['c'] < b['o'] and b['c'] < mid:
            yield i, 'short'


def fwd(bars, i, n, direction):
    j = min(i + n, len(bars) - 1)
    r = (bars[j]['c'] / bars[i]['c'] - 1) * 100
    return r if direction == 'long' else -r


def tstat(xs):
    if len(xs) < 2:
        return 0.0
    sd = st.stdev(xs)
    return st.mean(xs) / (sd / len(xs) ** .5) if sd else 0.0


if __name__ == '__main__':
    files = sorted(glob.glob(os.path.join(D, '*.csv')))
    sig = {d: {'long': [], 'short': []} for d in HORIZONS}
    base = {d: {'long': [], 'short': []} for d in HORIZONS}
    n_days = 0

    for p in files:
        bars = load(p)
        n_days += len(bars)
        idx = list(signals(bars))
        for n in HORIZONS:
            # unconditional: every day in the same series, both directions
            for i in range(1, len(bars) - 1):
                base[n]['long'].append(fwd(bars, i, n, 'long'))
                base[n]['short'].append(fwd(bars, i, n, 'short'))
            for i, direction in idx:
                sig[n][direction].append(fwd(bars, i, n, direction))

    print(f"universe {len(files)} symbols, {n_days} name-days, "
          f"{len(list(signals(load(files[0]))))} signals in the first symbol\n")
    print(f"{'horizon':>8} {'side':>6} {'n':>6} {'signal':>9} {'uncond':>9} "
          f"{'EXCESS':>9} {'t(sig)':>7} {'>0.9%':>7}")
    for n in HORIZONS:
        for side in ('long', 'short'):
            s, b = sig[n][side], base[n][side]
            if not s:
                continue
            ex = st.mean(s) - st.mean(b)
            hit = sum(1 for x in s if x > OPTION_BREAKEVEN) / len(s) * 100
            print(f"{n:>6}d {side:>7} {len(s):>6} {st.mean(s):>+8.2f}% "
                  f"{st.mean(b):>+8.2f}% {ex:>+8.2f}% {tstat(s):>7.2f} {hit:>6.0f}%")

    print("\nEXCESS is the column that matters. `signal` alone measures the "
          "universe's drift.\n`t(sig)` is on the raw signal, and daily "
          "observations overlap at every horizon\nbeyond 1 day, so it is "
          "optimistic. `>0.9%` is the share of signals that clear an\noption's "
          "round-trip spread at all.")
