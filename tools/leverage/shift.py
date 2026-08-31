#!/usr/bin/env python3
"""SHIFT LEVERAGE WITH TIMING -- carry L_high when the breaker is on and
L_low (>0) when it is off, rather than going fully to cash.

This is NOT the falsified design. What was falsified is exposure scaled by the
CONVICTION SCORE, which is inverted (high score -> worse forward returns,
confirmed four ways). Here exposure is a function of the binary timing STATE,
which is the only part of the signal that carries information.

  L_low = 0        -> pure binary timing (already tested, loses on search)
  L_low = L_high   -> buy-and-hold        (already tested, wins on search)
  0 < L_low < L_high -> the untested middle, which is what "shift leverage
                        with timing" actually means.

Also tests a 3-STATE ladder on MA agreement (above both 50 and 200dma / above
200 only / below both), graded on AGREEMENT rather than on the inverted score.

Discipline unchanged: search 2010-02-11..2019-12-31, holdout 2020-01-01 on,
costs on real turnover, benchmarked against QQQ buy-and-hold.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B

SPLIT = '2019-12-31'
COST_BPS = 10.0


def ladder(L):
    """Lowest-multiple routing: QQQ<=1x, QQQ/QLD 1-2x, QLD/TQQQ 2-3x."""
    if L <= 0:   return {}
    if L <= 1.0: return {'QQQ': L}
    if L <= 2.0: return {'QQQ': 2.0 - L, 'QLD': L - 1.0}
    return {'QLD': 3.0 - L, 'TQQQ': L - 2.0}


def run_variable(rows, levs, cost_bps=COST_BPS):
    """Hold shares; rebalance only when the target leverage CHANGES."""
    side = cost_bps / 2.0 / 10000.0
    shares, cash, cur_L = {}, 1.0, None
    curve, rets, rfs = [], [], []
    trades, turnover = 0, 0.0
    for i in range(1, len(rows)):
        prev, cur = rows[i-1], rows[i]
        tgt = levs[i-1]                       # strictly prior row's state
        eq_open = cash*(1+B.daily_rf(prev['rf'])) + sum(
            n*B.px(prev, a, 'c') for a, n in shares.items())
        if cur_L is None or abs(tgt - cur_L) > 1e-9:
            w = ladder(tgt)
            new = {a: eq_open*wt/B.px(prev, a, 'c') for a, wt in w.items()}
            tv = sum(abs(new.get(a,0)-shares.get(a,0))*B.px(prev,a,'c')
                     for a in set(new)|set(shares))
            eq_open -= tv*side
            turnover += tv/eq_open if eq_open else 0
            trades += 1
            w = ladder(tgt)
            shares = {a: eq_open*wt/B.px(prev, a, 'c') for a, wt in w.items()}
            cash = eq_open - sum(n*B.px(prev,a,'c') for a,n in shares.items())
            cur_L = tgt
        eq = cash*(1+B.daily_rf(prev['rf'])) + sum(
            n*B.px(cur, a, 'c') for a, n in shares.items())
        cash = cash*(1+B.daily_rf(prev['rf']))
        prev_eq = curve[-1] if curve else 1.0
        curve.append(eq); rets.append(eq/prev_eq - 1)
        rfs.append(B.daily_rf(prev['rf']))
    m = B.metrics(curve, rets, rfs)
    yrs = (len(rows)-1)/B.TRADING_DAYS
    m['trades_per_yr'] = trades/yrs
    return m, curve


def main():
    rows = B.load_panel()
    dates = [r['date'] for r in rows[1:]]
    rf = [B.daily_rf(rows[i-1]['rf']) for i in range(1, len(rows))]
    cut = next(i for i, d in enumerate(dates) if d > SPLIT)

    def split_stats(curve):
        out = []
        for lo, hi in ((0, cut), (cut, len(curve))):
            c = [x/curve[lo] for x in curve[lo:hi]]
            r = [c[i]/c[i-1]-1 for i in range(1, len(c))]
            out.append(B.metrics(c, r, rf[lo:hi]))
        return out

    q = B.buy_hold(rows, 'QQQ')
    print(f"BAR: QQQ buy-and-hold  full Sharpe {q['sharpe']:.2f}  "
          f"CAGR {q['cagr']*100:+.2f}%  maxDD {q['mdd']*100:.1f}%  "
          f"underwater {q['dd_months']:.1f}mo\n")

    st = B.breaker_states(rows, 'ma200', 0.01)

    print("SHIFT LEVERAGE WITH TIMING: L_high when above 200dma, L_low when below")
    print(f"{'L_high':>7}{'L_low':>7}{'fullSh':>8}{'CAGR':>9}{'maxDD':>8}"
          f"{'uw mo':>7}{'tr/yr':>7}   {'srchSh':>8}{'holdSh':>8}{'spread':>8}")
    best = []
    for Lh in (2.0, 3.0):
        for Ll in (0.0, 0.5, 1.0, 1.5, 2.0):
            if Ll > Lh: continue
            levs = [Lh if s else Ll for s in st]
            m, curve = run_variable(rows, levs)
            s, h = split_stats(curve)
            print(f"{Lh:>7.1f}{Ll:>7.1f}{m['sharpe']:>8.2f}{m['cagr']*100:>8.2f}%"
                  f"{m['mdd']*100:>7.1f}%{m['dd_months']:>7.1f}{m['trades_per_yr']:>7.1f}"
                  f"   {s['sharpe']:>8.2f}{h['sharpe']:>8.2f}"
                  f"{abs(s['sharpe']-h['sharpe']):>8.2f}")
            best.append((Lh, Ll, s['sharpe'], h['sharpe'], m))

    print("\n3-STATE LADDER on MA agreement (not on the inverted score)")
    s50 = B.breaker_states(rows, 'ma50', 0.01)
    s200 = B.breaker_states(rows, 'ma200', 0.01)
    print(f"{'both':>6}{'200only':>9}{'neither':>9}{'fullSh':>8}{'CAGR':>9}"
          f"{'maxDD':>8}{'uw mo':>7}{'tr/yr':>7}   {'srchSh':>8}{'holdSh':>8}")
    for trio in ((3.0,2.0,1.0),(3.0,1.5,0.0),(2.0,1.5,1.0),(3.0,2.0,0.0),(2.0,1.0,0.5)):
        a,b,c = trio
        levs = [a if (x and y) else (b if y else c) for x, y in zip(s50, s200)]
        m, curve = run_variable(rows, levs)
        s, h = split_stats(curve)
        print(f"{a:>6.1f}{b:>9.1f}{c:>9.1f}{m['sharpe']:>8.2f}{m['cagr']*100:>8.2f}%"
              f"{m['mdd']*100:>7.1f}%{m['dd_months']:>7.1f}{m['trades_per_yr']:>7.1f}"
              f"   {s['sharpe']:>8.2f}{h['sharpe']:>8.2f}")

    print("\nsearch-period winner (what a pre-registered run would have picked):")
    w = max(best, key=lambda x: x[2])
    print(f"  L_high={w[0]} L_low={w[1]}  search Sharpe {w[2]:.2f} -> "
          f"holdout {w[3]:.2f}")


if __name__ == '__main__':
    main()
