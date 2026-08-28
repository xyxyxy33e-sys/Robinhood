#!/usr/bin/env python3
"""Test structurally different entry hypotheses against data/bars/.

Written 2026-08-28 after the §1.3 rule was found to be unable to fire
(tools/backtest_legs.py --audit) and, when unblocked, to carry no edge.
The question this answers is not "what threshold?" but "is the leg rule
selecting for anything at all?".

Everything here is direction-adjusted: a positive number is a gain for the
trade as placed (calls up, puts down), on the UNDERLYING, before option costs.

READ THE SIGNIFICANCE CAVEAT. Forward-60-minute windows sampled every 5
minutes overlap by 11/12, so the naive t-statistic over all bars is badly
inflated. Every test is therefore reported twice: over all bars, and over
one non-overlapping observation per name-day, which is the honest n.
"""
import os, sys, statistics as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_legs as B
from eval_entry import evaluate_ohlcv


def sessions():
    for f, pc, direction in B.cases():
        yield f[:-4], B.load(os.path.join(B.D, f)), pc, direction


def ev(bars, i, pc, d, th=1.5):
    if i + 1 < 10:
        return None
    b = [(x['o'], x['h'], x['l'], x['c'], x['v']) for x in bars[:i + 1]]
    return evaluate_ohlcv(b, pc, d, B.cfg(th))


def ret(bars, i, direction, n):
    e = bars[i]['c']
    j = min(i + n, len(bars) - 1) if n else len(bars) - 1
    r = (bars[j]['c'] / e - 1) * 100
    return r if direction == 'call' else -r


def stat(name, xs, note=''):
    if len(xs) < 2:
        print(f"{name:44s} n={len(xs):3}   (too few)")
        return
    m = st.mean(xs); sd = st.stdev(xs); t = m / (sd / len(xs) ** .5)
    print(f"{name:44s} n={len(xs):4} mean={m:+6.2f}% sd={sd:5.2f} "
          f"t={t:+5.2f} win={sum(1 for x in xs if x > 0):3}/{len(xs)} {note}")


def collect():
    """All base-tape bars and all §1.3-qualifying bars, with per-name-day firsts."""
    base_all, leg_all = [], []
    base_first, leg_first = [], []
    for name, bars, pc, d in sessions():
        seen_base = seen_leg = False
        for i, x in enumerate(bars):
            if x['t'] < B.T_START or x['t'] > B.T_END or i >= len(bars) - 1:
                continue
            e = ev(bars, i, pc, d)
            if not e or not e['base']:
                continue
            r = ret(bars, i, d, 12)
            base_all.append(r)
            if not seen_base:
                base_first.append(r); seen_base = True
            if e['qualified']:
                leg_all.append((name, bars, i, d, e, r))
                if not seen_leg:
                    leg_first.append((name, bars, i, d, e, r)); seen_leg = True
    return base_all, leg_all, base_first, leg_first


if __name__ == '__main__':
    base_all, leg_all, base_first, leg_first = collect()
    lr_all = [r for *_, r in leg_all]
    lr_first = [r for *_, r in leg_first]

    print("=== H1: does the §1.3 leg rule improve on the base tape? ===")
    print("--- all bars (OVERLAPPING — t is inflated, do not read it as significance)")
    stat("base tape only", base_all)
    stat("base tape + full §1.3 leg", lr_all)
    print("--- one observation per name-day (non-overlapping, honest n)")
    stat("base tape only, first bar of day", base_first)
    stat("base tape + §1.3, first bar of day", lr_first)
    if base_first and lr_first:
        print(f"\n§1.3 selects {len(lr_all)} bars out of {len(base_all)} base-tape bars "
              f"and the selected\nbars average {st.mean(lr_all) - st.mean(base_all):+.2f}% "
              f"versus the unselected average. The rule is not\nfinding the good bars.")

    print("\n=== H2: fade the breakout instead of following it ===")
    stat("§1.3 bars, faded", [-x for x in lr_all])
    stat("§1.3 first-per-day, faded", [-x for x in lr_first])

    print("\n=== H3: holding period (first §1.3 bar per name-day) ===")
    for n, lab in ((3, '15 min'), (6, '30 min'), (12, '60 min'),
                   (24, '120 min'), (0, 'to the close')):
        stat(f"hold {lab}", [ret(b, i, d, n) for _, b, i, d, _, _ in leg_first])

    print("\n=== H4: cost arithmetic ===")
    m = st.mean(lr_first) if lr_first else 0.0
    print(f"signal is worth {m:+.3f}% per trade on the underlying.")
    print("An option at 7.9x delta leverage paying a 7% round-trip spread needs")
    print("roughly +0.9% on the underlying just to break even. The signal is two")
    print("orders of magnitude short of its own transaction cost.")
