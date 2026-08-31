#!/usr/bin/env python3
"""Backtest: buy the N biggest one-day losers in the S&P 500 at the close, sell at
the next close. N = 1, 3, 5, 10. Window: ~1 year (default 2025-08-28 .. 2026-08-27).

METHODOLOGY NOTES — the parts that are easy to get wrong, and how this file handles them
=======================================================================================

1. CLUSTER BY DAY, NOT BY LEG.
   The N names bought on a given day are ONE observation, not N. They share the same
   market shock (biggest-loser days cluster on selloffs) so their legs are strongly
   cross-correlated. This file forms each day's WEIGHTED BASKET RETURN first and runs
   every statistic on the SERIES OF DAILY BASKET RETURNS (n = number of trading days,
   ~250). Pooling individual legs would inflate t by roughly sqrt(N).

2. BENCHMARK AGAINST THE SAME DAY'S UNIVERSE.
   The counterfactual is what the REST of the index did on the SAME next day, not the
   all-period average. Loser days cluster on market-wide down days and the whole index
   tends to bounce, so an unconditional baseline measures market timing and mislabels it
   stock selection. For every variant we report raw basket return, the same-day
   equal-weighted return of the whole eligible universe, and the EXCESS (basket minus
   universe, same day). The EXCESS is the headline; raw is decoration.

3. STATISTICS. mean, sd (sample), t = mean / (sd/sqrt(n)), and annualized Sharpe =
   mean/sd * sqrt(252), all on the daily series described above.

4. ENTRY TIMING / LOOKAHEAD. The stated rule needs the close to rank the losers and then
   fills at that same close. That is not executable: a market-on-close order must be in
   before roughly 15:50 ET, so you commit before the ranking is known. Two entry variants
   are computed:
     close  = buy at day t close, sell at day t+1 close   (the stated, LOOKAHEAD rule)
     open   = buy at day t+1 OPEN,  sell at day t+1 close  (executable; ranking is known)
   The gap between them is the size of the lookahead problem.

5. WEIGHTING. equal, w ∝ |drop|, w ∝ sqrt(|drop|), normalized to 1 within the day's
   basket. Drop-weighting mechanically concentrates into the highest-volatility names and
   raises the basket sd, so it must be judged on Sharpe/t of the excess, not mean return.

6. COSTS. Round-trip cost is subtracted from the basket (hence from the excess) at 5bp
   and 10bp. The universe benchmark is a costless reference line, not a tradable arm.

7. SURVIVORSHIP. data/sp500_members.csv is TODAY'S membership. Names deleted from the
   index during the window are absent, and deletions are disproportionately bad
   performers — which biases a buy-the-losers strategy UPWARD. This cannot be corrected
   without point-in-time membership; results are an UPPER BOUND. The one correction that
   IS possible is on the addition side: --pit excludes a name on days before its
   date_added. Both are reported.

Usage:
  python3 tools/sp500_losers_backtest.py                 # full report
  python3 tools/sp500_losers_backtest.py --no-pit        # ignore date_added filter
  python3 tools/sp500_losers_backtest.py --start 2025-08-28 --end 2026-08-27
  python3 tools/sp500_losers_backtest.py --max-drop 0.50 # treat worse as data artifact
"""
import argparse, csv, math, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BARS = os.path.join(ROOT, 'data', 'sp500_daily')
MEMBERS = os.path.join(ROOT, 'data', 'sp500_members.csv')
NS = ( 1, 3, 5, 10 )
WEIGHTS = ('equal', 'drop', 'sqrtdrop')
TRADING_DAYS = 252


# ---------------------------------------------------------------- data loading
def load_members(path=MEMBERS):
    rows = list(csv.DictReader(l for l in open(path) if not l.startswith('#')))
    return {r['symbol']: r['date_added'] for r in rows}


def load_bars(symbols):
    """{sym: {date: (o,h,l,c,v)}} plus the sorted date list per symbol."""
    px, missing = {}, []
    for s in sorted(symbols):
        p = os.path.join(BARS, f'{s}.csv')
        if not os.path.exists(p):
            missing.append(s); continue
        d = {}
        for r in csv.DictReader(open(p)):
            try:
                d[r['d']] = (float(r['o']), float(r['h']), float(r['l']), float(r['c']), float(r['v']))
            except ValueError:
                continue
        if d:
            px[s] = d
        else:
            missing.append(s)
    return px, missing


# ---------------------------------------------------------------- stats
def stats(xs):
    n = len(xs)
    if n < 2:
        return dict(n=n, mean=float('nan'), sd=float('nan'), t=float('nan'), sharpe=float('nan'))
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    sd = math.sqrt(var)
    t = m / (sd / math.sqrt(n)) if sd > 0 else float('nan')
    sharpe = (m / sd) * math.sqrt(TRADING_DAYS) if sd > 0 else float('nan')
    return dict(n=n, mean=m, sd=sd, t=t, sharpe=sharpe)


def weights_for(drops, scheme):
    """drops = list of DROP MAGNITUDES (positive = fell that much). Returns weights summing to 1."""
    k = len(drops)
    if scheme == 'equal':
        return [1.0 / k] * k, False
    pos = [max(d, 0.0) for d in drops]
    if scheme == 'sqrtdrop':
        pos = [math.sqrt(d) for d in pos]
    s = sum(pos)
    if s <= 0:                       # every "loser" was actually up: degenerate, fall back
        return [1.0 / k] * k, True
    return [p / s for p in pos], False


# ---------------------------------------------------------------- core
def build_panel(px, members, start, end, pit, max_drop):
    """Return list of per-day dicts with the ranking signal and both forward returns."""
    all_dates = sorted({d for s in px for d in px[s]})
    idx = {d: i for i, d in enumerate(all_dates)}
    days = []
    artifacts = []
    for i, t in enumerate(all_dates):
        if t < start or t > end:
            continue
        if i == 0 or i + 1 >= len(all_dates):
            continue
        prev, nxt = all_dates[i - 1], all_dates[i + 1]
        rows = []
        for s, d in px.items():
            if pit and members.get(s, '9999') > t:
                continue            # not in the index yet on day t
            b_prev, b_t, b_n = d.get(prev), d.get(t), d.get(nxt)
            if not (b_prev and b_t and b_n):
                continue
            c_prev, c_t, o_n, c_n = b_prev[3], b_t[3], b_n[0], b_n[3]
            if min(c_prev, c_t, o_n, c_n) <= 0:
                continue
            r = c_t / c_prev - 1.0
            if max_drop and abs(r) > max_drop:
                artifacts.append((t, s, r)); continue
            rows.append(dict(sym=s, ret=r,
                             fwd_close=c_n / c_t - 1.0,     # buy at t close
                             fwd_open=c_n / o_n - 1.0))     # buy at t+1 open
        if len(rows) < 50:
            continue
        rows.sort(key=lambda x: x['ret'])
        days.append(dict(date=t, rows=rows,
                         uni_close=sum(x['fwd_close'] for x in rows) / len(rows),
                         uni_open=sum(x['fwd_open'] for x in rows) / len(rows),
                         uni_today=sum(x['ret'] for x in rows) / len(rows)))
    return days, artifacts


def series(days, n, scheme, entry):
    """Daily basket, universe and excess return series for one variant."""
    key = 'fwd_close' if entry == 'close' else 'fwd_open'
    ukey = 'uni_close' if entry == 'close' else 'uni_open'
    basket, uni, exc, degen = [], [], [], 0
    for d in days:
        picks = d['rows'][:n]
        if len(picks) < n:
            continue
        w, fell_back = weights_for([-p['ret'] for p in picks], scheme)
        degen += fell_back
        b = sum(wi * p[key] for wi, p in zip(w, picks))
        basket.append(b); uni.append(d[ukey]); exc.append(b - d[ukey])
    return basket, uni, exc, degen


# ---------------------------------------------------------------- reporting
def fmt_pct(x):
    return f'{100*x:+.4f}%'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2025-08-28')
    ap.add_argument('--end', default='2026-08-27')
    ap.add_argument('--no-pit', action='store_true',
                    help='do NOT apply the date_added point-in-time filter')
    ap.add_argument('--max-drop', type=float, default=0.50,
                    help='|1-day return| above this is treated as a data artifact and dropped (0 = keep all)')
    ap.add_argument('--costs', default='0,5,10', help='round-trip cost scenarios in bp')
    a = ap.parse_args()

    members = load_members()
    px, missing = load_bars(members)
    print(f'universe file: {len(members)} S&P 500 members (today\'s membership)')
    print(f'bars loaded  : {len(px)} symbols; MISSING/NO DATA: {len(missing)} {missing}')

    days, artifacts = build_panel(px, members, a.start, a.end, not a.no_pit, a.max_drop)
    print(f'trading days : {len(days)} signal days from {days[0]["date"]} to {days[-1]["date"]}'
          f'  (entry day t, exit day t+1)')
    print(f'universe size: min {min(len(d["rows"]) for d in days)}, '
          f'median {sorted(len(d["rows"]) for d in days)[len(days)//2]}, '
          f'max {max(len(d["rows"]) for d in days)} eligible names per day')
    print(f'point-in-time additions filter: {"OFF" if a.no_pit else "ON (date_added <= t)"}')
    if artifacts:
        print(f'data artifacts dropped (|1d move| > {a.max_drop:.0%}): {len(artifacts)}')
        for t, s, r in sorted(artifacts, key=lambda x: x[2])[:12]:
            print(f'   {t} {s:6s} {100*r:+.1f}%')

    # how selloff-clustered are the loser days? (motivates the same-day benchmark)
    down = sum(1 for d in days if d['uni_today'] < 0)
    print(f'\nof {len(days)} signal days the equal-weighted universe was DOWN on {down} '
          f'({100*down/len(days):.0f}%); mean same-day universe move '
          f'{fmt_pct(sum(d["uni_today"] for d in days)/len(days))}')
    print('mean drop of the picked names on the signal day (equal weight):')
    for n in NS:
        m = sum(sum(p['ret'] for p in d['rows'][:n]) / n for d in days) / len(days)
        print(f'   N={n:<3d} {fmt_pct(m)}')

    costs = [float(c) / 10000.0 for c in a.costs.split(',')]

    for entry, label in (('close', 'ENTRY AT DAY-t CLOSE  (the stated rule -- USES LOOKAHEAD)'),
                         ('open',  'ENTRY AT DAY-t+1 OPEN (executable; ranking known before entry)')):
        print('\n' + '=' * 108)
        print(label)
        print('=' * 108)
        print(f'{"N":>3} {"weight":<9} {"n":>4} {"raw mean":>11} {"raw sd":>9} '
              f'{"uni mean":>11} {"exc mean":>11} {"exc sd":>9} {"t(exc)":>7} {"Sharpe":>7}  '
              + '  '.join(f'{"exc-"+str(int(c*10000))+"bp":>11}' for c in costs[1:]))
        for n in NS:
            schemes = WEIGHTS if n > 1 else ('equal',)
            for scheme in schemes:
                b, u, e, degen = series(days, n, scheme, entry)
                sb, su, se = stats(b), stats(u), stats(e)
                net = '  '.join(f'{fmt_pct(se["mean"]-c):>11}' for c in costs[1:])
                print(f'{n:>3} {scheme:<9} {se["n"]:>4} {fmt_pct(sb["mean"]):>11} {100*sb["sd"]:>8.3f}% '
                      f'{fmt_pct(su["mean"]):>11} {fmt_pct(se["mean"]):>11} {100*se["sd"]:>8.3f}% '
                      f'{se["t"]:>7.2f} {se["sharpe"]:>7.2f}  {net}'
                      + (f'   [{degen} degenerate-weight days]' if degen else ''))

    # matrix view: excess mean and t, rows N, columns weighting scheme
    for entry in ('close', 'open'):
        print(f'\nMATRIX -- daily EXCESS vs same-day universe, entry={entry} '
              f'(cell = mean excess / t / annualized Sharpe)')
        print(f'{"N":>3} | ' + ' | '.join(f'{w:^30}' for w in WEIGHTS))
        for n in NS:
            cells = []
            for scheme in WEIGHTS:
                if n == 1 and scheme != 'equal':
                    cells.append(f'{"(same as equal)":^30}'); continue
                _, _, e, _ = series(days, n, scheme, entry)
                s = stats(e)
                cells.append(f'{fmt_pct(s["mean"]):>10}  t={s["t"]:+5.2f}  Sh={s["sharpe"]:+5.2f}')
            print(f'{n:>3} | ' + ' | '.join(cells))

    # ---- robustness: is any of this driven by a handful of days? -------------
    print('\nROBUSTNESS (equal weight): median daily excess, share of positive days, and the mean')
    print('after deleting the 1 and 3 largest-|excess| days -- a real edge should not live in 1% of the sample.')
    print(f'{"entry":<6} {"N":>3} {"mean exc":>10} {"median":>10} {"%days>0":>8} {"drop-1":>10} {"drop-3":>10}')
    for entry in ('close', 'open'):
        for n in NS:
            _, _, e, _ = series(days, n, 'equal', entry)
            srt = sorted(e, key=lambda x: -abs(x))
            m1 = sum(srt[1:]) / (len(srt) - 1)
            m3 = sum(srt[3:]) / (len(srt) - 3)
            med = sorted(e)[len(e) // 2]
            pos = 100.0 * sum(1 for x in e if x > 0) / len(e)
            print(f'{entry:<6} {n:>3} {fmt_pct(sum(e)/len(e)):>10} {fmt_pct(med):>10} '
                  f'{pos:>7.1f}% {fmt_pct(m1):>10} {fmt_pct(m3):>10}')

    nvar = len(NS) * len(WEIGHTS) - 2   # N=1 has only one distinct scheme
    print(f'\nVARIANTS TESTED per entry timing: {nvar} '
          f'({len(NS)} basket sizes x {len(WEIGHTS)} weightings, N=1 collapses to one). '
          f'Across both entry timings: {2*nvar}. The best of {2*nvar} is expected to look '
          f'good by chance; do not select on the outcome.')


if __name__ == '__main__':
    main()
