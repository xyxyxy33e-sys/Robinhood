#!/usr/bin/env python3
"""Does buying the N biggest S&P 500 daily losers, every day, actually BEAT THE
INDEX? Two non-overlapping 1-year windows, a real compounded equity curve, and
SPY — the actual investable index — as the competitor.

This is the third tool on this strategy family today. sp500_losers_backtest.py
measured mean daily EXCESS vs an equal-weight universe of the same picks;
sp500_losers_hold.py measured multi-day holds and found the apparent edge was
leveraged beta. Neither answered the owner's actual question, which is whether
a dollar in this strategy ends up ahead of a dollar in SPY. That needs a
compounded curve and a real index benchmark, which is what this file builds.

METHODOLOGY — every choice, and why
===================================

1. ENTRY IS THE NEXT OPEN. NO CLOSE-ENTRY RESULT IS REPORTED AS TRADABLE.
   Ranking the day's losers requires day-t's close. A market-on-close order has
   to be in ~15:50 ET, before the ranking exists, so "buy at the t close" is
   lookahead. Today's 1-year study measured that lookahead at 13-23bp/day —
   larger than the entire apparent edge. So the headline curve here is:
       rank at day-t close -> BUY at day-(t+1) OPEN -> SELL at day-(t+1) CLOSE.
   A close-entry curve is still computed, labelled LOOKAHEAD, purely to keep
   the size of the bias visible next to the tradable number.

2. THE CURVE IS COMPOUNDED, NOT AVERAGED. Start at $10,000. On each trade day
   the ENTIRE current equity goes into that day's basket, equal-weighted across
   the N names, and the day's basket return is multiplied into equity. A mean
   daily return hides both the volatility drag and the fact that costs compound.

3. CASH RULE, STATED EXPLICITLY. On any trade day where the panel is unusable —
   fewer than 50 eligible names with a valid prev-close/close/next-open/
   next-close chain, or fewer than N ranked names — the strategy earns EXACTLY
   0% (holds cash) and pays NO cost. Such days are counted and printed. They
   are NOT skipped: skipping would silently shorten the window and flatter the
   CAGR. The benchmarks still earn their return on those days.

4. THE BENCHMARK IS SPY, THE THING YOU COULD OTHERWISE BUY. Buy-and-hold SPY
   over the IDENTICAL set of trade dates, close-to-close, split-adjusted.
   (Split-adjusted only: SPY's ~1.2%/yr dividend is NOT in these bars, so the
   SPY line understates the real index total return by roughly that much. Every
   comparison below is therefore generous to the strategy.) The equal-weight
   universe-of-picks line from the earlier tools is kept as a third column for
   continuity, but it is not investable and is not the verdict.

5. BETA/ALPHA vs SPY, BECAUSE THAT IS WHAT KILLED THE LAST VERSION. Today's
   hold study found double-digit "excess" that was entirely 3-11x market beta
   in a +27% year. Same check here, against the real index:
       beta  = cov(strat, spy) / var(spy)
       alpha = mean(strat) - beta * mean(spy)      [daily; x252 to annualize]
   with a t-stat on alpha from the regression residuals. TWO market series are
   reported because the exposure windows differ:
       SPY c2c (close-to-close) — what a buy-and-hold index investor earns, the
           right yardstick for total return, but a MISMATCHED regressor: the
           strategy is flat overnight and c2c includes the overnight move.
       SPY o2c (open-to-close)  — the market move over exactly the hours the
           strategy is invested. This is the honest CAPM regressor and the one
           the alpha verdict uses.
   Reporting only the flattering one of the two would repeat this morning's
   wrong-benchmark error, so both are printed side by side.

6. COSTS COMPOUND DAILY. This strategy does a FULL ROUND TRIP EVERY TRADING DAY
   — ~250 round trips a year, versus one per signal in the flip study. Cost is
   applied multiplicatively on every invested day: r_net = (1+r_gross)*(1-c)-1
   at c = 5bp and 10bp round trip. 10bp/day compounds to about -22%/yr of drag.
   Gross and net are printed side by side so the drag cannot hide inside a
   single headline number.

7. TWO NON-OVERLAPPING YEARS, REPORTED SEPARATELY.
       Year A 2024-08-28..2025-08-27 (backfilled today; out of sample)
       Year B 2025-08-28..2026-08-27 (the window every earlier test used)
   Pooling them would let a strong year carry a weak one. Windows are defined on
   the TRADE date (the day the money is actually at risk), so the curve dates and
   the SPY dates are the same set by construction.

   A third POOLED 2-year window is printed last. It is a summary, not the test:
   the two 1-year windows are the out-of-sample check on each other, and a
   pooled number can let one year carry the other.

9. SURVIVORSHIP — WORSE HERE THAN ANYWHERE ELSE TODAY, AND IT GROWS BACKWARD.
   data/sp500_members.csv is TODAY'S membership. Every name deleted from the
   index during a window is missing, and deletions skew hard to bad performers —
   precisely what a buy-the-losers rule buys. Year A is a further year back, so
   it has an EXTRA year of deletions scrubbed out of it and is MORE upward-biased
   than Year B. Any Year-A outperformance must be discounted harder than Year-B
   outperformance, not less. The additions half is partly correctable and is
   corrected (--pit, on by default: a name is ineligible before its date_added);
   the deletions half is not correctable without point-in-time membership data,
   which this repo does not have. All results are an UPPER BOUND.

10. WHAT "COMPETES WITH THE INDEX" MEANS HERE, decided before looking at output:
   net-of-5bp CAGR >= SPY CAGR over the same window AND alpha vs SPY o2c not
    negative. Both must hold. Beating SPY's CAGR while running 2x its volatility
   is leverage, not skill, and the alpha column is what separates them.

Usage:
  python3 tools/sp500_losers_equity_curve.py
  python3 tools/sp500_losers_equity_curve.py --weight drop
  python3 tools/sp500_losers_equity_curve.py --no-pit
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sp500_losers_backtest import (load_members, load_bars, weights_for, stats,
                                   build_panel, fmt_pct)

NS = (1, 3, 5, 10)
TRADING_DAYS = 252
START_EQUITY = 10_000.0
WINDOWS = (('Year A', '2024-08-28', '2025-08-27'),
           ('Year B', '2025-08-28', '2026-08-27'),
           ('Pooled 2y', '2024-08-28', '2026-08-27'))


# ------------------------------------------------------------------ helpers
def curve_metrics(rets, equity0=START_EQUITY):
    """Compound a daily return series and report the curve's statistics."""
    eq = equity0
    peak, mdd = equity0, 0.0
    path = []
    for r in rets:
        eq *= (1.0 + r)
        path.append(eq)
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1.0)
    n = len(rets)
    total = eq / equity0 - 1.0
    cagr = (eq / equity0) ** (TRADING_DAYS / n) - 1.0 if n and eq > 0 else float('nan')
    s = stats(rets)
    return dict(n=n, final=eq, total=total, cagr=cagr,
                vol=s['sd'] * math.sqrt(TRADING_DAYS),
                sharpe=s['sharpe'], mdd=mdd, mean=s['mean'], sd=s['sd'], path=path)


def beta_alpha(strat, mkt):
    """CAPM by cov/var on the daily series, with a residual t-stat on alpha."""
    n = len(strat)
    if n < 3:
        return dict(beta=float('nan'), alpha=float('nan'), alpha_ann=float('nan'), t=float('nan'))
    ms, mm = sum(strat) / n, sum(mkt) / n
    cov = sum((a - ms) * (b - mm) for a, b in zip(strat, mkt)) / (n - 1)
    var = sum((b - mm) ** 2 for b in mkt) / (n - 1)
    if var <= 0:
        return dict(beta=float('nan'), alpha=float('nan'), alpha_ann=float('nan'), t=float('nan'))
    beta = cov / var
    alpha = ms - beta * mm
    resid = [a - (alpha + beta * b) for a, b in zip(strat, mkt)]
    rss = sum(r * r for r in resid) / (n - 2)
    sxx = sum((b - mm) ** 2 for b in mkt)
    se = math.sqrt(rss * (1.0 / n + mm * mm / sxx)) if sxx > 0 else float('nan')
    t = alpha / se if se and se > 0 else float('nan')
    return dict(beta=beta, alpha=alpha, alpha_ann=(1 + alpha) ** TRADING_DAYS - 1, t=t)


def net(rets, invested, c):
    """Apply a round-trip cost multiplicatively on every INVESTED day only."""
    return [((1 + r) * (1 - c) - 1) if inv else r for r, inv in zip(rets, invested)]


# ------------------------------------------------------------------ core
def build(px, spy, members, start, end, pit, max_drop, scheme):
    """Per-trade-date returns for every N, plus the benchmark series.

    Trade date = t+1, the day capital is actually at risk. build_panel is
    re-used verbatim for the ranking panel; days it drops become cash days.
    """
    all_dates = sorted({d for s in px for d in px[s]})
    idx = {d: i for i, d in enumerate(all_dates)}
    # widen so a signal day just before `start` can supply a trade day inside it
    lo = all_dates[max(0, idx.get(start, 0) - 5)]
    days, _ = build_panel(px, members, lo, end, pit, max_drop)
    by_trade = {}
    for d in days:
        i = idx[d['date']]
        if i + 1 < len(all_dates):
            by_trade[all_dates[i + 1]] = d

    trade_dates = [d for d in all_dates if start <= d <= end and d in spy
                   and idx[d] > 0 and all_dates[idx[d] - 1] in spy]
    out = {n: [] for n in NS}
    look = {n: [] for n in NS}
    inv = {n: [] for n in NS}
    spy_c2c, spy_o2c, uni_ew, dates = [], [], [], []
    cash = {n: 0 for n in NS}
    for d in trade_dates:
        prev = all_dates[idx[d] - 1]
        so, sc, spc = spy[d][0], spy[d][3], spy[prev][3]
        spy_c2c.append(sc / spc - 1.0)
        spy_o2c.append(sc / so - 1.0)
        dates.append(d)
        day = by_trade.get(d)
        uni_ew.append(day['uni_open'] if day else 0.0)
        for n in NS:
            if not day or len(day['rows']) < n:
                out[n].append(0.0); look[n].append(0.0); inv[n].append(False)
                cash[n] += 1
                continue
            picks = day['rows'][:n]
            w, _ = weights_for([-p['ret'] for p in picks], scheme)
            out[n].append(sum(wi * p['fwd_open'] for wi, p in zip(w, picks)))
            look[n].append(sum(wi * p['fwd_close'] for wi, p in zip(w, picks)))
            inv[n].append(True)
    return dict(dates=dates, strat=out, look=look, inv=inv, cash=cash,
                spy_c2c=spy_c2c, spy_o2c=spy_o2c, uni_ew=uni_ew, by_trade=by_trade)


def report_window(label, start, end, px, spy, members, pit, max_drop, scheme, costs):
    b = build(px, spy, members, start, end, pit, max_drop, scheme)
    dates = b['dates']
    by_trade_lookup = b['by_trade']
    if not dates:
        print(f'\n{label}: NO DATA in {start}..{end}'); return
    print('\n' + '=' * 116)
    print(f'{label}   trade dates {dates[0]} .. {dates[-1]}   ({len(dates)} trading days)   '
          f'weighting={scheme}  PIT={"ON" if pit else "OFF"}')
    print('=' * 116)

    spy_m = curve_metrics(b['spy_c2c'])
    uni_m = curve_metrics(b['uni_ew'])
    print(f'BENCHMARK  SPY buy&hold (close-to-close, split-adj, NO dividends): '
          f'total {100*spy_m["total"]:+.2f}%  CAGR {100*spy_m["cagr"]:+.2f}%  '
          f'vol {100*spy_m["vol"]:.2f}%  Sharpe {spy_m["sharpe"]:+.2f}  maxDD {100*spy_m["mdd"]:.2f}%')
    print(f'REFERENCE  equal-weight universe of eligible names, open-to-close only (not investable): '
          f'total {100*uni_m["total"]:+.2f}%  CAGR {100*uni_m["cagr"]:+.2f}%')
    hurdle = spy_m['cagr']

    hdr = (f'{"N":>3} {"cash d":>6} {"final $":>11} {"total":>9} {"CAGR":>9} {"vol":>8} '
           f'{"Sharpe":>7} {"maxDD":>9} | ' +
           ' | '.join(f'{"CAGR@"+str(int(c*1e4))+"bp":>10} {"Sh":>6} {"DD":>8}' for c in costs[1:]))
    print('\nEXECUTABLE: rank at day-t close, BUY day-t+1 OPEN, SELL day-t+1 CLOSE')
    print('-' * 116)
    print(hdr)
    res = {}
    for n in NS:
        g = curve_metrics(b['strat'][n])
        cells = []
        for c in costs[1:]:
            m = curve_metrics(net(b['strat'][n], b['inv'][n], c))
            cells.append(f'{100*m["cagr"]:>9.2f}% {m["sharpe"]:>6.2f} {100*m["mdd"]:>7.1f}%')
            res[(n, c)] = m
        res[(n, 0.0)] = g
        print(f'{n:>3} {b["cash"][n]:>6} {g["final"]:>11,.0f} {100*g["total"]:>8.2f}% '
              f'{100*g["cagr"]:>8.2f}% {100*g["vol"]:>7.2f}% {g["sharpe"]:>7.2f} '
              f'{100*g["mdd"]:>8.2f}% | ' + ' | '.join(cells))

    print('\nLOOKAHEAD DIAGNOSTIC ONLY -- buy at the day-t close you ranked on (NOT TRADABLE):')
    print(f'{"N":>3} {"final $":>11} {"total":>9} {"CAGR":>9} {"Sharpe":>7}   '
          f'(gap vs executable CAGR)')
    for n in NS:
        m = curve_metrics(b['look'][n])
        print(f'{n:>3} {m["final"]:>11,.0f} {100*m["total"]:>8.2f}% {100*m["cagr"]:>8.2f}% '
              f'{m["sharpe"]:>7.2f}   {100*(m["cagr"]-res[(n,0.0)]["cagr"]):>+8.2f} pp')

    print('\nCAPM vs SPY on the daily series (gross, executable entry). o2c is the matched-exposure')
    print('regressor -- the strategy is flat overnight -- and is the one the alpha verdict uses.')
    print(f'{"N":>3} | {"beta c2c":>9} {"alpha/d":>10} {"alpha/yr":>10} {"t":>6} | '
          f'{"beta o2c":>9} {"alpha/d":>10} {"alpha/yr":>10} {"t":>6}')
    ba = {}
    for n in NS:
        a = beta_alpha(b['strat'][n], b['spy_c2c'])
        o = beta_alpha(b['strat'][n], b['spy_o2c'])
        ba[n] = (a, o)
        print(f'{n:>3} | {a["beta"]:>9.2f} {fmt_pct(a["alpha"]):>10} {100*a["alpha_ann"]:>9.2f}% '
              f'{a["t"]:>6.2f} | {o["beta"]:>9.2f} {fmt_pct(o["alpha"]):>10} '
              f'{100*o["alpha_ann"]:>9.2f}% {o["t"]:>6.2f}')

    print('\nROBUSTNESS (gross, executable entry): does the curve live in a handful of days?')
    print(f'{"N":>3} {"%days>0":>8} {"median/d":>10} {"CAGR":>9} {"drop-1":>9} {"drop-3":>9} '
          f'{"drop-5":>9}   best day / worst day')
    for n in NS:
        r = b['strat'][n]
        order = sorted(range(len(r)), key=lambda i: -abs(r[i]))
        drops = [curve_metrics([r[i] for i in order[k:]])['cagr'] for k in (1, 3, 5)]
        hi = max(range(len(r)), key=lambda i: r[i])
        lo = min(range(len(r)), key=lambda i: r[i])
        print(f'{n:>3} {100*sum(1 for x in r if x>0)/len(r):>7.1f}% '
              f'{fmt_pct(sorted(r)[len(r)//2]):>10} {100*res[(n,0.0)]["cagr"]:>8.2f}% '
              + ' '.join(f'{100*x:>8.2f}%' for x in drops)
              + f'   {dates[hi]} {100*r[hi]:+.1f}% / {dates[lo]} {100*r[lo]:+.1f}%')
    cnt = {}
    for d in dates:
        day = by_trade_lookup.get(d)
        if day:
            cnt[day['rows'][0]['sym']] = cnt.get(day['rows'][0]['sym'], 0) + 1
    top = sorted(cnt.items(), key=lambda kv: -kv[1])[:6]
    print(f'N=1 concentration: {len(cnt)} distinct names over {len(dates)} days; most-picked '
          + ', '.join(f'{s_}x{c_}' for s_, c_ in top))

    print('\nVERDICT (test fixed in advance: net-of-5bp CAGR >= SPY CAGR *and* alpha vs SPY o2c not negative)')
    c5 = costs[1] if len(costs) > 1 else 0.0
    for n in NS:
        m = res[(n, c5)]
        o = ba[n][1]
        beats = m['cagr'] >= hurdle
        pos_alpha = o['alpha'] >= 0
        ok = beats and pos_alpha
        why = []
        why.append(f'net-5bp CAGR {100*m["cagr"]:+.2f}% vs SPY {100*hurdle:+.2f}%')
        why.append(f'beta {o["beta"]:.2f}')
        why.append(f'alpha {100*o["alpha_ann"]:+.2f}%/yr (t={o["t"]:+.2f})')
        verb = 'COMPETES WITH' if ok else 'DOES NOT COMPETE WITH'
        print(f'  {label} N={n:<3} {verb} the S&P 500 index: ' + '; '.join(why) + '.')
    return b, res, ba, spy_m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weight', default='equal', choices=('equal', 'drop', 'sqrtdrop'))
    ap.add_argument('--no-pit', action='store_true')
    ap.add_argument('--max-drop', type=float, default=0.50)
    ap.add_argument('--costs', default='0,5,10')
    a = ap.parse_args()

    members = load_members()
    px, missing = load_bars(members)
    spy_px, spy_missing = load_bars(['SPY'])
    if spy_missing:
        sys.exit('SPY bars missing -- pull data/sp500_daily/SPY.csv first')
    spy = spy_px['SPY']
    costs = [float(c) / 10000.0 for c in a.costs.split(',')]

    print(f'universe: {len(members)} current S&P 500 members, {len(px)} with bars, missing {missing}')
    span = sorted({d for s in px for d in px[s]})
    print(f'panel spans {span[0]} .. {span[-1]} ({len(span)} trading days); '
          f'SPY spans {min(spy)} .. {max(spy)} ({len(spy)} bars)')
    short = sorted((min(px[s]), s) for s in px if min(px[s]) > '2024-08-05')
    print(f'symbols with PARTIAL history (first bar after 2024-08-05): {len(short)} -> '
          + ', '.join(f'{s} from {d}' for d, s in short))
    print('Each is simply ineligible on days it has no bar; the panel is UNBALANCED, not padded.')
    print('SURVIVORSHIP: today\'s membership only. Year A carries one MORE year of scrubbed-out')
    print('deletions than Year B, so Year A is the MORE upward-biased of the two windows.')

    for label, s, e in WINDOWS:
        report_window(label, s, e, px, spy, members, not a.no_pit, a.max_drop, a.weight, costs)


if __name__ == '__main__':
    main()
