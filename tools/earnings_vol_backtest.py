#!/usr/bin/env python3
"""Backtest: is the option market over- or under-pricing the SIZE of the earnings move?

Two symmetric bets on ~2 years of single-stock earnings events:
  SHORT PREMIUM  sell an ATM straddle before the print, buy it back at the close of the
                 first session that contains the move (captures the IV crush).
  LONG  PREMIUM  the exact mirror image, same events, same contracts, opposite sign.

This is deliberately a DIFFERENT SHAPE of bet from everything else in tools/: it does not
forecast direction, it forecasts realised-vs-implied magnitude. Its failure mode is also
different, so the reporting is built around the TAIL, not the mean.

DATA (all real, none simulated) -- see data/earnings_options/
  earnings_dates.csv  get_earnings_results, 40 symbols x up-to-8 quarters. report.timing
                      ('am'/'pm') is what fixes entry/exit; getting it backwards is the
                      single easiest way to ruin this study.
  worklist.csv        derived: entry day, move day, expiry, ATM strike, realised move.
  instruments.csv     get_option_instruments(state='expired') -> real contract UUIDs.
  prices.csv          get_option_historicals(interval='day') -> real daily OHLC. The
                      CLOSE of a daily option bar is the LAST TRADE of the session, not a
                      mid and not a settlement mark. See "known data limits" below.
  ../sp500_daily/     cached split-adjusted equity bars (underlying + SPY).

METHODOLOGY -- the traps this file is built to avoid
====================================================
1. ONE EARNINGS EVENT = ONE OBSERVATION. The call and the put of a straddle are one
   trade, not two; they are summed into a single event P&L before any statistic is
   computed. Pooling the legs would inflate every t by ~sqrt(2) for free.
   Events also cluster hard in time (earnings season, and several mega-caps reporting on
   the same night). So every headline is also recomputed CLUSTERED BY MOVE DAY: average
   the events sharing a move day into one observation, then run the statistics on the
   series of daily averages. That is the number to trust.

2. NO LOOKAHEAD. Explicitly, what is known at each decision point:
     - report date + am/pm timing: published in advance (get_earnings_calendar carries the
       same field for future dates), so it is available before the trade.
     - move day M   = the report date itself for an 'am' (before-open) report, or the NEXT
       trading day for a 'pm' (after-close) report.
     - entry day E  = the trading day BEFORE M. The fill is that day's close, which is
       strictly before the release in both cases.
     - strike       = the listed strike nearest the underlying's close on day E. That
       price is observed while the order is being worked and is by construction pre-event.
       It is same-bar, not forward-looking; nothing about the earnings outcome is used.
     - expiry       = the nearest listed expiration STRICTLY AFTER M, so the position is
       always closed with time value remaining and never settles. Chosen from the listed
       expiration calendar, which is static and known in advance.
   Exit is the close of day M. Nothing after M is used for anything except reporting.

3. SPLIT-ADJUSTMENT TRAP (caught, and it would have silently voided ~7 events).
   data/sp500_daily is SPLIT-ADJUSTED; the strikes that actually traded are not. NFLX
   shows a 87.00 adjusted close in Jan-2025 while the real ATM strike was 870.00. Strikes
   were resolved against the live expired-contract list, not computed, so a wrong strike
   surfaces as an empty instrument lookup rather than as a plausible wrong number.

4. COSTS ARE THE POINT, NOT A FOOTNOTE. Four fills per event (sell call, sell put, buy
   call, buy put). Cost is charged as a fraction of the premium actually transacted on
   each side: cost = (rt/2)*entry_premium + (rt/2)*exit_premium, where rt is the ROUND
   TRIP spread as a % of mid. rt is not invented here: the 2026-08-28 journal records
   live single-stock option spreads of 6-8% of mid on the liquid names this strategy would
   trade (MRVL 220P 6.06-9.14%, IREN band 3.5-11%, ESTC 15-19%), with 5-10%+ the working
   range. So 8% is the realistic case, 4% a generous "top-of-book on the most liquid ATM
   contract" case, 12% a stress case, and 0% is printed only as an upper bound.
   Per-contract regulatory/exchange fees (~$0.03-0.08 per contract per side, ~$0.25 per
   straddle round trip) are an order of magnitude smaller than the spread and are ignored;
   noting them so it is clear they were considered and not forgotten.

5. THE TAIL IS THE RESULT. Short vol wins small and often, then loses enormous and rarely.
   A mean or a Sharpe computed over 270 events hides that by construction. This file
   therefore reports the full distribution, the single worst events by dollars, and total
   P&L with the worst 1/2/3/5 events deleted, on every cost scenario.

KNOWN DATA LIMITS (stated, not worked around)
  - Option daily CLOSE = last trade, not mid, not settlement. On a thin strike the last
    print can sit at the bid or the ask, which adds noise to BOTH entry and exit and is
    NOT the same thing as the spread cost modelled above. get_option_quotes and the Greeks
    endpoints are live-only -- there is no historical bid/ask or historical IV available
    through this API -- so a mid-price reconstruction is impossible and a stated spread
    assumption is the only honest option.
  - Guard against the worst of that noise: PUT-CALL PARITY. For a European-ish ATM pair,
    C - P should equal S - K to within carry. Events whose parity error exceeds
    --parity-max (default 2.5% of spot) on either the entry or the exit bar are excluded
    as stale/erroneous prints, and the count is reported. --parity-max 999 disables it.
  - 2 of 272 events (NVDA and CRM, both moving on 2026-02-26) are dropped outright: the
    vendor returns interpolated=true for every contract on that date, i.e. there is no
    exit bar to price against.
  - Universe = 40 large caps that are S&P 500 members TODAY. Survivorship applies, but it
    bites far less here than in a directional study: this bet is on move size, not on
    whether the company survived, and a delisted name would if anything have had LARGER
    earnings moves (i.e. the bias runs AGAINST the short-vol side, not for it).
  - Both years are bull markets. No 2008/2020-style vol regime is in the sample.

Usage:
  python3 tools/earnings_vol_backtest.py
  python3 tools/earnings_vol_backtest.py --parity-max 999      # no data-quality filter
  python3 tools/earnings_vol_backtest.py --dte-split           # split by DTE at entry
"""
import argparse, csv, math, os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EO   = os.path.join(ROOT, 'data', 'earnings_options')
BARS = os.path.join(ROOT, 'data', 'sp500_daily')
MULT = 100.0                      # option contract multiplier
COSTS = (0.00, 0.04, 0.08, 0.12)  # round-trip spread as a fraction of mid


def load_bars(sym):
    d = {}
    with open(os.path.join(BARS, sym + '.csv')) as f:
        for r in csv.DictReader(f):
            d[r['d']] = (float(r['o']), float(r['h']), float(r['l']), float(r['c']))
    return d


def mean(x):
    return sum(x) / len(x) if x else float('nan')


def sd(x):
    n = len(x)
    if n < 2:
        return float('nan')
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))


def tstat(x):
    s = sd(x)
    return mean(x) / (s / math.sqrt(len(x))) if s and len(x) > 1 else float('nan')


def pct(x, q):
    if not x:
        return float('nan')
    y = sorted(x)
    i = q * (len(y) - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return y[lo] + (y[hi] - y[lo]) * (i - lo)


def corr(a, b):
    if len(a) < 3:
        return float('nan')
    ma, mb, sa, sb = mean(a), mean(b), sd(a), sd(b)
    if not sa or not sb:
        return float('nan')
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / ((len(a) - 1) * sa * sb)


def build(parity_max):
    work  = list(csv.DictReader(open(os.path.join(EO, 'worklist.csv'))))
    inst  = {int(r['row']): r for r in csv.DictReader(open(os.path.join(EO, 'instruments.csv')))}
    px    = {int(r['row']): r for r in csv.DictReader(open(os.path.join(EO, 'prices.csv')))}
    spy   = load_bars('SPY')
    cache = {}
    events, dropped_gap, dropped_parity = [], [], []

    for i, w in enumerate(work):
        if i not in px:
            dropped_gap.append((w['symbol'], w['move_day']))
            continue
        sym = w['symbol']
        if sym not in cache:
            cache[sym] = load_bars(sym)
        ub = cache[sym]
        E, M, K = w['entry_day'], w['move_day'], float(inst[i]['strike'])
        # underlying: cached bars are SPLIT-ADJUSTED, strikes are not. Rescale spot into
        # the contract's own (unadjusted) price space using the strike-selection ratio.
        adj_e, adj_m = ub[E][3], ub[M][3]
        scale = 1.0
        adj_k = float(w['strike'])
        if adj_k > 0 and abs(K / adj_k - 1.0) > 0.10:      # a split lives between them
            scale = K / adj_k
        Se, Sm = adj_e * scale, adj_m * scale

        p = px[i]
        ce, cx = float(p['call_entry']), float(p['call_exit'])
        pe, pxx = float(p['put_entry']), float(p['put_exit'])
        prem_in, prem_out = ce + pe, cx + pxx
        if prem_in <= 0:
            dropped_gap.append((sym, M))
            continue

        # put-call parity data-quality screen (both bars)
        par_e = abs((ce - pe) - (Se - K)) / Se
        par_x = abs((cx - pxx) - (Sm - K)) / Sm
        parity = max(par_e, par_x)
        if parity > parity_max:
            dropped_parity.append((sym, M, parity))
            continue

        move = adj_m / adj_e - 1.0
        spy_r = (spy[M][3] / spy[E][3] - 1.0) if (M in spy and E in spy) else float('nan')
        events.append(dict(
            row=i, symbol=sym, report=w['report_date'], timing=w['timing'],
            entry_day=E, move_day=M, expiry=w['expiry'], dte=int(w['dte_entry']),
            strike=K, spot_entry=Se, spot_exit=Sm,
            prem_in=prem_in, prem_out=prem_out, parity=parity,
            move=move, abs_move=abs(move), spy=spy_r,
            implied=prem_in / Se,             # straddle as a fraction of spot = priced move
            intrinsic_exit=abs(Sm - K),       # what the straddle is worth at exit if vol were 0
            tv_exit=prem_out - abs(Sm - K),   # residual TIME VALUE still in the position at exit
            spot_expiry=(ub[w['expiry']][3] * scale) if w['expiry'] in ub else float('nan'),
        ))
    return events, dropped_gap, dropped_parity


def spread_cost(ev, rt):
    """Dollar cost of crossing the spread on all four fills, per 1-contract straddle."""
    return ((rt / 2.0) * ev['prem_in'] + (rt / 2.0) * ev['prem_out']) * MULT


def pnl(ev, rt):
    """SHORT-straddle P&L in DOLLARS per 1-contract straddle, net of a round-trip spread rt."""
    return (ev['prem_in'] - ev['prem_out']) * MULT - spread_cost(ev, rt)


def pnl_long(ev, rt):
    """LONG-straddle P&L. NOT the negative of pnl(): both sides PAY the spread.

    Negating the short side's net P&L would hand the buyer the spread as a credit, which
    would make costs look like they help both sides at once -- an obvious impossibility,
    and the bug this function exists to make impossible. Gross P&L is antisymmetric; the
    cost is symmetric and always subtracted.
    """
    return (ev['prem_out'] - ev['prem_in']) * MULT - spread_cost(ev, rt)


def pnl_expiry(ev, rt):
    """Variant B: SELL the straddle at the day-E close and simply let it expire.

    Removes the residual-time-value drag that variant A pays to buy the position back with
    days of life still in it, at the price of carrying several extra sessions of direction
    risk (and, for a real short position, assignment). Only ONE side of the spread is paid,
    because nothing is bought back. Uses the underlying's split-adjusted close on the
    expiration date, rescaled into the contract's own price space.
    """
    if math.isnan(ev['spot_expiry']):
        return float('nan')
    settle = abs(ev['spot_expiry'] - ev['strike'])
    return (ev['prem_in'] * (1 - rt / 2.0) - settle) * MULT


def distribution(vals, label):
    wins = [v for v in vals if v > 0]
    loss = [v for v in vals if v <= 0]
    print('  %-14s n=%3d  total $%+10.0f  mean $%+8.2f  median $%+8.2f  sd $%8.0f' %
          (label, len(vals), sum(vals), mean(vals), pct(vals, 0.5), sd(vals)))
    print('  %-14s win %5.1f%%  avg win $%+8.2f  avg loss $%+9.2f  t(event)=%+5.2f' %
          ('', 100.0 * len(wins) / len(vals), mean(wins) if wins else 0.0,
           mean(loss) if loss else 0.0, tstat(vals)))
    print('  %-14s p05 $%+9.0f  p25 $%+8.0f  p75 $%+8.0f  p95 $%+9.0f  min $%+9.0f  max $%+9.0f' %
          ('', pct(vals, .05), pct(vals, .25), pct(vals, .75), pct(vals, .95),
           min(vals), max(vals)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parity-max', type=float, default=0.025)
    ap.add_argument('--dte-split', action='store_true')
    a = ap.parse_args()

    events, gap, par = build(a.parity_max)
    print('=' * 100)
    print('EARNINGS VOLATILITY BACKTEST  -- short vs long ATM straddle across the print')
    print('=' * 100)
    print('universe            40 S&P 500 large caps, all with liquid weekly/monthly options')
    print('events built        272   (40 symbols x up to 7 reported quarters)')
    print('dropped, no bar     %-3d  %s' % (len(gap), ', '.join('%s %s' % g[:2] for g in gap)))
    print('dropped, parity>%.1f%% %-3d  (last-trade closes inconsistent with C-P = S-K)'
          % (100 * a.parity_max, len(par)))
    print('EVENTS ANALYSED     %d' % len(events))
    print('window              %s .. %s' % (min(e['move_day'] for e in events),
                                            max(e['move_day'] for e in events)))
    print('distinct move days  %d   (events per day %.2f)'
          % (len(set(e['move_day'] for e in events)),
             len(events) / len(set(e['move_day'] for e in events))))
    print()
    print('--- what the market priced vs what happened -------------------------------------')
    imp = [100 * e['implied'] for e in events]
    rea = [100 * e['abs_move'] for e in events]
    print('  straddle premium at entry, %% of spot   mean %5.2f%%  median %5.2f%%' % (mean(imp), pct(imp, .5)))
    print('  realised |move| entry->exit,  %% of spot mean %5.2f%%  median %5.2f%%' % (mean(rea), pct(rea, .5)))
    print('  realised move exceeded the straddle in %d of %d events (%.1f%%)'
          % (sum(1 for e in events if e['abs_move'] > e['implied']), len(events),
             100.0 * sum(1 for e in events if e['abs_move'] > e['implied']) / len(events)))
    print()

    for rt in COSTS:
        vals = [pnl(e, rt) for e in events]
        print('--- ROUND-TRIP SPREAD %.0f%% of mid %s' % (100 * rt, '-' * 58))
        distribution(vals, 'SHORT straddle')
        distribution([pnl_long(e, rt) for e in events], 'LONG  straddle')
        # cluster by move day: one observation per day
        byday = defaultdict(list)
        for e, v in zip(events, vals):
            byday[e['move_day']].append(v)
        daily = [mean(v) for v in byday.values()]
        print('  clustered by MOVE DAY: n=%d days  mean $%+8.2f  t=%+5.2f   (short side)'
              % (len(daily), mean(daily), tstat(daily)))
        # tail surgery
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        tot = sum(vals)
        line = '  total $%+9.0f' % tot
        for k in (1, 2, 3, 5):
            line += '   drop worst %d: $%+9.0f' % (k, tot - sum(vals[i] for i in order[:k]))
        print(line + '   (short side)')
        print()

    rt = 0.08
    vals = [pnl(e, rt) for e in events]
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    print('--- WORST 8 EVENTS FOR THE SHORT SIDE (at the realistic 8% round trip) ----------')
    print('  %-6s %-10s %-9s %8s %8s %9s %9s %10s' %
          ('sym', 'move day', 'strike', 'priced%', 'moved%', 'prem in', 'prem out', 'P&L $'))
    for i in order[:8]:
        e = events[i]
        print('  %-6s %-10s %9.2f %7.2f%% %+7.2f%% %9.2f %9.2f %+10.0f' %
              (e['symbol'], e['move_day'], e['strike'], 100 * e['implied'],
               100 * e['move'], e['prem_in'], e['prem_out'], vals[i]))
    print()
    print('--- BEST 5 EVENTS FOR THE SHORT SIDE ---------------------------------------------')
    for i in order[-5:][::-1]:
        e = events[i]
        print('  %-6s %-10s %9.2f %7.2f%% %+7.2f%% %9.2f %9.2f %+10.0f' %
              (e['symbol'], e['move_day'], e['strike'], 100 * e['implied'],
               100 * e['move'], e['prem_in'], e['prem_out'], vals[i]))
    print()

    print("--- WHERE THE SHORT SIDE'S MONEY GOES (means, % of spot, per event) ------------")
    print('  premium SOLD at entry                     %+6.2f%%' % (100 * mean([e['implied'] for e in events])))
    print('  INTRINSIC value bought back at exit       -%5.2f%%' % (100 * mean([e['intrinsic_exit'] / e['spot_entry'] for e in events])))
    print('  RESIDUAL TIME VALUE bought back at exit   -%5.2f%%  <- position is CLOSED with ~%d'
          % (100 * mean([e['tv_exit'] / e['spot_entry'] for e in events]),
             round(mean([e['dte'] for e in events]) - 1)))
    print('                                                    days of life left, not settled')
    print('  spread paid, 8%% round trip                -%5.2f%%'
          % (100 * mean([(0.04 * e['prem_in'] + 0.04 * e['prem_out']) / e['spot_entry'] for e in events])))
    print('  = net short-straddle edge                 %+6.2f%% of spot per event'
          % (100 * mean([pnl(e, 0.08) / MULT / e['spot_entry'] for e in events])))
    print()

    print('--- VARIANT B: SELL AND LET IT EXPIRE (no buy-back, one-way spread only) ---------')
    for rtb in (0.00, 0.04, 0.08):
        vb = [pnl_expiry(e, rtb) for e in events if not math.isnan(pnl_expiry(e, rtb))]
        wins = [v for v in vb if v > 0]
        ob = sorted(range(len(vb)), key=lambda i: vb[i])
        bd = defaultdict(list)
        for e, v in zip([e for e in events if not math.isnan(e['spot_expiry'])], vb):
            bd[e['move_day']].append(v)
        dl = [mean(v) for v in bd.values()]
        print('  spread %2.0f%%  n=%3d  total $%+9.0f  mean $%+8.2f  median $%+8.2f  win %5.1f%%  t(event)=%+5.2f  t(day)=%+5.2f'
              % (100 * rtb, len(vb), sum(vb), mean(vb), pct(vb, .5),
                 100.0 * len(wins) / len(vb), tstat(vb), tstat(dl)))
        print('             worst $%+9.0f   drop worst 1: $%+9.0f  drop worst 3: $%+9.0f  drop worst 5: $%+9.0f'
              % (min(vb), sum(vb) - vb[ob[0]], sum(vb) - sum(vb[i] for i in ob[:3]),
                 sum(vb) - sum(vb[i] for i in ob[:5])))
    print()

    print('--- NORMALISED: P&L AS % OF SPOT (equal risk per event, not equal contracts) ----')
    print('  One contract of NFLX at $1,250 carries ~50x the notional of one PFE contract at')
    print('  $25, so an equal-CONTRACT dollar total is really a bet on the biggest names.')
    print('  Dividing each event by its own spot equal-weights them.')
    for rtn in (0.00, 0.04, 0.08, 0.12):
        vn = [100 * pnl(e, rtn) / MULT / e['spot_entry'] for e in events]
        bd = defaultdict(list)
        for e, v in zip(events, vn):
            bd[e['move_day']].append(v)
        dl = [mean(v) for v in bd.values()]
        on = sorted(range(len(vn)), key=lambda i: vn[i])
        tot = sum(vn)
        print('  spread %2.0f%%  mean %+6.3f%%  median %+6.3f%%  sd %5.2f%%  win %5.1f%%  t(event)=%+5.2f  t(day)=%+5.2f'
              % (100 * rtn, mean(vn), pct(vn, .5), sd(vn),
                 100.0 * sum(1 for v in vn if v > 0) / len(vn), tstat(vn), tstat(dl)))
        print('             sum %+7.1f%%   drop worst 1: %+7.1f%%  drop worst 3: %+7.1f%%  drop worst 5: %+7.1f%%'
              % (tot, tot - vn[on[0]], tot - sum(vn[i] for i in on[:3]),
                 tot - sum(vn[i] for i in on[:5])))
    vn8 = [100 * pnl(e, 0.08) / MULT / e['spot_entry'] for e in events]
    on = sorted(range(len(vn8)), key=lambda i: vn8[i])
    print('  worst 5 normalised (8% spread): ' + '  '.join(
        '%s %s %.1f%%' % (events[i]['symbol'], events[i]['move_day'], vn8[i]) for i in on[:5]))
    print()

    print('--- THE LONG SIDE, NORMALISED (% of spot, equal risk per event) -----------------')
    for rtn in (0.00, 0.04, 0.08, 0.12):
        vl = [100 * pnl_long(e, rtn) / MULT / e['spot_entry'] for e in events]
        bd = defaultdict(list)
        for e, v in zip(events, vl):
            bd[e['move_day']].append(v)
        dl = [mean(v) for v in bd.values()]
        ol = sorted(range(len(vl)), key=lambda i: vl[i])
        print('  spread %2.0f%%  mean %+6.3f%%  median %+6.3f%%  win %5.1f%%  t(event)=%+5.2f  t(day)=%+5.2f  best +%.1f%% (%s %s)'
              % (100 * rtn, mean(vl), pct(vl, .5),
                 100.0 * sum(1 for v in vl if v > 0) / len(vl), tstat(vl), tstat(dl),
                 vl[ol[-1]], events[ol[-1]]['symbol'], events[ol[-1]]['move_day']))
    print()

    print('--- IS IT MARKET-NEUTRAL? -------------------------------------------------------')
    ok = [i for i in range(len(events)) if not math.isnan(events[i]['spy'])]
    v  = [vals[i] for i in ok]
    print('  corr(short P&L, SAME-DAY underlying move)      %+6.3f' % corr(v, [events[i]['move'] for i in ok]))
    print('  corr(short P&L, |same-day underlying move|)    %+6.3f' % corr(v, [events[i]['abs_move'] for i in ok]))
    print('  corr(short P&L, SPY same-day return)           %+6.3f' % corr(v, [events[i]['spy'] for i in ok]))
    up = [vals[i] for i in ok if events[i]['move'] > 0]
    dn = [vals[i] for i in ok if events[i]['move'] <= 0]
    print('  mean short P&L on UP prints   $%+8.2f (n=%d)' % (mean(up), len(up)))
    print('  mean short P&L on DOWN prints $%+8.2f (n=%d)' % (mean(dn), len(dn)))
    print()

    print('--- PER-SYMBOL, short side at 8% (n>=6 only) ------------------------------------')
    bysym = defaultdict(list)
    for e, x in zip(events, vals):
        bysym[e['symbol']].append(x)
    rows = sorted(((s, mean(x), sum(x), len(x)) for s, x in bysym.items() if len(x) >= 6),
                  key=lambda r: r[1])
    for s, m, t, n in rows:
        print('  %-6s n=%d  mean $%+8.2f  total $%+9.0f' % (s, n, m, t))
    print()

    if a.dte_split:
        print('--- BY DTE AT ENTRY, short side at 8% -------------------------------------------')
        byd = defaultdict(list)
        for e, x in zip(events, vals):
            byd['2-4d' if e['dte'] <= 4 else '6-9d'].append(x)
        for k in sorted(byd):
            print('  %-6s n=%3d  mean $%+8.2f  win %5.1f%%  total $%+9.0f'
                  % (k, len(byd[k]), mean(byd[k]),
                     100.0 * sum(1 for x in byd[k] if x > 0) / len(byd[k]), sum(byd[k])))
        print()


if __name__ == '__main__':
    main()
