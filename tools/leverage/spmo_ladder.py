#!/usr/bin/env python3
"""Apply the six-state leverage ladder to the SPMO momentum book instead of QQQ.

Motivation: the SPMO Mirror Study reaches the same verdict this file does from an
independent direction -- momentum stock selection "earns its keep through a
shallower drawdown rather than a higher return." The two are complementary
layers, not competitors: SPMO is selection at 1x, the ladder is regime-scaled
leverage. This tests them stacked.

KEY MODELLING DIFFERENCE. There is no leveraged SPMO ETF, so leverage must come
from MARGIN, not from a 3x fund. That changes the cost structure in both
directions:
  + no daily-reset decay, because a margin position is not rebalanced daily
  - an explicit borrowing cost on the levered portion, at rf + spread

Modelled as: daily return = L*r_asset - (L-1)*(rf + spread)/252.
Spread swept, since a retail margin rate (Robinhood Gold ~5-6% gross) is far
worse than the financing embedded in TQQQ.

Regime states are built from the TRADED asset's own 50/200dma, which is the
principled choice, with QQQ-derived states reported alongside as a check.
"""
import csv, os, sys, statistics as st, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B

TD = 252


def load(sym):
    out = {}
    for r in csv.DictReader(open(f'data/kairos/etf/{sym}.csv')):
        try: out[r['d']] = float(r['c'])
        except Exception: pass
    return out


def rf_map():
    m = {}
    for r in csv.DictReader(open('data/kairos/DGS3MO.csv')):
        try: m[r['observation_date']] = float(r['DGS3MO'])/100.0
        except Exception: pass
    return m


def sma(v, i, n):
    return sum(v[i-n+1:i+1])/n if i >= n-1 else None


def states(dates, px, buf=0.01):
    """Six-state classifier with the same hysteresis band, on this asset."""
    v = [px[d] for d in dates]
    s50 = s200 = None
    out = []
    for i, d in enumerate(dates):
        m50, m200 = sma(v, i, 50), sma(v, i, 200)
        if m200 is None:
            out.append('F'); continue
        if v[i] > m50*(1+buf): s50 = True
        elif v[i] < m50*(1-buf): s50 = False
        if v[i] > m200*(1+buf): s200 = True
        elif v[i] < m200*(1-buf): s200 = False
        cr = m50 > m200
        if s50 and s200:        out.append('A' if cr else 'B')
        elif s50 and not s200:  out.append('C')
        elif s200:              out.append('D')
        else:                   out.append('E' if cr else 'F')
    return out


def sim(dates, px, levs, rf, spread):
    eq = 1.0; curve = []; rets = []; rfs = []
    for i in range(1, len(dates)):
        L = levs[i-1]
        r_a = px[dates[i]]/px[dates[i-1]] - 1
        rd = rf.get(dates[i-1], 0.04)
        borrow = max(0.0, L-1.0) * (rd + spread)/TD
        cash = max(0.0, 1.0-L) * rd/TD
        r = L*r_a - borrow + cash
        eq *= (1+r); curve.append(eq); rets.append(r); rfs.append(rd/TD)
    return B.metrics(curve, rets, rfs), curve


def main():
    rf = rf_map()
    SP, QQ = load('SPMO'), load('QQQ')
    dates = sorted(set(SP) & set(QQ))
    print(f"window {dates[0]} .. {dates[-1]}  ({len(dates)} sessions, "
          f"{len(dates)/TD:.1f} yrs)\n")

    st_self = states(dates, SP)
    st_qqq = states(dates, QQ)
    L6 = dict(A=2.0, B=2.0, C=0.5, D=1.0, E=1.0, F=0.5)

    def row(lab, m):
        print(f"{lab:40}{(m['final']-1)*100:>9.1f}{m['cagr']*100:>8.1f}"
              f"{m['mdd']*100:>9.1f}{m['vol']*100:>7.1f}{m['sharpe']:>8.2f}"
              f"{m['dd_months']:>7.1f}")

    print(f"{'':40}{'TOTAL':>9}{'CAGR':>8}{'MAX DD':>9}{'VOL':>7}{'SHARPE':>8}{'uw mo':>7}")
    for sym, px in (('SPMO', SP), ('QQQ', QQ)):
        m, _ = sim(dates, px, [1.0]*len(dates), rf, 0.0)
        row(f'{sym} buy-and-hold (1x)', m)

    print()
    for spread in (0.015, 0.03, 0.05):
        print(f"  --- margin spread over T-bills: {spread:.1%}")
        for lab, stt in (('SPMO ladder, own MAs', st_self),
                         ('SPMO ladder, QQQ MAs', st_qqq)):
            m, _ = sim(dates, SP, [L6[s] for s in stt], rf, spread)
            row(f'    {lab}', m)
        m, _ = sim(dates, QQ, [L6[s] for s in st_qqq], rf, spread)
        row('    QQQ ladder, QQQ MAs (reference)', m)
        print()

    print("  --- flat 2x margin, no timing (is the ladder or the leverage doing it?)")
    for sym, px in (('SPMO', SP), ('QQQ', QQ)):
        m, _ = sim(dates, px, [2.0]*len(dates), rf, 0.03)
        row(f'    {sym} constant 2x @3% spread', m)


if __name__ == '__main__':
    main()
