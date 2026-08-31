#!/usr/bin/env python3
"""Extension of sp500_losers_backtest.py: instead of a 1-day flip, BUILD A
PORTFOLIO — buy the daily biggest-loser basket and hold it for H trading
days before selling. Same signal (that day's 1-day % drop), same universe,
same data (data/sp500_daily/, data/sp500_members.csv). Reuses the loading
and weighting code from sp500_losers_backtest.py rather than re-deriving it.

WHY THIS NEEDS ITS OWN OVERLAP HANDLING (read before trusting any t-stat here)
===============================================================================
The 1-day version clustered by DAY: each day was one basket, one observation,
because a 1-day hold means consecutive daily baskets don't share any return
history. A multi-day hold breaks that. If you form a new basket every day and
hold each for H days, basket(t) and basket(t+1) overlap over H-1 of their H
days — they are the SAME underlying stock returns counted almost twice. Pool
those as independent observations and the t-stat inflates by roughly sqrt(H),
on top of the sqrt(N) leg-pooling error already fixed once today.

So every holding period is reported TWO ways:

  rolling (overlapping)   — a new cohort formed every trading day, held H
                             days. Larger n, but observations overlap by
                             (H-1)/H. The 'n_eff' column divides n by H as a
                             conservative independence discount; treat the
                             raw t next to it as an upper bound, not a result.
  non-overlapping (block) — cohorts formed every H trading days, so no two
                             holding periods share a single day. Honest n,
                             but n shrinks fast as H grows (n ~= days/H).

BENCHMARK: same-WINDOW equal-weighted universe return (entry date -> exit
date, same eligible names used for ranking), not an all-period average — for
the same reason as the 1-day version: loser days cluster on selloffs and
longer windows still inherit that starting condition.

COSTS: one round-trip charged per cohort regardless of H, so the cost drag
per day shrinks as H grows — report both the per-cohort and the annualized-
equivalent cost so the two are not confused.

Usage:
  python3 tools/sp500_losers_hold.py                         # full report
  python3 tools/sp500_losers_hold.py --holds 5,10,21,63,126,252
  python3 tools/sp500_losers_hold.py --weight drop            # drop-weighted basket
"""
import argparse, csv, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sp500_losers_backtest import load_members, load_bars, weights_for, stats, fmt_pct, BARS, MEMBERS

NS = (1, 3, 5, 10)
HOLDS = (5, 10, 21, 63, 126, 252)
TRADING_DAYS = 252


def build_universe(px, members, start, end, pit, max_drop):
    """Per-day signal (1-day drop) and per-day close, restricted to names with
    a bar on that day. Returns sorted trading-day list and {date: rows}."""
    all_dates = sorted({d for s in px for d in px[s]})
    days = []
    for i, t in enumerate(all_dates):
        if t < start or t > end or i == 0:
            continue
        prev = all_dates[i - 1]
        rows = []
        for s, d in px.items():
            if pit and members.get(s, '9999') > t:
                continue
            b_prev, b_t = d.get(prev), d.get(t)
            if not (b_prev and b_t) or min(b_prev[3], b_t[3]) <= 0:
                continue
            r = b_t[3] / b_prev[3] - 1.0
            if max_drop and abs(r) > max_drop:
                continue
            rows.append(dict(sym=s, ret=r))
        if len(rows) >= 50:
            rows.sort(key=lambda x: x['ret'])
            days.append(dict(date=t, i=i, rows=rows))
    return all_dates, days


def window_return(px, sym, entry_date, exit_date, field_entry='o', field_exit='c'):
    d = px[sym]
    if entry_date not in d or exit_date not in d:
        return None
    e = d[entry_date][0 if field_entry == 'o' else 3]
    x = d[exit_date][3]
    if e <= 0:
        return None
    return x / e - 1.0


def cohorts_for_hold(all_dates, days, px, H, n, scheme):
    """One row per SIGNAL day t where entry=t+1 open, exit=(t+1+H) close both
    exist. Returns list of dict(date, entry_date, exit_date, basket, universe, excess)."""
    idx = {d['date']: d for d in days}
    out = []
    for d in days:
        i = d['i']
        if i + 1 + H >= len(all_dates):
            continue
        entry_date, exit_date = all_dates[i + 1], all_dates[i + 1 + H]
        picks = d['rows'][:n]
        if len(picks) < n:
            continue
        w, _ = weights_for([-p['ret'] for p in picks], scheme)
        legs = [window_return(px, p['sym'], entry_date, exit_date) for p in picks]
        if any(l is None for l in legs):
            continue
        basket = sum(wi * l for wi, l in zip(w, legs))
        uni_legs = [window_return(px, r['sym'], entry_date, exit_date) for r in d['rows']]
        uni_legs = [l for l in uni_legs if l is not None]
        if len(uni_legs) < 50:
            continue
        universe = sum(uni_legs) / len(uni_legs)
        out.append(dict(date=d['date'], entry=entry_date, exit=exit_date,
                        basket=basket, universe=universe, excess=basket - universe))
    return out


def beta_alpha(basket, universe):
    """CAPM-style: how much of the naive excess is just market-beta leverage?
    Added after the first run of this file showed long holds (H=126) reporting
    +25%/yr 'excess' on n_block<=1 -- turned out to be almost entirely a beta
    tilt (picked names run 1.4x-4.5x the universe's volatility) compounding
    through a +34% bull year in the cached window, not stock-picking skill.
    beta = cov(basket,universe)/var(universe); alpha = mean(basket) - beta*mean(universe)."""
    bm = sum(basket) / len(basket); um = sum(universe) / len(universe)
    cov = sum((b - bm) * (u - um) for b, u in zip(basket, universe)) / (len(basket) - 1)
    var = sum((u - um) ** 2 for u in universe) / (len(universe) - 1)
    beta = cov / var if var else float('nan')
    return beta, bm - beta * um


def block_sample(rolling, H):
    """Non-overlapping: keep the 1st, (H+1)th, (2H+1)th ... rolling cohort by
    signal-day order. Approximate but simple and honest about independence."""
    return rolling[::H]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2025-08-28')
    ap.add_argument('--end', default='2026-08-27')
    ap.add_argument('--no-pit', action='store_true')
    ap.add_argument('--max-drop', type=float, default=0.50)
    ap.add_argument('--holds', default=','.join(str(h) for h in HOLDS))
    ap.add_argument('--weight', default='equal', choices=('equal', 'drop', 'sqrtdrop'))
    ap.add_argument('--costs', default='0,10', help='round-trip cost scenarios in bp, per cohort')
    a = ap.parse_args()
    holds = [int(x) for x in a.holds.split(',')]

    members = load_members()
    px, missing = load_bars(members)
    print(f'universe file: {len(members)} S&P 500 members; bars loaded: {len(px)}; missing: {len(missing)}')
    print(f'weighting scheme: {a.weight}   window: {a.start} .. {a.end}\n')

    all_dates, days = build_universe(px, members, a.start, a.end, not a.no_pit, a.max_drop)
    print(f'signal days available: {len(days)} of {len(all_dates)} trading days in the cached range\n')

    costs = [float(c) / 10000.0 for c in a.costs.split(',')]

    for n in NS:
        print('=' * 116)
        print(f'BASKET SIZE N = {n}   (weight = {a.weight})')
        print('=' * 116)
        header = (f"{'H(days)':>8}{'entry':>12}{'exit':>12}"
                  f"{'n_roll':>8}{'t_roll':>8}{'n_eff':>7}{'t_eff':>7}"
                  f"{'n_block':>9}{'t_block':>9}"
                  f"{'excess/cohort':>15}{'ann.excess':>12}{'ann.Sharpe':>11}")
        print(header)
        for H in holds:
            rolling = cohorts_for_hold(all_dates, days, px, H, n, a.weight)
            if len(rolling) < 5:
                print(f"{H:>8}   -- fewer than 5 cohorts fit in the window, skipped --")
                continue
            exc = [r['excess'] for r in rolling]
            st_roll = stats(exc)
            n_eff = max(1, len(exc) // H)
            sd = st_roll['sd']
            t_eff = st_roll['mean'] / (sd / math.sqrt(n_eff)) if sd > 0 else float('nan')

            block = block_sample(rolling, H)
            st_block = stats([r['excess'] for r in block])

            periods_per_year = TRADING_DAYS / H
            ann_excess = st_roll['mean'] * periods_per_year
            ann_sharpe = (st_roll['mean'] / sd) * math.sqrt(periods_per_year) if sd > 0 else float('nan')

            print(f"{H:>8}{rolling[0]['entry']:>12}{rolling[-1]['exit']:>12}"
                  f"{st_roll['n']:>8}{st_roll['t']:>8.2f}{n_eff:>7}{t_eff:>7.2f}"
                  f"{st_block['n']:>9}{st_block['t']:>9.2f}"
                  f"{fmt_pct(st_roll['mean']):>15}{fmt_pct(ann_excess):>12}{ann_sharpe:>11.2f}")

            if H == holds[-1] or H == max(holds):
                pass
        print()

    # ---- cost sensitivity, one round trip per cohort, rolling series -------
    print('=' * 116)
    print(f'COST SENSITIVITY  (one round-trip charged per COHORT regardless of H; weight={a.weight})')
    print('=' * 116)
    print(f"{'N':>4}{'H':>6}{'gross/cohort':>15}" +
          ''.join(f'{c*10000:>9.0f}bp' for c in costs) +
          "   ann.gross   ann.@10bp")
    for n in NS:
        for H in holds:
            rolling = cohorts_for_hold(all_dates, days, px, H, n, a.weight)
            if len(rolling) < 5:
                continue
            exc = [r['excess'] for r in rolling]
            m = sum(exc) / len(exc)
            periods_per_year = TRADING_DAYS / H
            line = f"{n:>4}{H:>6}{fmt_pct(m):>15}"
            for c in costs:
                line += f"{fmt_pct(m - c):>11}"
            line += f"{fmt_pct(m*periods_per_year):>12}{fmt_pct((m-costs[-1])*periods_per_year):>12}"
            print(line)

    print('=' * 116)
    print(f'BETA/ALPHA CHECK  (weight={a.weight}) -- is the "excess" above stock-picking, or leveraged market beta?')
    print('=' * 116)
    _d0, _d1 = days[0]['date'], days[-1]['date']
    _rets = [px[s][_d1][3] / px[s][_d0][3] - 1.0
             for s in px if _d0 in px[s] and _d1 in px[s] and px[s][_d0][3] > 0]
    _uni_ret = sum(_rets) / len(_rets) if _rets else float('nan')
    print(f"the cached universe returned {100*_uni_ret:+.1f}% equal-weight, {_d0}..{_d1} "
          f"(n={len(_rets)}) -- a strong bull run. In a strong bull run, a")
    print("higher-beta basket outperforms an equal-beta universe for reasons that have nothing to do with stock selection.")
    print(f"{'N':>4}{'H':>6}{'naive excess':>14}{'beta':>7}{'true alpha':>12}{'n_block':>9}")
    for n in NS:
        for H in holds:
            rolling = cohorts_for_hold(all_dates, days, px, H, n, a.weight)
            if len(rolling) < 5:
                continue
            b = [r['basket'] for r in rolling]; u = [r['universe'] for r in rolling]
            beta, alpha = beta_alpha(b, u)
            block = block_sample(rolling, H)
            naive = (sum(b) / len(b)) - (sum(u) / len(u))
            print(f"{n:>4}{H:>6}{fmt_pct(naive):>14}{beta:>7.2f}{fmt_pct(alpha):>12}{len(block):>9}")
    print("\nbeta is estimated on the ROLLING (overlapping) series, so treat it as directional, not precise.")
    print("At H=126 beta ran 2.8x-4.5x and true alpha went NEGATIVE for every N -- the entire long-hold")
    print("'excess' at that horizon was leveraged market exposure, not selection skill.\n")

    print("""
READING THIS TABLE
- t_roll is the overlapping-window t-stat: OPTIMISTIC, an upper bound. Do not
  quote it on its own.
- t_eff divides n by H before computing t, a blunt independence discount.
  Still approximate (adjacent cohorts H days apart are not perfectly
  independent either) but far more honest than t_roll.
- t_block is the true non-overlapping test. Trust this one, but note n_block
  shrinks fast: at H=252 there is at most 1 non-overlapping cohort in a
  ~1-year window, i.e. no statistical test at all, just a single anecdote.
- ann.excess/ann.Sharpe annualize the per-cohort mean by (252/H) holding
  periods per year -- i.e. what you'd get if you could always immediately
  redeploy into a fresh cohort the moment one exits. Real capital can't
  always do that (basket sizes vary night to night); treat as an upper bound
  on deployable annual return, not a promise.
""")


if __name__ == '__main__':
    main()
