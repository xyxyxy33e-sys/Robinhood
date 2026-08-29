#!/usr/bin/env python3
"""Leverage a 15-stock book WITHOUT margining the stocks.

The practical objection to the previous test: you cannot easily run a leverage
ladder on fifteen individual positions. Margining each name is operationally
ugly and expensive at retail rates.

But finding 3 of that test said the regime signal is a MARKET signal, not an
asset signal (SPMO traded off QQQ's moving averages beat SPMO traded off its
own by 0.10 of Sharpe). If the signal is about the market, the leverage can be
too. So: hold the stock book unlevered as the CORE, and express all the
leverage through a single INDEX SATELLITE whose size the ladder sets.

  weight_TQQQ = f(state);  weight_SPMO = 1 - weight_TQQQ
  effective exposure = (1-w)*1 + w*3 = 1 + 2w

No margin, no borrowing spread, no per-name financing. One satellite position
to resize, ~8 times a year. TQQQ carries its own embedded leverage, which is
cheaper than retail margin and is already in its price history.

Comparison set includes the margin version from the previous test so the two
routes to the same exposure can be read side by side.
"""
import csv, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B
from spmo_ladder import load, rf_map, states, sim

TD = 252


def overlay(dates, SP, TQ, st, wmap, rf, cost_bps=10.0):
    """Core SPMO + TQQQ satellite sized by regime state. Rebalance on change."""
    eq = 1.0; curve = []; rets = []; rfs = []
    cur = None
    side = cost_bps/2/10000.0
    for i in range(1, len(dates)):
        w = wmap[st[i-1]]
        if cur is None or abs(w-cur) > 1e-9:
            eq *= (1 - abs(w-(cur or 0.0))*2*side)   # both legs traded
            cur = w
        r = (1-w)*(SP[dates[i]]/SP[dates[i-1]]-1) + w*(TQ[dates[i]]/TQ[dates[i-1]]-1)
        eq *= (1+r); curve.append(eq); rets.append(r)
        rfs.append(rf.get(dates[i-1], 0.04)/TD)
    return B.metrics(curve, rets, rfs), curve


def main():
    rf = rf_map()
    SP, QQ, TQ = load('SPMO'), load('QQQ'), load('TQQQ')
    dates = sorted(set(SP) & set(QQ) & set(TQ))
    st = states(dates, QQ)          # market signal, per finding 3
    print(f"window {dates[0]} .. {dates[-1]}  ({len(dates)/TD:.1f} yrs)")
    print("states from QQQ's own 50/200dma (market signal); core = SPMO\n")

    def row(lab, m, extra=''):
        print(f"{lab:44}{(m['final']-1)*100:>9.1f}{m['cagr']*100:>8.1f}"
              f"{m['mdd']*100:>9.1f}{m['vol']*100:>7.1f}{m['sharpe']:>8.2f}"
              f"{m['dd_months']:>7.1f}  {extra}")

    print(f"{'':44}{'TOTAL':>9}{'CAGR':>8}{'MAX DD':>9}{'VOL':>7}{'SHARPE':>8}{'uw mo':>7}")
    for sym, px in (('SPMO', SP), ('QQQ', QQ)):
        m, _ = sim(dates, px, [1.0]*len(dates), rf, 0.0)
        row(f'{sym} buy-and-hold (1x)', m)
    m, _ = sim(dates, SP, [dict(A=2.0,B=2.0,C=0.5,D=1.0,E=1.0,F=0.5)[s] for s in st],
               rf, 0.03)
    row('SPMO + MARGIN ladder @3% (previous test)', m)

    print("\n  SPMO core + TQQQ satellite, no margin:")
    for lab, wm in [
        ('sat 25/25/0/10/10/0   -> 1.5x max',
         dict(A=0.25,B=0.25,C=0.0,D=0.10,E=0.10,F=0.0)),
        ('sat 35/35/0/15/15/0   -> 1.7x max',
         dict(A=0.35,B=0.35,C=0.0,D=0.15,E=0.15,F=0.0)),
        ('sat 50/50/0/25/25/0   -> 2.0x max',
         dict(A=0.50,B=0.50,C=0.0,D=0.25,E=0.25,F=0.0)),
        ('sat 50/50/0/25/25/0 + cash in C/F', None),
        ('sat flat 35% always   -> 1.7x const',
         dict(A=0.35,B=0.35,C=0.35,D=0.35,E=0.35,F=0.35)),
    ]:
        if wm is None:
            continue
        m, _ = overlay(dates, SP, TQ, st, wm, rf)
        row('    '+lab, m)

    print("\n  reference: pure QQQ/QLD/TQQQ ladder (no stock book)")
    from shift import run_variable
    rows = B.load_panel()
    d2 = [r['date'] for r in rows[1:]]
    i0 = next(i for i, d in enumerate(d2) if d >= dates[0])
    L6 = dict(A=2.0,B=2.0,C=0.5,D=1.0,E=1.0,F=0.5)
    s6 = states([r['date'] for r in rows], {r['date']: r['qqq_c'] for r in rows})
    _, c = run_variable(rows, [L6[s] for s in s6])
    cc = [x/c[i0] for x in c[i0:]]
    rr = [cc[i]/cc[i-1]-1 for i in range(1, len(cc))]
    rfl = [B.daily_rf(rows[i-1]['rf']) for i in range(1, len(rows))][i0:]
    row('    QQQ ladder 2/2/0.5/1/1/0.5', B.metrics(cc, rr, rfl))


if __name__ == '__main__':
    main()
