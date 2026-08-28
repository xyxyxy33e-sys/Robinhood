#!/usr/bin/env python3
"""LOCKED HOLDOUT -- Year B, 2025-08-28 .. 2026-08-27. RUN EXACTLY ONCE.

The candidate below was frozen by tools/mix_search_yeara.py after a K = 44 variant
search that touched ONLY Year A (2024-08-28 .. 2025-08-27). Nothing in this file is
tuned; it exists to answer one question one time. If the candidate fails here, that is
the answer, and the correct response is to write the failure down -- NOT to go back to
Year A, find a different mix, and run this file again. A holdout that has been looked
at twice is a search period.

THE LOCKED CANDIDATE, stated completely so it can be checked against the search file
====================================================================================
    Universe   503 current S&P 500 members, point-in-time additions filter on
               (date_added <= trade date), prior close >= $5, 21-day median dollar
               volume >= $5m, unbroken 63-bar close history ending at the prior close.
    Signals    (1) mom21   = 21-trading-day price return through the prior close
               (2) trend50 = prior close / its own 50-day simple MA - 1
               Combined as an EQUAL-WEIGHTED RANK BLEND: each eligible name is ranked
               on each signal (rank 0 = strongest), the ranks are summed, and the 50
               lowest sums are held.
    Portfolio  K = 50 names, EQUAL WEIGHTED, LONG ONLY, UNLEVERED, always fully invested
               (this candidate has no cash state).
    Rebalance  every 21 trading days (~monthly), 12 rebalances a year.
    Timing     signals computed through the CLOSE of day t-1; the old book is sold and
               the new book is bought at the OPEN of day t. No rule ever uses a close it
               also fills at.
    Costs      round-trip 5bp and 10bp, charged as cost * one-way turnover on the equity
               marked at the rebalance open.
    Capital    $10,000 at the open of the first day of the window.

WHY THIS ONE AND NOT THE BEST-LOOKING CELL. The highest Year-A alpha t among mixes was
the same rule with an added SPY-above-50dma cash gate (t = 1.51, Sharpe 1.81); it was
NOT locked, because it cleared the beta/cost gates at only ONE parameterization -- a lone
spike whose Year-A advantage comes from a single event (the April 2025 selloff). The
mom21 + trend50 structure cleared at four parameterizations (K = 25/50/100 and P = 5),
and within that structure the BASE parameterization (K = 50, P = 21, both fixed a priori
in the grid header) is locked rather than its best cell.

WHAT THE CANDIDATE ALREADY FAILED, ON THE SEARCH PERIOD ITSELF
=============================================================
Its Year-A alpha t is 1.21, well BELOW the pre-registered t > 2.5 screening bar. No
variant of the 44 cleared that bar. A 210-day sample can essentially never produce
t > 2.5 for a realistic equity rule -- +25%/yr of alpha at this volatility is only
t ~ 1.2 -- which is itself a finding: one year of daily data cannot establish an edge,
so the holdout is not a confirmation of a Year-A discovery, it is the only real test in
the exercise. A pass here is therefore WEAK evidence (two agreeing years, neither
individually significant); a failure here is strong evidence against.

TWO FURTHER CAVEATS THAT APPLY WHATEVER THIS PRINTS
===================================================
1. mom21 and trend50 have a mean cross-sectional Spearman rank correlation of +0.88 on
   Year A, and the blend's book overlaps each single factor's book 84% of the time. This
   is a two-horizon TREND rule, not two independent ideas. It satisfies the letter of
   "a mix" and only partly its spirit.
2. Both years in this cache are BULL years for SPY (Year A CAGR +15.3%, Year B +19.3%).
   A long-only trend rule has never been shown a bear market here. Nothing in this file
   can speak to how it behaves in one.

Usage:  python3 tools/mix_holdout_yearb.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mix_engine import (Panel, evaluate, spy_series, curve_metrics, beta_alpha,
                        HDR, fmt_row, TRADING_DAYS)
from mix_signals import blend, eligible, MOM, TREND

YEAR_B = ('2025-08-28', '2026-08-27')
K_NAMES, REBAL, BACK = 50, 21, 63

# Year-A numbers, copied from the search run so the two are side by side. These are
# RESTATED, not recomputed -- this file never re-opens the search period.
YEAR_A_NOTE = dict(cagr=0.2651, net5=0.2594, net10=0.2537, vol=0.1756, sharpe=1.43,
                   mdd=-0.1608, beta=0.63, alpha=0.1676, t=1.21,
                   spy_cagr=0.1394, spy_vol=0.2093, spy_sharpe=0.73, spy_mdd=-0.1900)


def locked_candidate():
    """The frozen rule. Built from the same library the search used."""
    return blend([MOM(21), TREND(50)], K_NAMES)


def ew_universe():
    cache = {}
    def select(P, i):
        if i not in cache:
            cache[i] = eligible(P, i, BACK)
        return cache[i]
    return select


def main():
    P = Panel(pit=True)
    idx = [i for i in P.window(*YEAR_B) if i - 1 - BACK >= 0]
    spy = spy_series(P, idx)
    sm = curve_metrics(spy)

    print('=' * 120)
    print('LOCKED HOLDOUT EVALUATION -- ONE LOOK, NO RE-TUNING')
    print('=' * 120)
    print(f'candidate : mom21 + trend50 equal-weight rank blend, K=50, monthly (P=21), '
          f'long-only, unlevered')
    print(f'window    : {P.dates[idx[0]]} .. {P.dates[idx[-1]]}, {len(idx)} trading days '
          f'(bars {idx[0]}..{idx[-1]})')
    print(f'search per: 2024-08-28..2025-08-27, K = 44 variants, none cleared t > 2.5')
    print(f'\nSPY buy-and-hold, IDENTICAL dates, identical first-day convention '
          f'(bought at the open of day 1):')
    print(f'   total {100*sm["total"]:+.2f}%  CAGR {100*sm["cagr"]:+.2f}%  vol {100*sm["vol"]:.2f}%  '
          f'Sharpe {sm["sharpe"]:.2f}  maxDD {100*sm["mdd"]:.2f}%  final ${10000*(1+sm["total"]):,.0f}')
    print('   (split-adjusted bars only: ~1.2%/yr of SPY dividend is MISSING, so this '
          'comparison is generous to the candidate.)')

    r = evaluate('LOCKED mom21+trend50', P, idx, locked_candidate(), REBAL)
    ref = evaluate('REF equal-weight universe', P, idx, ew_universe(), REBAL)

    print('\n' + HDR)
    print(fmt_row(r))
    print(fmt_row(ref))

    g, n5, n10 = r['gross'], r['nets'][5.0], r['nets'][10.0]
    d = r['diag']
    print(f'\nEQUITY CURVE, $10,000 at the open of {P.dates[idx[0]]}:')
    for lbl, m in (('gross', g), ('net 5bp', n5), ('net 10bp', n10)):
        print(f'   {lbl:<9} final ${m["final"]:>10,.0f}   total {100*m["total"]:+7.2f}%   '
              f'CAGR {100*m["cagr"]:+7.2f}%   vol {100*m["vol"]:6.2f}%   Sharpe {m["sharpe"]:+5.2f}   '
              f'maxDD {100*m["mdd"]:+7.2f}%')
    print(f'   SPY       final ${10000*(1+sm["total"]):>10,.0f}   total {100*sm["total"]:+7.2f}%   '
          f'CAGR {100*sm["cagr"]:+7.2f}%   vol {100*sm["vol"]:6.2f}%   Sharpe {sm["sharpe"]:+5.2f}   '
          f'maxDD {100*sm["mdd"]:+7.2f}%')

    print(f'\nTRADING PROFILE: {d["rebalances"]} rebalances, mean one-way turnover '
          f'{sum(d["turnover"])/len(d["turnover"]):.2f}, {len(d["names"])} distinct names held, '
          f'{d["cash_periods"]} cash periods, {d["carried_bars"]} carried (missing) bars.')
    cost_drag5 = 100 * (g['cagr'] - n5['cagr'])
    print(f'   Cost drag at 5bp round trip: {cost_drag5:.2f} pp of CAGR '
          f'({cost_drag5*2:.2f} pp at 10bp). Monthly rebalancing is what makes this small; the '
          f'daily-flip strategies tested earlier today paid ~12 pp at the same 5bp.')

    ba = beta_alpha(r['rets'][0.0], spy)
    print(f'\nCAPM vs SPY (matched exposure: both fully invested, both open-of-day-1 to '
          f'close-of-last-day, both hold overnight)')
    print(f'   beta  {ba["beta"]:+.3f}')
    print(f'   alpha {100*ba["alpha"]:+.4f}%/day = {100*ba["alpha_ann"]:+.2f}%/yr   '
          f't(alpha) = {ba["t"]:+.2f}')
    ba5 = beta_alpha(r['rets'][5.0], spy)
    print(f'   net of 5bp: alpha {100*ba5["alpha_ann"]:+.2f}%/yr, t = {ba5["t"]:+.2f}')
    print(f'   lag-1 autocorrelation of daily returns {r["ac1"]:+.3f}')

    rr = r['rets'][0.0]
    srt = sorted(range(len(rr)), key=lambda k: -abs(rr[k]))
    print('\nFRAGILITY (does the result live in a handful of days?)')
    for drop in (1, 3, 5):
        keep = [rr[k] for k in range(len(rr)) if k not in set(srt[:drop])]
        print(f'   gross CAGR after deleting the {drop} largest-|return| day(s): '
              f'{100*curve_metrics(keep)["cagr"]:+.2f}%')

    a = YEAR_A_NOTE
    print('\nSEARCH PERIOD vs HOLDOUT, side by side (Year A restated from the search run, '
          'not recomputed)')
    print(f'{"":<14} {"CAGR":>9} {"@5bp":>9} {"vol":>8} {"Sharpe":>7} {"maxDD":>9} '
          f'{"beta":>6} {"alpha/yr":>9} {"t":>6} {"SPY CAGR":>9}')
    print(f'{"Year A (fit)":<14} {100*a["cagr"]:>8.2f}% {100*a["net5"]:>8.2f}% {100*a["vol"]:>7.2f}% '
          f'{a["sharpe"]:>7.2f} {100*a["mdd"]:>8.2f}% {a["beta"]:>6.2f} {100*a["alpha"]:>8.2f}% '
          f'{a["t"]:>6.2f} {100*a["spy_cagr"]:>8.2f}%')
    print(f'{"Year B (HOLD)":<14} {100*g["cagr"]:>8.2f}% {100*n5["cagr"]:>8.2f}% {100*g["vol"]:>7.2f}% '
          f'{g["sharpe"]:>7.2f} {100*g["mdd"]:>8.2f}% {ba["beta"]:>6.2f} {100*ba["alpha_ann"]:>8.2f}% '
          f'{ba["t"]:>6.2f} {100*sm["cagr"]:>8.2f}%')

    print('\n' + '=' * 120)
    print('VERDICT (test fixed before this file was run: net-of-5bp CAGR >= SPY CAGR over the '
          'identical dates, AND alpha vs SPY not negative. Both must hold.)')
    c1 = n5['cagr'] >= sm['cagr']
    c2 = ba['alpha'] >= 0
    print(f'   net-5bp CAGR {100*n5["cagr"]:+.2f}% vs SPY {100*sm["cagr"]:+.2f}%  -> '
          f'{"PASS" if c1 else "FAIL"}')
    print(f'   alpha vs SPY {100*ba["alpha_ann"]:+.2f}%/yr (t={ba["t"]:+.2f})  -> '
          f'{"PASS" if c2 else "FAIL"}')
    print(f'   OVERALL: {"PASS" if (c1 and c2) else "FAIL"}')
    print('=' * 120)
    print('This holdout has now been used. Any further variant tested on Year B is an '
          'in-sample result and must be labelled as one.')


if __name__ == '__main__':
    main()
