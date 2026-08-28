#!/usr/bin/env python3
"""LITERAL test, owner's exact words: "buy 100 dollar of the most dip stock
everyday for two years, sell limit at 90 and 120, track this for the whole
year, show me the end balance of the account."

WHAT THIS IS AND HOW IT DIFFERS FROM tools/sp500_dip_hold20_recycle.py
=======================================================================
That file recycled a FIXED $10,000 pool across M tranches — capped concurrency,
a freed tranche waits for the next morning. This is different and simpler:
EVERY trading day, spend a FRESH $100 on that day's single biggest S&P 500
drop, regardless of how many earlier $100 positions are still open. There is
no shared pool and no cap — the "account" is an ever-growing set of
independent $100 bets, funded by new contributions each day (like a daily
DCA-style buy), not by recycling. That is what "track the account balance"
implies: total money put IN matters as much as the ending value.

"sell limit at 90 and 120" — implemented as a bracket: LIMIT sell at $120
(take-profit, a limit order is the right tool to sell into strength) and a
STOP at $90 for the downside, not a resting limit. A real sell LIMIT at $90
would refuse to fill below $90 — if the stock gaps under $90 it would do
NOTHING, leaving the position open and falling further, which is the
opposite of "limiting the loss." A stop order (trigger at $90, execute at
the next available price) is what actually caps the loss, so that is what is
modelled, with the same gap-aware fill logic already validated in
sp500_dip_hold20_recycle.py: if the day's OPEN is already <= $90, the fill is
that OPEN (the realistic bad price), not a fantasy $90 print.

Every other methodology choice matches today's established discipline and is
inherited, not re-derived: no lookahead (rank at day t's close, buy at day
t+1's open), PIT date_added filter (survivorship-uncorrectable on deletions,
worse for the older year — same caveat as every prior test today), real SPY
benchmark via an equivalent $100/day DCA-into-SPY comparison (the fair "same
cash flows, just the index" competitor), and costs at 5bp/10bp round trip.

Reuses load_members/load_bars/stats/fmt_pct from sp500_losers_backtest.py and
build_ranked from sp500_dip_hold20_recycle.py rather than reimplementing.

Usage: python3 tools/sp500_dip_daily_100.py [--target 0.20] [--stop 0.10] [--costs 0,5,10]
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sp500_losers_backtest import load_members, load_bars, stats, fmt_pct
from sp500_dip_hold20_recycle import build_ranked

DAILY_BUY = 100.0


def simulate(all_dates, px, ranked, start, end, target, stop, cost_rt):
    """Independent $100 position opened every trading day (next-day open),
    bracket-exit (gap-aware stop, close-checked target), no shared capital
    cap. Returns closed/open position records and full daily accounting."""
    half = cost_rt / 2.0
    dates = [d for d in all_dates if start <= d <= end]
    idx = {d: i for i, d in enumerate(all_dates)}
    open_lots = []          # list of dicts: sym, sh, ep, ed, days, minlow, mindd
    closed = []
    last_px = {}
    contributed = 0.0
    buys_made = 0
    no_candidate_days = 0

    for d in dates:
        i = idx[d]
        if i == 0:
            continue
        # ---- 1. today's fresh $100 buy, at the open, ranked off yesterday's close
        sig_day = all_dates[i - 1]
        cands = ranked.get(sig_day, [])
        bought = False
        for s, r in cands:
            if r >= 0:
                continue                       # only actual drops qualify
            bar = px[s].get(d)
            if not bar or bar[0] <= 0:
                continue
            p = bar[0]
            eff = p * (1.0 + half)
            sh = DAILY_BUY / eff
            open_lots.append(dict(sym=s, sh=sh, ep=p, ed=d, days=0,
                                  minlow=bar[2], mindd=min(0.0, bar[2] / p - 1.0)))
            contributed += DAILY_BUY
            buys_made += 1
            bought = True
            break
        if not bought:
            no_candidate_days += 1

        # ---- 2. mark + gap-aware bracket exit check on every open lot
        still_open = []
        for lot in open_lots:
            bar = px[lot['sym']].get(d)
            if bar:
                last_px[lot['sym']] = bar[3]
                lo, hi, c, op = bar[2], bar[1], bar[3], bar[0]
                if lo < lot['minlow']:
                    lot['minlow'] = lo
                lot['mindd'] = min(lot['mindd'], lo / lot['ep'] - 1.0)
            else:
                c = last_px.get(lot['sym'], lot['ep']); lo = hi = op = c
            entry_day = lot['ed'] == d          # today IS this lot's entry day
            if not entry_day:
                lot['days'] += 1
            tgt = lot['ep'] * (1.0 + target) if target else None
            stl = lot['ep'] * (1.0 - stop)
            reason, fill = None, None
            # A real bracket/stop order is live from the moment of entry, so
            # a LATER day's open gapping through the stop is the realistic
            # bad fill (BUG FIXED: an earlier version of this file checked
            # the gap condition only ON the entry day, where entry price IS
            # that day's open by construction — op<=stl can never be true
            # there, silently making stop_gap unreachable and reporting 0
            # gap-throughs on a 2-year, 500-name run where the tranche-pool
            # sibling script found ~24%. The entry day cannot gap through
            # itself; only a HELD position can gap on a subsequent morning.)
            if not entry_day and op <= stl:
                reason, fill = 'stop_gap', op
            elif lo <= stl:
                reason, fill = 'stop', stl
            elif not entry_day and tgt is not None and c >= tgt:
                reason, fill = 'target', c
            if reason:
                proceeds = lot['sh'] * fill * (1.0 - half)
                closed.append(dict(sym=lot['sym'], ed=lot['ed'], ep=lot['ep'],
                                   xd=d, xp=fill, days=lot['days'], reason=reason,
                                   cost=lot['sh'] * lot['ep'], proceeds=proceeds,
                                   ret=fill / lot['ep'] - 1.0))
            else:
                still_open.append(lot)
        open_lots = still_open

    open_value = 0.0
    open_positions = []
    for lot in open_lots:
        bar = px[lot['sym']].get(dates[-1])
        mark = bar[3] if bar else last_px.get(lot['sym'], lot['ep'])
        v = lot['sh'] * mark
        open_value += v
        open_positions.append(dict(sym=lot['sym'], ed=lot['ed'], ep=lot['ep'],
                                   days=lot['days'], mark=mark, value=v,
                                   ret=mark / lot['ep'] - 1.0))

    realized = sum(c['proceeds'] for c in closed)
    realized_cost = sum(c['cost'] for c in closed)
    balance = realized + open_value
    return dict(dates=dates, closed=closed, open=open_positions,
               contributed=contributed, buys_made=buys_made,
               no_candidate_days=no_candidate_days,
               realized=realized, realized_cost=realized_cost,
               open_value=open_value, balance=balance)


def dca_spy(spy, dates, cost_rt):
    """Same cash flow discipline: $100 into SPY at every trading day's open,
    never sold, marked at the window's last close. The fair 'just buy the
    index with this money' comparison."""
    half = cost_rt / 2.0
    shares = 0.0
    contributed = 0.0
    for d in dates:
        bar = spy.get(d)
        if not bar or bar[0] <= 0:
            continue
        shares += DAILY_BUY / (bar[0] * (1.0 + half))
        contributed += DAILY_BUY
    last_close = None
    for d in reversed(dates):
        if d in spy:
            last_close = spy[d][3]
            break
    return dict(contributed=contributed, balance=shares * last_close,
               shares=shares, mark=last_close)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', type=float, default=0.20)
    ap.add_argument('--no-target', action='store_true',
                    help='disable the take-profit leg entirely -- stop-loss only, let winners run')
    ap.add_argument('--stop', type=float, default=0.10)
    ap.add_argument('--no-pit', action='store_true')
    ap.add_argument('--max-drop', type=float, default=0.50)
    ap.add_argument('--costs', default='0,5,10')
    a = ap.parse_args()

    members = load_members()
    px, missing = load_bars(members)
    spy_px, _ = load_bars(['SPY'])
    spy = spy_px['SPY']
    costs = [float(c) / 10000.0 for c in a.costs.split(',')]

    all_dates, ranked, artifacts = build_ranked(px, members, not a.no_pit, a.max_drop)
    start, end = all_dates[1], all_dates[-1]
    target = None if a.no_target else a.target

    print('=' * 112)
    print(f'BUY $100 OF THE BIGGEST DAILY DROP, EVERY TRADING DAY, FOR TWO YEARS')
    tgt_label = f'sell limit +{100*a.target:.0f}%, ' if target else 'NO TAKE-PROFIT -- '
    print(f'{tgt_label}stop -{100*a.stop:.0f}% (gap-aware){"" if target else ", let winners run"}')
    print('=' * 112)
    print(f'window        : {start} .. {end}  ({len(all_dates)-1} trading days)')
    print(f'universe      : {len(members)} current S&P 500 members; bars loaded {len(px)}, missing {len(missing)}')
    print(f'PIT filter    : {"OFF" if a.no_pit else "ON (date_added <= signal day)"} — deletions still uncorrectable,')
    print(f'                more so for the earlier part of the window; every number below is an upper bound.')
    print(f'entry         : next trading day OPEN (executable, no lookahead)')
    if target:
        print(f'exit          : LIMIT sell at entry*1.{100*a.target:.0f} checked on the CLOSE;')
    else:
        print(f'exit          : NO TAKE-PROFIT -- a position is held until it stops out or the window ends.')
    print(f'                STOP at entry*0.{100*(1-a.stop):.0f}, gap-aware (fills at the OPEN if it gapped through)')
    print()

    for cost in costs:
        r = simulate(all_dates, px, ranked, start, end, target, a.stop, cost)
        n_c, n_o = len(r['closed']), len(r['open'])
        wins = sum(1 for c in r['closed'] if c['reason'] == 'target')
        stops = sum(1 for c in r['closed'] if c['reason'] in ('stop', 'stop_gap'))
        gaps = sum(1 for c in r['closed'] if c['reason'] == 'stop_gap')
        win_rate = wins / n_c if n_c else float('nan')

        print('-' * 112)
        print(f'COST {cost*10000:.0f}bp round trip')
        print('-' * 112)
        print(f'  trading days with a buy      : {r["buys_made"]} of {len(r["dates"])-1}  '
              f'(no-candidate days: {r["no_candidate_days"]})')
        print(f'  total contributed            : ${r["contributed"]:,.2f}')
        print(f'  positions closed / still open: {n_c} / {n_o}')
        print(f'  closed: hit +{100*a.target:.0f}% target   : {wins}  ({100*wins/n_c:.1f}% of closed)' if (n_c and target) else '')
        print(f'  closed: hit -{100*a.stop:.0f}% stop      : {stops}  (of which gapped through: {gaps})' if n_c else '')
        print(f'  win rate (closed positions)  : {100*win_rate:.1f}%'
              if n_c else '  win rate: n/a')
        print(f'  realized P&L (closed)        : ${r["realized"]-r["realized_cost"]:+,.2f}  '
              f'(cost basis ${r["realized_cost"]:,.2f} -> proceeds ${r["realized"]:,.2f})')
        print(f'  value of still-open positions: ${r["open_value"]:,.2f}  '
              f'({100*r["open_value"]/r["contributed"]:.1f}% of all contributions, marked at window end)')
        print(f'  ---')
        print(f'  ENDING ACCOUNT BALANCE       : ${r["balance"]:,.2f}')
        print(f'  NET GAIN / LOSS               : ${r["balance"]-r["contributed"]:+,.2f}  '
              f'({100*(r["balance"]/r["contributed"]-1):+.2f}% on contributed capital)')

        if cost == costs[1] if len(costs) > 1 else False:
            pass

    print()
    print('=' * 112)
    print('SAME CASH FLOWS, JUST BUYING SPY INSTEAD ($100/day, held, never sold)')
    print('=' * 112)
    for cost in costs:
        d = dca_spy(spy, [dd for dd in all_dates if start <= dd <= end], cost)
        print(f'  {cost*10000:>4.0f}bp   contributed ${d["contributed"]:,.2f}  ->  '
              f'balance ${d["balance"]:,.2f}  '
              f'({100*(d["balance"]/d["contributed"]-1):+.2f}% on contributed capital)')

    print()
    print('Reading this: "balance" mixes REALIZED cash from closed trades with the paper')
    print('mark of whatever is still open at the window end — if a lot never hit +20% or')
    print('-10%, its "value" is just today\'s price, not money in hand. See the worst-position')
    print('detail printed below for how much of the balance that really is.')

    print()
    print('=' * 112)
    print('WORST OPEN POSITIONS AT WINDOW END (5bp cost run)')
    print('=' * 112)
    r5 = simulate(all_dates, px, ranked, start, end, target, a.stop, 0.0005)
    worst = sorted(r5['open'], key=lambda p: p['ret'])[:8]
    for p in worst:
        print(f"  {p['sym']:6s} bought {p['ed']} @ ${p['ep']:.2f} -> now ${p['mark']:.2f}  "
              f"({100*p['ret']:+.1f}%)  held {p['days']}d  position value ${p['value']:.2f}")


if __name__ == '__main__':
    main()
