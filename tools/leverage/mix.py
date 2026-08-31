#!/usr/bin/env python3
"""Do MIXES help? Two distinct meanings of "mix", both tested.

Builds on tools/leverage/backtest.py (imported, not reimplemented).

  MIX A -- STRATEGY BLEND. Hold a fixed fraction w of capital in an UNTIMED
  buy-and-hold sleeve and (1-w) in the 200dma-timed sleeve, rebalanced monthly.
  This is NOT the graded allocation already falsified: exposure is not scaled by
  a conviction score (that score is inverted). It is diversification ACROSS
  STRATEGIES at a fixed weight, which nothing has tested yet.

  MIX B -- SIGNAL ENSEMBLE. Equal-weight the 50/100/200dma sleeves, monthly
  rebalanced -- i.e. exposure proportional to how many rules agree. Motivated by
  the buffer sensitivity the main study left unsolved (ma200 CAGR swings
  47.24% -> 38.48% between 1% and 2% buffers): an ensemble should be less
  hostage to any one parameter. Graded on AGREEMENT, not on the inverted score.

Discipline unchanged: search 2010-02-11..2019-12-31, holdout 2020-01-01 onward,
costs on real turnover, benchmarked against buy-and-hold QQQ, which nothing in
six prior studies has beaten on Sharpe.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B

SPLIT = '2019-12-31'


def curve_of(recs):
    return [float(r['equity_curve']) for r in recs]


def blend(curves, weights, rebal=21):
    """Fixed-weight blend of sleeves, rebalanced every `rebal` trading days."""
    n = len(curves[0])
    a = list(weights)
    out = [1.0]
    for i in range(1, n):
        a = [a[k] * (curves[k][i] / curves[k][i-1]) for k in range(len(curves))]
        t = sum(a)
        out.append(t)
        if i % rebal == 0:
            a = [t * w for w in weights]
    return out


def main():
    rows = B.load_panel()
    dates = [r['date'] for r in rows[1:]]        # run() curves start at row 1
    rf = [B.daily_rf(rows[i-1]['rf']) for i in range(1, len(rows))]
    cut = next(i for i, d in enumerate(dates) if d > SPLIT)

    def report(label, curve):
        cells = []
        for lo, hi in ((0, cut), (cut, len(curve))):
            c = [x / curve[lo] for x in curve[lo:hi]]
            r = [c[i]/c[i-1]-1 for i in range(1, len(c))]
            m = B.metrics(c, r, rf[lo:hi])
            cells.append((m['cagr']*100, m['sharpe'], m['mdd']*100))
        (c1, s1, d1), (c2, s2, d2) = cells
        star = '  <== beats QQQ B&H holdout' if s2 > 0.74 else ''
        print(f"  {label:38s} search {c1:+7.2f}% Sh {s1:5.2f} DD {d1:7.1f}% | "
              f"holdout {c2:+7.2f}% Sh {s2:5.2f} DD {d2:7.1f}%{star}")
        return s1, s2

    print("BENCHMARK -- the bar nothing has cleared")
    qqq = B.buy_hold(rows, 'QQQ')
    print(f"  QQQ buy-and-hold: full-period Sharpe {qqq['sharpe']:.2f}, "
          f"CAGR {qqq['cagr']*100:+.2f}%, maxDD {qqq['mdd']*100:.1f}%\n")

    st200 = B.breaker_states(rows, 'ma200', 0.01)
    allin = B.breaker_states(rows, 'bh', 0.0)

    print("MIX A -- fixed blend: w untimed buy-and-hold + (1-w) 200dma-timed")
    for L in (1.0, 2.0, 3.0):
        timed = curve_of(B.run(rows, st200, L, collect=True)[1])
        untimed = curve_of(B.run(rows, allin, L, collect=True)[1])
        print(f"  --- leverage L={L}")
        for w in (0.0, 0.25, 0.50, 0.75, 1.0):
            report(f'w={w:.2f} untimed / {1-w:.2f} timed',
                   blend([untimed, timed], [w, 1-w]))

    print("\nMIX B -- ensemble of the 50/100/200dma sleeves, equal weight")
    for L in (1.0, 2.0, 3.0):
        legs = [curve_of(B.run(rows, B.breaker_states(rows, r, 0.01), L,
                               collect=True)[1])
                for r in ('ma50', 'ma100', 'ma200')]
        report(f'ensemble 50/100/200, L={L}', blend(legs, [1/3]*3))

    print("\nMIX B2 -- ensemble robustness: does it tame the buffer sensitivity?")
    for buf in (0.0, 0.01, 0.02):
        single = curve_of(B.run(rows, B.breaker_states(rows, 'ma200', buf), 2.0,
                                collect=True)[1])
        legs = [curve_of(B.run(rows, B.breaker_states(rows, r, buf), 2.0,
                               collect=True)[1]) for r in ('ma50','ma100','ma200')]
        s = report(f'ma200 alone, buffer {buf:.0%}', single)
        e = report(f'ensemble,    buffer {buf:.0%}', blend(legs, [1/3]*3))


if __name__ == '__main__':
    main()
