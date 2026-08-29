#!/usr/bin/env python3
"""Sweep the leverage assigned to state B (the "reclaim" state).

B = price above BOTH averages while the 50dma is still below the 200dma.
Forward 21d return in B is +5.15% against +2.71% in A, so overweighting B has a
rationale. B is only ~5.3% of the time, so the question is whether that rationale
survives its small footprint.

Runs on RAW price-vs-MA inequalities (labels mean exactly what they say) AND on
the buffered/hysteretic states used elsewhere, because the earlier six-state work
used buffered states whose labels disagreed with the raw inequality on 6.9% of
days.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B
from shift import run_variable

SPLIT = '2019-12-31'


def states_raw(rows):
    out = []
    for r in rows:
        m50, m200, p = r['ma50'], r['ma200'], r['qqq_c']
        if not (m50 and m200):
            out.append('F'); continue
        p50, p200, cr = p > m50, p > m200, m50 > m200
        if p50 and p200:       out.append('A' if cr else 'B')
        elif p50 and not p200: out.append('C')
        elif not p50 and p200: out.append('D')
        else:                  out.append('E' if cr else 'F')
    return out


def states_buf(rows, buf):
    s50 = B.breaker_states(rows, 'ma50', buf)
    s200 = B.breaker_states(rows, 'ma200', buf)
    out = []
    for i, r in enumerate(rows):
        m50, m200 = r['ma50'], r['ma200']
        cr = bool(m50 and m200 and m50 > m200)
        p50, p200 = bool(s50[i]), bool(s200[i])
        if p50 and p200:       out.append('A' if cr else 'B')
        elif p50 and not p200: out.append('C')
        elif not p50 and p200: out.append('D')
        else:                  out.append('E' if cr else 'F')
    return out


def main():
    rows = B.load_panel()
    dates = [r['date'] for r in rows[1:]]
    rf = [B.daily_rf(rows[i-1]['rf']) for i in range(1, len(rows))]
    cut = next(i for i, d in enumerate(dates) if d > SPLIT)

    def sp(c):
        o = []
        for lo, hi in ((0, cut), (cut, len(c))):
            cc = [x/c[lo] for x in c[lo:hi]]
            r = [cc[i]/cc[i-1]-1 for i in range(1, len(cc))]
            o.append(B.metrics(cc, r, rf[lo:hi]))
        return o

    q = B.buy_hold(rows, 'QQQ')
    QS, QC, QD, QU = q['sharpe'], q['cagr'], q['mdd'], q['dd_months']
    print(f"BAR  QQQ B&H: Sh {QS:.2f}  CAGR {QC*100:+.2f}%  maxDD {QD*100:.1f}%  uw {QU:.1f}mo")
    print("base config A=2.0 C=0.5 D=1.0 E=1.0 F=0.5; only B varies\n")

    for tag, st in (('RAW inequalities', states_raw(rows)),
                    ('BUFFERED 1% (as used earlier)', states_buf(rows, 0.01))):
        print(f"--- {tag}")
        print(f"{'B':>5}{'fullSh':>8}{'CAGR':>9}{'maxDD':>8}{'uw':>6}{'tr/yr':>6}"
              f"{'srch':>7}{'hold':>7}{'spread':>8}")
        for b in (1.0, 1.5, 2.0, 2.5, 3.0):
            L = dict(A=2.0, B=b, C=0.5, D=1.0, E=1.0, F=0.5)
            m, c = run_variable(rows, [L[s] for s in st])
            s, h = sp(c)
            win = (m['sharpe'] > QS and m['cagr'] > QC and m['mdd'] > QD
                   and m['dd_months'] < QU)
            print(f"{b:>5.1f}{m['sharpe']:>8.2f}{m['cagr']*100:>8.2f}%"
                  f"{m['mdd']*100:>7.1f}%{m['dd_months']:>6.1f}"
                  f"{m['trades_per_yr']:>6.1f}{s['sharpe']:>7.2f}{h['sharpe']:>7.2f}"
                  f"{abs(s['sharpe']-h['sharpe']):>8.2f}{'  *' if win else ''}")
        print()

    print("buffer robustness of B=3.0 vs B=2.0 (full Sharpe at 0% / 1% / 2%)")
    for b in (2.0, 3.0):
        line = []
        for buf in (0.0, 0.01, 0.02):
            L = dict(A=2.0, B=b, C=0.5, D=1.0, E=1.0, F=0.5)
            m, _ = run_variable(rows, [L[s] for s in states_buf(rows, buf)])
            line.append(m['sharpe'])
        print(f"  B={b:.1f}:  {line[0]:.2f} / {line[1]:.2f} / {line[2]:.2f}"
              f"   spread {max(line)-min(line):.2f}")
    print("\n* = beats QQQ B&H on ALL FOUR")


if __name__ == '__main__':
    main()
