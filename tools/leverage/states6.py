#!/usr/bin/env python3
"""SIX states, not four: price-vs-50, price-vs-200, AND 50-vs-200.

The earlier models used only price-vs-MA and treated 50-vs-200 as a separate
strategy. But the MA cross is a third dimension, and combining all three gives
six reachable states (two of the eight are arithmetically impossible):

  A  P>50, P>200, 50>200   established uptrend
  B  P>50, P>200, 50<200   RECLAIM -- price above both averages but the MAs
                           have not yet crossed. THIS is the true early-recovery
                           state; the previous model's "S3" was not.
  C  P>50, P<200, 50<200   bounce inside a downtrend
  D  P<50, P>200, 50>200   pullback inside an uptrend
  E  P<50, P<200, 50>200   BREAKDOWN -- price has lost both averages but the MAs
                           are still positively crossed. Early deterioration.
  F  P<50, P<200, 50<200   established downtrend

  impossible: (P>50, P<200, 50>200) implies P<200<50 hence P<50;
              (P<50, P>200, 50<200) implies P>200>50 hence P>50.

This matters because the earlier four-state test rejected the streak-age
hypothesis using state C (a dead-cat bounce) when the hypothesis was really
about state B (a genuine reclaim). Testing it on the right state.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B
from shift import run_variable
from collections import Counter

SPLIT = '2019-12-31'
ORDER = ['A', 'B', 'C', 'D', 'E', 'F']


def classify(rows, buf=0.01):
    s50 = B.breaker_states(rows, 'ma50', buf)
    s200 = B.breaker_states(rows, 'ma200', buf)
    out = []
    for i in range(len(rows)):
        m50, m200 = rows[i]['ma50'], rows[i]['ma200']
        cross = bool(m50 and m200 and m50 > m200)
        p50, p200 = bool(s50[i]), bool(s200[i])
        if p50 and p200:      out.append('A' if cross else 'B')
        elif p50 and not p200: out.append('C')
        elif not p50 and p200: out.append('D')
        else:                  out.append('E' if cross else 'F')
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
    print(f"BAR  QQQ B&H: Sh {QS:.2f}  CAGR {QC*100:+.2f}%  maxDD {QD*100:.1f}%  uw {QU:.1f}mo\n")

    st = classify(rows)
    cnt = Counter(st); tot = len(st)
    print("time in state: " + "  ".join(f"{k} {cnt[k]/tot*100:5.1f}%" for k in ORDER))

    # forward TQQQ return by state -- does B (reclaim) really lead?
    print("\nforward TQQQ return by state (21 trading days ahead):")
    fwd = {}
    for i in range(len(rows)-21):
        r = (rows[i+21]['tqqq_c']/rows[i]['tqqq_c']-1)*100
        fwd.setdefault(st[i], []).append(r)
    import statistics as S
    for k in ORDER:
        v = fwd.get(k, [])
        if len(v) > 20:
            print(f"   {k}  n={len(v):5}  mean {S.mean(v):+7.2f}%  median {S.median(v):+7.2f}%")

    def show(lab, L, cost=10.0):
        levs = [L[s] for s in st]
        m, c = run_variable(rows, levs, cost_bps=cost)
        s, h = sp(c)
        win = (m['sharpe'] > QS and m['cagr'] > QC and m['mdd'] > QD and m['dd_months'] < QU)
        print(f"{lab:38}{m['sharpe']:>7.2f}{m['cagr']*100:>8.2f}%{m['mdd']*100:>7.1f}%"
              f"{m['dd_months']:>6.1f}{m['trades_per_yr']:>6.1f}{s['sharpe']:>7.2f}"
              f"{h['sharpe']:>7.2f}{'  *' if win else ''}")

    print(f"\n{'config  A/B/C/D/E/F':38}{'fullSh':>7}{'CAGR':>9}{'maxDD':>7}{'uw':>6}{'tr/yr':>6}{'srch':>7}{'hold':>7}")
    cfgs = [
        ('2.0/2.0/0.5/1.0/0.5/0.5  B=A',   dict(A=2.0,B=2.0,C=0.5,D=1.0,E=0.5,F=0.5)),
        ('2.0/1.0/0.5/1.0/0.5/0.5  B mid', dict(A=2.0,B=1.0,C=0.5,D=1.0,E=0.5,F=0.5)),
        ('2.0/2.5/0.5/1.0/0.5/0.5  B>A',   dict(A=2.0,B=2.5,C=0.5,D=1.0,E=0.5,F=0.5)),
        ('2.0/2.0/0.5/1.0/1.0/0.5  E mid', dict(A=2.0,B=2.0,C=0.5,D=1.0,E=1.0,F=0.5)),
        ('2.0/2.0/0.5/1.0/0.0/0.0  E,F out',dict(A=2.0,B=2.0,C=0.5,D=1.0,E=0.0,F=0.0)),
        ('2.0/2.0/1.0/1.5/0.5/0.5',        dict(A=2.0,B=2.0,C=1.0,D=1.5,E=0.5,F=0.5)),
        ('3.0/3.0/0.5/1.5/0.5/0.5',        dict(A=3.0,B=3.0,C=0.5,D=1.5,E=0.5,F=0.5)),
    ]
    for lab, L in cfgs:
        show(lab, L)

    print("\nbuffer robustness of the best few (0% / 1% / 2%):")
    for lab, L in cfgs[:3]:
        line = []
        for buf in (0.0, 0.01, 0.02):
            s6 = classify(rows, buf)
            m, c = run_variable(rows, [L[s] for s in s6])
            line.append(m['sharpe'])
        print(f"  {lab:38} {line[0]:.2f} / {line[1]:.2f} / {line[2]:.2f}"
              f"   spread {max(line)-min(line):.2f}")
    print("\n* = beats QQQ B&H on ALL FOUR")


if __name__ == '__main__':
    main()
