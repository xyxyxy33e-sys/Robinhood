#!/usr/bin/env python3
"""The FOUR states of (50dma, 200dma), not three.

The earlier agreement ladder collapsed "above 50 but below 200" into the same
bucket as "below both". Those are very different tapes:

  S1  above both              -- established uptrend
  S2  above 200, below 50     -- pullback inside an uptrend
  S3  below 200, above 50     -- EARLY RECOVERY: price has reclaimed the fast
                                 average while the slow one is still falling
  S4  below both              -- established downtrend

S3 matters because of an independent earlier result: forward returns are
best in the FIRST ~20 days of a fresh regime and decay with trend age. If that
holds, S3 deserves MORE leverage than S2, not less -- the opposite of what a
naive "count how many MAs agree" ladder does.

Also tests the 50/200 CROSSOVER (golden/death cross) as the state variable,
which is a different signal from price-vs-MA, and a BUFFER ENSEMBLE that
averages over the fragile 1% buffer parameter.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B
from shift import run_variable

SPLIT = '2019-12-31'


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
    print(f"BAR  QQQ B&H: Sh {QS:.2f}  CAGR {QC*100:+.2f}%  "
          f"maxDD {QD*100:.1f}%  uw {QU:.1f}mo\n")

    def four(buf):
        s50 = B.breaker_states(rows, 'ma50', buf)
        s200 = B.breaker_states(rows, 'ma200', buf)
        return s50, s200

    def levs4(s50, s200, L):
        out = []
        for x, y in zip(s50, s200):
            if x and y:       out.append(L[0])   # S1 above both
            elif y:           out.append(L[1])   # S2 pullback in uptrend
            elif x:           out.append(L[2])   # S3 early recovery
            else:             out.append(L[3])   # S4 downtrend
        return out

    def show(lab, levs, cost=10.0):
        m, c = run_variable(rows, levs, cost_bps=cost)
        s, h = sp(c)
        win = (m['sharpe'] > QS and m['cagr'] > QC and m['mdd'] > QD
               and m['dd_months'] < QU)
        print(f"{lab:34}{m['sharpe']:>7.2f}{m['cagr']*100:>8.2f}%"
              f"{m['mdd']*100:>7.1f}%{m['dd_months']:>6.1f}{m['trades_per_yr']:>6.1f}"
              f"{s['sharpe']:>7.2f}{h['sharpe']:>7.2f}{'  *' if win else ''}")
        return m, c

    s50, s200 = four(0.01)
    # how much time is actually spent in each state?
    from collections import Counter
    cnt = Counter('S1' if (x and y) else 'S2' if y else 'S3' if x else 'S4'
                  for x, y in zip(s50, s200))
    tot = sum(cnt.values())
    print("time in each state: " + "  ".join(
        f"{k} {cnt[k]/tot*100:.1f}%" for k in ('S1','S2','S3','S4')) + "\n")

    hdr = f"{'config  (S1/S2/S3/S4)':34}{'fullSh':>7}{'CAGR':>9}{'maxDD':>7}{'uw':>6}{'tr/yr':>6}{'srch':>7}{'hold':>7}"
    print("FOUR-STATE LADDER — does S3 (early recovery) deserve more than S2?")
    print(hdr)
    for L in [(2.0,1.0,1.0,0.5),   # 3-state equivalent (S2=S3), the old winner
              (2.0,1.0,1.5,0.5),   # S3 > S2: early recovery gets MORE
              (2.0,1.5,1.0,0.5),   # S2 > S3: pullback gets more
              (2.0,1.0,0.5,0.5),   # S3 treated as weak
              (2.0,1.25,1.5,0.5),
              (2.5,1.25,1.5,0.5)]:
        show(f"{L[0]}/{L[1]}/{L[2]}/{L[3]}", levs4(s50, s200, L))

    print("\n50/200 CROSSOVER (golden/death cross) instead of price-vs-MA")
    print(hdr)
    gc = [1 if rows[i]['ma50'] and rows[i]['ma200'] and
          rows[i]['ma50'] > rows[i]['ma200'] else 0 for i in range(len(rows))]
    for hi, lo in ((2.0,1.0),(2.0,0.5),(3.0,1.5),(2.0,0.0)):
        show(f"cross {hi}/{lo}", [hi if g else lo for g in gc])

    print("\nBUFFER ENSEMBLE — average the 0%/1%/2% variants of the best ladder")
    print(hdr)
    curves = []
    for buf in (0.0, 0.01, 0.02):
        a, b = four(buf)
        _, c = run_variable(rows, levs4(a, b, (2.0,1.0,1.0,0.5)))
        curves.append(c)
    for buf, c in zip((0.0,0.01,0.02), curves):
        m = B.metrics(c, [c[i]/c[i-1]-1 for i in range(1,len(c))], rf)
        s, h = sp(c)
        win = (m['sharpe']>QS and m['cagr']>QC and m['mdd']>QD and m['dd_months']<QU)
        print(f"{'  single, buffer '+format(buf,'.0%'):34}{m['sharpe']:>7.2f}"
              f"{m['cagr']*100:>8.2f}%{m['mdd']*100:>7.1f}%{m['dd_months']:>6.1f}"
              f"{'':>6}{s['sharpe']:>7.2f}{h['sharpe']:>7.2f}{'  *' if win else ''}")
    ens = [1.0]
    a = [1/3]*3
    for i in range(1, len(curves[0])):
        a = [a[k]*(curves[k][i]/curves[k][i-1]) for k in range(3)]
        t = sum(a); ens.append(t)
        if i % 21 == 0: a = [t/3]*3
    m = B.metrics(ens, [ens[i]/ens[i-1]-1 for i in range(1,len(ens))], rf)
    s, h = sp(ens)
    win = (m['sharpe']>QS and m['cagr']>QC and m['mdd']>QD and m['dd_months']<QU)
    print(f"{'  ENSEMBLE over buffers':34}{m['sharpe']:>7.2f}{m['cagr']*100:>8.2f}%"
          f"{m['mdd']*100:>7.1f}%{m['dd_months']:>6.1f}{'':>6}"
          f"{s['sharpe']:>7.2f}{h['sharpe']:>7.2f}{'  *' if win else ''}")
    print("\n* = beats QQQ B&H on ALL FOUR (Sharpe, CAGR, maxDD, months underwater)")


if __name__ == '__main__':
    main()
