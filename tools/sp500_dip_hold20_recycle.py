#!/usr/bin/env python3
"""Owner's rule, verbatim: "Buy the most dip everyday, but sell once it's +20%,
then hold cash to buy more cheaper assets."

Formally: every trading day, each FREE tranche of capital buys the S&P 500 name
that fell the most (ranked by that day's 1-day close-to-close return); a position
is held with NO time limit until its price is +20% above the entry price, at
which point it is sold and the cash recycled into the next day's biggest dip.
Repeat for two years. M = 1, 3, 5, 10 concurrent tranches.

This is the SEVENTH test today on the buy-the-losers family and the first with a
PRICE-TRIGGERED, variable-length exit rather than a fixed horizon. The previous
six were all negative, and every apparently-positive intermediate result today
turned out to be one of five artifacts: pooling correlated legs as independent,
benchmarking against something you cannot buy, entry lookahead, leveraged beta
mistaken for selection skill, or survivorship. A different exit rule does not
exempt this test from any of them, so each is handled explicitly below.

METHODOLOGY — every design choice, made once and stated
======================================================

1. ENTRY IS THE NEXT OPEN. NO LOOKAHEAD IN THE HEADLINE.
   The ranking signal (day t's 1-day % change) is only known at day t's CLOSE.
   A market-on-close order must be in by ~15:50 ET, i.e. before the ranking
   exists, so "buy at the close you ranked on" is not executable. The primary
   simulation therefore ranks at day t's close and BUYS AT DAY t+1's OPEN.
   A same-day-close entry is also computed and printed, labelled LOOKAHEAD
   DIAGNOSTIC. Today's earlier work measured that gap at 13-23bp/day on a
   1-day flip and +44pp of CAGR on a compounded curve; it is not tradable and
   is never used for a verdict here.

2. THE EXIT CHECK USES THE CLOSE, ONCE PER DAY.
   Primary: at each day's close, if close/entry - 1 >= +0.20 the position is
   sold AT THAT CLOSE. No intraday assumption, no assumption that a limit order
   existed or filled. An OPTIMISTIC variant is also printed: if the day's HIGH
   touches entry * 1.20 the position is filled EXACTLY at entry * 1.20, i.e. a
   resting limit sell that always fills at the target with no slippage and no
   queue. That is the best case, is labelled as such, and is not the headline.

3. THREE EXIT-RULE VARIANTS, ALL REPORTED. This is the structural risk of the
   rule and the most important number in the file.
     BRACKET   - THE HEADLINE BOUNDED VARIANT, owner-specified: take profit at
                 +20%, stop loss at -10%, capital recycled on either exit. The
                 stop is GAP-AWARE and deliberately pessimistic: if a day's
                 OPEN is already at or below entry*0.90 the stop fills AT THAT
                 OPEN (reason 'stop_gap'), because a resting stop triggers on
                 the gap and the fill is wherever the market reopened. Only
                 when the open was still above the level and the stop is
                 touched intraday does it fill at the nominal -10%. This
                 matters here specifically: the entry pool is systematically
                 distressed names, which are exactly the ones that gap. If a
                 stop and a target trigger on the same day the STOP wins (the
                 conservative choice).
     PURE      - the rule exactly as the owner first stated it: no stop, no
                 time limit. A position that never gains 20% is held to the end
                 of the window. This can trap capital indefinitely; the report
                 quantifies exactly how much it trapped. Kept as the COMPARISON
                 POINT, not the headline.
     BOUND     - a second safety valve for contrast: a -25% STOP checked on the
                 close (sell at that close) and a 252-TRADING-DAY MAX HOLD.
                 Target wins a same-day tie in this variant.
   All three are printed side by side for every M, every window and every cost.
   Reporting only the flattering one would be the reporting failure this file
   exists to avoid.

3b. WIN RATE vs GEOMETRIC BREAKEVEN, for the bracket. The question "does one
   good stock cancel two bad ones" has an exact answer and it is NOT the naive
   arithmetic 33.3% = 10/(10+20). An account COMPOUNDS, so breakeven solves
       p*ln(1.20) + (1-p)*ln(0.90) = 0  ->  p* = 36.62%
   (1.20 * 0.90 * 0.90 = 0.972, i.e. one winner and two losers LOSES 2.8%).
   The empirical fraction of closed positions exiting at the target is reported
   against that 36.62% line, with and without counting still-open positions as
   losses, plus the cost-adjusted breakeven.

4. CAPITAL, CONCURRENCY AND THE CASH DRAG.
   $10,000 split into M EQUAL TRANCHES at the start of each window. A tranche is
   a self-contained sleeve: it holds either cash or exactly one position, and it
   reinvests its own realised proceeds (so a winning tranche compounds and a
   trapped tranche stops trading; tranches are never rebalanced against each
   other). Each day, every FREE tranche buys the biggest remaining drop among
   names NOT already held by another tranche, working down the ranked list;
   ties break on symbol. A candidate must actually have FALLEN (1-day return
   < 0) to qualify; if fewer qualifying candidates than free tranches exist the
   remainder sits in cash that day. Cash earns 0% - no money-market yield is
   credited, which is conservative by roughly the T-bill rate and is stated
   rather than hidden. A tranche that exits at day d's close becomes free at
   day d+1's open, never same-day.

5. THE EQUITY CURVE IS THE ACCOUNT, NOT A MEAN.
   Total equity = sum over tranches of (cash + shares x that day's close),
   recorded every trading day. CAGR, annualised vol, annualised Sharpe (excess
   over 0, consistent with the rest of the repo) and max drawdown are computed
   on the daily total-equity return series, so cash drag from idle tranches and
   volatility drag from concentrated ones both land where they belong. Positions
   open at the window's last day are marked to that day's close - NOT liquidated,
   and no exit cost is charged on them; the % of equity they represent is the
   "stuck capital" disclosure.

6. COSTS. A round-trip cost of c is charged as c/2 on EVERY entry and c/2 on
   EVERY exit, so one complete round trip costs exactly c. c = 0 (gross), 5bp
   and 10bp. Costs are charged inside the simulation, not subtracted afterwards,
   so they change the share count and therefore the path. The +20% EXIT TRIGGER
   is evaluated on GROSS price (the rule is a price rule); costs are applied to
   the cash, not the trigger. Trade count and turnover are printed so the cost
   impact is legible.

7. BENCHMARK IS SPY, THE THING YOU COULD OTHERWISE BUY.
   Buy-and-hold SPY over the identical trade dates from data/sp500_daily/SPY.csv,
   close-to-close, split-adjusted. SPY bars carry no dividend (~1.2%/yr), so the
   SPY line UNDERSTATES the real index and every comparison here is generous to
   the strategy.

8. BETA/ALPHA vs SPY, BECAUSE BETA IS WHAT KILLED THE LAST TWO VERSIONS.
   beta = cov(strat, spy_c2c)/var(spy_c2c) on daily returns; alpha = the
   regression intercept, annualised, with a residual t-stat. Unlike this
   morning's day-trade studies, THIS strategy holds overnight, so SPY
   close-to-close is the correctly-matched regressor and no open-to-close
   version is needed. The regression uses the strategy's ACTUAL daily portfolio
   return INCLUDING idle-tranche cash drag - a rule that is often in cash has a
   genuinely lower beta and that must show up, not be assumed away.

9. WINDOWS. Full 2y plus the two non-overlapping years, because today's other
   work found the two years tell opposite stories:
       Year A  2024-08-28 .. 2025-08-27
       Year B  2025-08-28 .. 2026-08-27
       Full    2024-07-25 .. 2026-08-27  (SPY cache ends 2026-08-27)
   EACH WINDOW IS AN INDEPENDENT SIMULATION starting from $10,000 in cash with
   no inherited positions. A sub-window is therefore not a slice of the full
   run; it answers "what if you started then", which is the question.

10. SURVIVORSHIP - UNCORRECTABLE AND IT BIASES THIS UPWARD.
    data/sp500_members.csv is TODAY'S membership. Names deleted from the index
    during the window are absent, and deletions skew hard toward the worst
    performers - exactly the names a buy-the-dip-and-hold-till-+20% rule buys
    and then gets trapped in. This rule is MORE exposed to that bias than any
    tested today, because a deleted name is precisely the kind of position that
    would never have reached +20% and would have sat in the portfolio forever.
    The additions half IS correctable and is corrected (--pit, on by default:
    a name is ineligible on days before its date_added, 23 names joined inside
    the window). The deletions half is not correctable without point-in-time
    membership data this repo does not have. Year A is a further year back and
    so carries an extra year of scrubbed-out deletions: it is the MORE biased
    window. ALL RESULTS BELOW ARE AN UPPER BOUND.

11. DATA ARTIFACTS. |1-day move| > 50% is treated as a bad bar and the name is
    dropped from that day's ranking (--max-drop). One is known: MRNA +177.0% on
    2026-08-19.

RESEARCH ONLY. config.yaml has dry_run: true. This file places no orders and
touches no broker API; it reads cached CSVs and prints.

Usage:
  python3 tools/sp500_dip_hold20_recycle.py
  python3 tools/sp500_dip_hold20_recycle.py --target 0.20 --stop 0.25 --maxhold 252
  python3 tools/sp500_dip_hold20_recycle.py --no-pit
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sp500_losers_backtest import load_members, load_bars, stats, fmt_pct
from sp500_losers_equity_curve import curve_metrics, beta_alpha

MS = (1, 3, 5, 10)
TRADING_DAYS = 252
START_EQUITY = 10_000.0
WINDOWS = (('Full 2y', '2024-07-25', '2026-08-27'),
           ('Year A ', '2024-08-28', '2025-08-27'),
           ('Year B ', '2025-08-28', '2026-08-27'))


# ---------------------------------------------------------------- ranking panel
def build_ranked(px, members, pit, max_drop, keep=40):
    """{date: [(sym, 1-day return), ...] ascending} — the ranking known at that
    date's CLOSE. Only the top `keep` are kept; M<=10 tranches can never need
    more than 10 distinct names plus the ones already held."""
    all_dates = sorted({d for s in px for d in px[s]})
    ranked, artifacts = {}, []
    for i, t in enumerate(all_dates):
        if i == 0:
            continue
        prev = all_dates[i - 1]
        rows = []
        for s, d in px.items():
            if pit and members.get(s, '9999') > t:
                continue                       # not an index member yet on day t
            bp, bt = d.get(prev), d.get(t)
            if not (bp and bt) or min(bp[3], bt[3]) <= 0:
                continue
            r = bt[3] / bp[3] - 1.0
            if max_drop and abs(r) > max_drop:
                artifacts.append((t, s, r)); continue
            rows.append((r, s))
        if len(rows) < 50:                     # unusable panel day -> no entries
            continue
        rows.sort()                            # most-negative first; ties on symbol
        ranked[t] = [(s, r) for r, s in rows[:keep]]
    return all_dates, ranked, artifacts


# ---------------------------------------------------------------- simulation
def simulate(all_dates, px, ranked, start, end, M, cost_rt, entry='open',
             exit_mode='close', target=0.20, stop=None, maxhold=None,
             stop_style='close'):
    """One independent run. Returns the daily equity/return series, the closed
    and open position records, and trade accounting.

    entry='open'  : rank at day t close, buy at day t+1 open   (EXECUTABLE)
    entry='close' : rank at day t close, buy at day t close     (LOOKAHEAD)
    exit_mode='close': target met only if the CLOSE is >= entry*(1+target);
                       fill at that close.
    exit_mode='high' : target met if the HIGH touches entry*(1+target);
                       fill EXACTLY at entry*(1+target)         (OPTIMISTIC)
    stop     : e.g. 0.25 -> stop level at entry*(1-stop)
    maxhold  : e.g. 252  -> forced sale at the close of that many held days
    stop_style='close'   : the stop is evaluated ONLY on the close and fills at
                           that close; the target wins a same-day tie.
    stop_style='bracket' : GAP-AWARE, and deliberately the pessimistic reading.
                           Order of checks within a day:
                             (a) if the OPEN is already at/below the stop level,
                                 the resting stop triggers at the open and fills
                                 AT THAT OPEN — the realistic bad fill, recorded
                                 as reason 'stop_gap'. This is checked FIRST
                                 because it happens before any intraday high.
                             (b) otherwise the intraday LOW touching the stop
                                 fills at the NOMINAL level entry*(1-stop).
                                 stop_style='bracket_pess' is the pessimistic
                                 bound on the SAME event: an intraday touch
                                 fills at that day's CLOSE instead. It exists
                                 because the nominal fill is itself optimistic
                                 in a fast market — KVUE 2025-09-05 opened
                                 above the stop and fell 16% intraday; assuming
                                 a clean fill at exactly -10% on that tape is
                                 not credible, and the two styles bracket the
                                 truth.
                           The stop leg is live from the entry day (a real OCO
                           bracket is), so an entry-day intraday touch counts.
                             (c) otherwise the take-profit check runs as normal.
                           If a stop and a target both trigger on the same day
                           the STOP wins here (the conservative choice; it
                           requires a >33% intraday range and never occurred).
    """
    half = cost_rt / 2.0
    dates = [d for d in all_dates if start <= d <= end]
    idx = {d: i for i, d in enumerate(all_dates)}
    tranches = [dict(cash=START_EQUITY / M, sym=None, sh=0.0, ep=0.0,
                     ed=None, days=0, minlow=None, mindd=0.0) for _ in range(M)]
    last_px = {}                       # carry-forward mark for a missing bar
    eq_series, ret_series, dates_used = [], [], []
    closed, entries, exits, traded_dollars = [], 0, 0, 0.0
    prev_eq = START_EQUITY
    cash_tranche_days = 0

    for d in dates:
        i = idx[d]
        # ---- 1. ENTRIES, at the open (or at the close in the lookahead variant)
        sig_day = all_dates[i - 1] if entry == 'open' else d
        cands = ranked.get(sig_day, [])
        held = {t['sym'] for t in tranches if t['sym']}
        free = [t for t in tranches if t['sym'] is None]
        if free:
            k = 0
            for t in free:
                bought = False
                while k < len(cands):
                    s, r = cands[k]; k += 1
                    if s in held or r >= 0:    # already held, or did not fall
                        continue
                    bar = px[s].get(d)
                    if not bar:
                        continue
                    p = bar[0] if entry == 'open' else bar[3]
                    if p <= 0:
                        continue
                    eff = p * (1.0 + half)
                    t['sh'] = t['cash'] / eff
                    traded_dollars += t['cash']
                    t['cash'] = 0.0
                    t['sym'], t['ep'], t['ed'], t['days'] = s, p, d, 0
                    t['minlow'], t['mindd'] = bar[2], min(0.0, bar[2] / p - 1.0)
                    held.add(s); entries += 1; bought = True
                    break
                if not bought:
                    pass
        # idle-tranche accounting: tranches holding nothing after the open
        cash_tranche_days += sum(1 for t in tranches if t['sym'] is None)

        # ---- 2. MARK AND EXIT CHECK, at the close
        for t in tranches:
            if not t['sym']:
                continue
            bar = px[t['sym']].get(d)
            if bar:
                last_px[t['sym']] = bar[3]
                lo, hi, c = bar[2], bar[1], bar[3]
                if t['minlow'] is None or lo < t['minlow']:
                    t['minlow'] = lo
                t['mindd'] = min(t['mindd'], lo / t['ep'] - 1.0)
            else:
                c = last_px.get(t['sym'], t['ep']); lo = hi = c
            if t['ed'] != d:
                t['days'] += 1
            tgt = t['ep'] * (1.0 + target)
            stl = t['ep'] * (1.0 - stop) if stop else None
            op = bar[0] if bar else c
            reason, fill = None, None
            fresh = t['ed'] != d
            brk = stop_style in ('bracket', 'bracket_pess')
            # a real bracket/OCO order is live from the moment of entry, so the
            # stop leg IS checked on the entry day too (the target leg is not:
            # +20% from that morning's open on the same session never happened).
            if brk and stl and fresh and op <= stl:
                reason, fill = 'stop_gap', op        # gapped through overnight
            elif brk and stl and lo <= stl:
                reason, fill = 'stop', (c if stop_style == 'bracket_pess' else stl)
            elif exit_mode == 'high' and hi >= tgt and fresh:
                reason, fill = 'target', tgt
            elif c >= tgt and fresh:
                reason, fill = 'target', c
            elif stop_style == 'close' and stl and fresh and c <= stl:
                reason, fill = 'stop', c
            elif maxhold and t['days'] >= maxhold:
                reason, fill = 'maxhold', c
            if reason:
                proceeds = t['sh'] * fill * (1.0 - half)
                traded_dollars += t['sh'] * fill
                closed.append(dict(sym=t['sym'], ed=t['ed'], ep=t['ep'], xd=d,
                                   xp=fill, days=t['days'], reason=reason,
                                   minlow=t['minlow'], mindd=t['mindd'],
                                   nominal=(-stop if stop else None),
                                   ret=fill / t['ep'] - 1.0))
                t['cash'], t['sh'], t['sym'] = proceeds, 0.0, None
                exits += 1

        # ---- 3. TOTAL EQUITY
        eq = 0.0
        for t in tranches:
            eq += t['cash']
            if t['sym']:
                bar = px[t['sym']].get(d)
                eq += t['sh'] * (bar[3] if bar else last_px.get(t['sym'], t['ep']))
        eq_series.append(eq)
        ret_series.append(eq / prev_eq - 1.0)
        dates_used.append(d)
        prev_eq = eq

    open_pos = []
    for t in tranches:
        if t['sym']:
            bar = px[t['sym']].get(dates[-1])
            mark = bar[3] if bar else last_px.get(t['sym'], t['ep'])
            open_pos.append(dict(sym=t['sym'], ed=t['ed'], ep=t['ep'], xd=None,
                                 xp=mark, days=t['days'], reason='open',
                                 minlow=t['minlow'], mindd=t['mindd'],
                                 ret=mark / t['ep'] - 1.0,
                                 value=t['sh'] * mark))
    return dict(dates=dates_used, eq=eq_series, rets=ret_series, closed=closed,
                open=open_pos, entries=entries, exits=exits,
                traded=traded_dollars, final=eq_series[-1] if eq_series else START_EQUITY,
                stuck=sum(p['value'] for p in open_pos),
                cash_tranche_days=cash_tranche_days, tranche_days=M * len(dates))


# ---------------------------------------------------------------- reporting
def spy_series(spy, dates, all_dates):
    idx = {d: i for i, d in enumerate(all_dates)}
    out = []
    for d in dates:
        prev = all_dates[idx[d] - 1]
        if d in spy and prev in spy:
            out.append(spy[d][3] / spy[prev][3] - 1.0)
        else:
            out.append(0.0)
    return out


def pct(x):
    return f'{100*x:+.2f}%'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', type=float, default=0.20)
    ap.add_argument('--bracket-stop', type=float, default=0.10,
                    help='HEADLINE bracket stop, as a positive fraction (owner-specified -10%%)')
    ap.add_argument('--stop', type=float, default=0.25, help='secondary close-stop variant, positive fraction')
    ap.add_argument('--maxhold', type=int, default=252, help='bounded-variant max hold in trading days')
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
    print('=' * 118)
    print('DIP-BUY, SELL-AT-+20%, RECYCLE-CASH  —  "buy the most dip everyday, but sell once '
          "it's +20%, then hold cash\"")
    print('=' * 118)
    print(f'universe      : {len(members)} current S&P 500 members; bars loaded {len(px)}, missing {len(missing)}')
    print(f'panel         : {len(all_dates)} trading days {all_dates[0]}..{all_dates[-1]}; '
          f'{len(ranked)} usable ranking days')
    print(f'PIT filter    : {"OFF" if a.no_pit else "ON (date_added <= signal day)"}   '
          f'artifacts dropped (|1d| > {a.max_drop:.0%}): {len(artifacts)}')
    print(f'rule          : take profit +{100*a.target:.0f}%. THREE exit variants: '
          f'BRACKET (-{100*a.bracket_stop:.0f}% gap-aware stop, HEADLINE), '
          f'PURE (no stop, hold forever), '
          f'BOUND (-{100*a.stop:.0f}% close stop + {a.maxhold}d max hold)')
    print(f'costs         : round trip {a.costs} bp, charged half on entry and half on exit')
    print('entry         : PRIMARY = next trading day OPEN (executable). '
          'close-entry printed later as a LOOKAHEAD diagnostic only.')
    print('exit check    : PRIMARY = once daily on the CLOSE. '
          'intraday-HIGH touch printed later as an OPTIMISTIC diagnostic only.')

    # (label, stop, maxhold, stop_style) — the +20%/-10% bracket is the HEADLINE
    # bounded variant per the owner's specification; PURE is the comparison point.
    variants = ((f'BRACKET +{100*a.target:.0f}%/-{100*a.bracket_stop:.0f}% (gap-aware)',
                 a.bracket_stop, None, 'bracket'),
                ('PURE  (no stop, hold forever)', None, None, 'close'),
                (f'BOUND (-{100*a.stop:.0f}% close stop, {a.maxhold}d max)',
                 a.stop, a.maxhold, 'close'))

    # ------------------------------------------------ headline tables
    store = {}
    for wname, ws, we in WINDOWS:
        base = simulate(all_dates, px, ranked, ws, we, 1, 0.0)   # for dates only
        dates = base['dates']
        sr = spy_series(spy, dates, all_dates)
        spym = curve_metrics(sr)
        print('\n' + '=' * 118)
        print(f'{wname.strip()}  {dates[0]} .. {dates[-1]}  ({len(dates)} trading days)')
        print(f'SPY buy & hold: final ${START_EQUITY*(1+spym["total"]):,.0f}  total {pct(spym["total"])}  '
              f'CAGR {pct(spym["cagr"])}  vol {100*spym["vol"]:.2f}%  Sharpe {spym["sharpe"]:+.2f}  '
              f'maxDD {pct(spym["mdd"])}')
        print('=' * 118)
        print(f'{"variant":<34} {"M":>2} {"final$":>9} {"CAGR gr":>8} {"vol":>7} {"Sh":>6} {"maxDD":>8} '
              f'{"CAGR5bp":>8} {"Sh5bp":>6} {"CAGR10bp":>9} {"pos":>4} {"hit":>4} {"open":>5} '
              f'{"turn/yr":>8} {"%stuck":>7} {"%uw":>6} {"%cashdy":>8}')
        for vlabel, vstop, vmax, vstyle in variants:
            for M in MS:
                row = []
                for c in costs:
                    r = simulate(all_dates, px, ranked, ws, we, M, c,
                                 entry='open', exit_mode='close',
                                 target=a.target, stop=vstop, maxhold=vmax,
                                 stop_style=vstyle)
                    row.append((c, r, curve_metrics(r['rets'])))
                g_r, g_m = row[0][1], row[0][2]
                m5, m10 = row[1][2], row[2][2]
                yrs = len(dates) / TRADING_DAYS
                avg_eq = sum(g_r['eq']) / len(g_r['eq'])
                turn = g_r['traded'] / avg_eq / yrs
                stuck = g_r['stuck'] / g_r['final'] if g_r['final'] else 0.0
                uw = sum(p['value'] for p in g_r['open'] if p['ret'] < 0) / g_r['final']
                cashfrac = g_r['cash_tranche_days'] / g_r['tranche_days']
                hits = sum(1 for p in g_r['closed'] if p['reason'] == 'target')
                print(f'{vlabel:<34} {M:>2} {g_r["final"]:>9,.0f} {pct(g_m["cagr"]):>8} '
                      f'{100*g_m["vol"]:>6.2f}% {g_m["sharpe"]:>+6.2f} {pct(g_m["mdd"]):>8} '
                      f'{pct(m5["cagr"]):>8} {m5["sharpe"]:>+6.2f} {pct(m10["cagr"]):>9} '
                      f'{g_r["entries"]:>4} {hits:>4} {len(g_r["open"]):>5} '
                      f'{turn:>7.2f}x {100*stuck:>6.1f}% {100*uw:>5.1f}% {100*cashfrac:>7.1f}%')
                store[(wname, vlabel, M)] = row

        # ---- beta / alpha vs SPY, gross, executable
        print(f'\nBETA / ALPHA vs SPY close-to-close (gross, executable entry, includes cash drag) — {wname.strip()}')
        print(f'{"variant":<34} {"M":>2} {"beta":>6} {"alpha/yr":>10} {"t":>7} {"corr":>6}')
        for vlabel, vstop, vmax, vstyle in variants:
            for M in MS:
                r = store[(wname, vlabel, M)][0][1]
                ba = beta_alpha(r['rets'], sr)
                sx, sy = stats(r['rets']), stats(sr)
                cov = sum((x - sx['mean']) * (y - sy['mean']) for x, y in zip(r['rets'], sr)) / (len(sr) - 1)
                corr = cov / (sx['sd'] * sy['sd']) if sx['sd'] and sy['sd'] else float('nan')
                print(f'{vlabel:<34} {M:>2} {ba["beta"]:>6.2f} {pct(ba["alpha_ann"]):>10} '
                      f'{ba["t"]:>+7.2f} {corr:>6.2f}')

    # ------------------------------------------------ bracket win rate vs breakeven
    T, S = a.target, a.bracket_stop
    lw, ll = math.log(1.0 + T), -math.log(1.0 - S)
    p_star = ll / (lw + ll)
    print('\n' + '=' * 118)
    print(f'BRACKET +{100*T:.0f}% / -{100*S:.0f}% — EMPIRICAL WIN RATE vs GEOMETRIC BREAKEVEN')
    print('=' * 118)
    print(f'Breakeven solves p*ln(1{T:+.2f}) + (1-p)*ln(1{-S:+.2f}) = 0  ->  p* = {100*p_star:.2f}%.')
    print(f'That is the COMPOUNDING breakeven, not the naive arithmetic {100*S/(S+T):.1f}% '
          f'({100*S:.0f}/({100*S:.0f}+{100*T:.0f})): an account multiplies, it does not add, so a')
    print('20% gain does NOT cancel two 10% losses (1.20*0.90*0.90 = 0.972, a 2.8% LOSS).')
    for c in costs:
        if c <= 0:
            continue
        lwc, llc = math.log((1.0 + T) * (1 - c)), -math.log((1.0 - S) * (1 - c))
        print(f'   net of a {int(c*10000)}bp round trip the breakeven rises to '
              f'{100*llc/(lwc+llc):.2f}%.')
    print(f'\n{"window":<9} {"M":>2} {"closed":>7} {"target":>7} {"stop":>6} {"stopgap":>8} '
          f'{"WIN RATE":>9} {"vs p*":>8} {"open@end":>9} {"win incl. open as loss":>23}')
    for wname, ws, we in WINDOWS:
        for M in MS:
            r = simulate(all_dates, px, ranked, ws, we, M, 0.0, 'open', 'close', T, S, None, 'bracket')
            cl = r['closed']
            tg = sum(1 for p in cl if p['reason'] == 'target')
            st = sum(1 for p in cl if p['reason'] == 'stop')
            sg = sum(1 for p in cl if p['reason'] == 'stop_gap')
            wr = tg / len(cl) if cl else float('nan')
            wr_all = tg / (len(cl) + len(r['open'])) if (cl or r['open']) else float('nan')
            print(f'{wname:<9} {M:>2} {len(cl):>7} {tg:>7} {st:>6} {sg:>8} '
                  f'{100*wr:>8.1f}% {100*(wr-p_star):>+7.1f}pp {len(r["open"]):>9} '
                  f'{100*wr_all:>22.1f}%')

    print(f'\nSTOP-LOSS GAP-THROUGH — how often the -{100*S:.0f}% stop did NOT fill at -{100*S:.0f}%')
    print(f'{"window":<9} {"M":>2} {"stop exits":>11} {"gapped thru":>12} {"%gapped":>8} '
          f'{"avg loss, gapped":>17} {"avg loss, clean":>16} {"worst gap fill":>15}')
    for wname, ws, we in WINDOWS:
        for M in MS:
            r = simulate(all_dates, px, ranked, ws, we, M, 0.0, 'open', 'close', T, S, None, 'bracket')
            g = [p for p in r['closed'] if p['reason'] == 'stop_gap']
            n_ = [p for p in r['closed'] if p['reason'] == 'stop']
            tot = len(g) + len(n_)
            avg_g = sum(p['ret'] for p in g) / len(g) if g else float('nan')
            avg_n = sum(p['ret'] for p in n_) / len(n_) if n_ else float('nan')
            worst = min((p['ret'] for p in g), default=float('nan'))
            print(f'{wname:<9} {M:>2} {tot:>11} {len(g):>12} '
                  f'{(100*len(g)/tot if tot else float("nan")):>7.1f}% '
                  f'{(pct(avg_g) if g else "n/a"):>17} {(pct(avg_n) if n_ else "n/a"):>16} '
                  f'{(pct(worst) if g else "n/a"):>15}')

    # ------------------------------------------------ position-level disclosure
    print('\n' + '=' * 118)
    print('POSITION-LEVEL DISCLOSURE — Full 2y, PURE variant (the rule as stated), gross, executable entry')
    print('=' * 118)
    wname, ws, we = WINDOWS[0]
    for M in MS:
        r = simulate(all_dates, px, ranked, ws, we, M, 0.0, entry='open', exit_mode='close',
                     target=a.target, stop=None, maxhold=None, stop_style='close')
        hit = [p for p in r['closed'] if p['reason'] == 'target']
        op = r['open']
        hd = [p['days'] for p in hit] or [0]
        od = [p['days'] for p in op] or [0]
        print(f'\nM = {M}:  {len(hit)} positions hit +{100*a.target:.0f}%, {len(op)} still open at window end')
        print(f'   holding period, HIT +20%   : avg {sum(hd)/len(hd):6.1f} td   max {max(hd):4d} td')
        print(f'   holding period, STILL OPEN : avg {sum(od)/len(od):6.1f} td   max {max(od):4d} td')
        print(f'   capital stuck in open positions at window end: '
              f'${r["stuck"]:,.0f} of ${r["final"]:,.0f} final equity = '
              f'{100*r["stuck"]/r["final"]:.1f}%')
        if op:
            print(f'   open positions, marked to the last close:')
            for p in sorted(op, key=lambda x: x['ret']):
                print(f'      {p["sym"]:<6} in {p["ed"]} @ {p["ep"]:9.2f}  mark {p["xp"]:9.2f}  '
                      f'{pct(p["ret"]):>8}  held {p["days"]:4d} td  worst low {p["minlow"]:9.2f} '
                      f'({pct(p["mindd"])})')
        allp = r['closed'] + op
        if allp:
            worst = min(allp, key=lambda p: p['mindd'])
            if worst['reason'] == 'open':
                ending = 'STILL OPEN at window end, marked %.2f' % worst['xp']
            else:
                ending = '%s on %s @ %.2f' % (worst['reason'], worst['xd'], worst['xp'])
            print('   WORST SINGLE POSITION by max unrealised drawdown:')
            print(f'      {worst["sym"]}  entered {worst["ed"]} @ {worst["ep"]:.2f}  '
                  f'worst price {worst["minlow"]:.2f} ({pct(worst["mindd"])} unrealised)  '
                  f'ended: {ending}  '
                  f'held {worst["days"]} td  realised/marked {pct(worst["ret"])}')
            wr = min(allp, key=lambda p: p['ret'])
            print(f'   WORST SINGLE POSITION by final (realised or marked) return: '
                  f'{wr["sym"]} in {wr["ed"]} @ {wr["ep"]:.2f} -> {wr["xp"]:.2f} '
                  f'{pct(wr["ret"])} ({wr["reason"]}, {wr["days"]} td)')

    print('\n' + '-' * 118)
    print(f'Same disclosure for the HEADLINE BRACKET variant (+{100*a.target:.0f}%/-{100*a.bracket_stop:.0f}%), Full 2y, gross')
    print('-' * 118)
    print(f'{"M":>2} {"hit +20%":>9} {"stopped":>8} {"open":>5} {"avg td HIT":>11} {"max td HIT":>11} '
          f'{"avg td STOP":>12} {"avg td OPEN":>12} {"max td OPEN":>12} {"%stuck":>7} {"%uw":>6}')
    for M in MS:
        r = simulate(all_dates, px, ranked, ws, we, M, 0.0, 'open', 'close',
                     a.target, a.bracket_stop, None, 'bracket')
        hit = [p for p in r['closed'] if p['reason'] == 'target']
        stp = [p for p in r['closed'] if p['reason'] in ('stop', 'stop_gap')]
        op = r['open']
        f = lambda xs: (sum(p['days'] for p in xs) / len(xs)) if xs else float('nan')
        g = lambda xs: max((p['days'] for p in xs), default=0)
        uw = sum(p['value'] for p in op if p['ret'] < 0) / r['final']
        print(f'{M:>2} {len(hit):>9} {len(stp):>8} {len(op):>5} {f(hit):>11.1f} {g(hit):>11d} '
              f'{f(stp):>12.1f} {f(op):>12.1f} {g(op):>12d} '
              f'{100*r["stuck"]/r["final"]:>6.1f}% {100*uw:>5.1f}%')
        allp = r['closed'] + op
        worst = min(allp, key=lambda q: q['mindd'])
        print(f'     worst position by max unrealised drawdown: {worst["sym"]} in {worst["ed"]} '
              f'@ {worst["ep"]:.2f}, worst low {worst["minlow"]:.2f} ({pct(worst["mindd"])}), '
              f'ended {worst["reason"]} {worst["xd"] or "(open)"} @ {worst["xp"]:.2f} '
              f'{pct(worst["ret"])} after {worst["days"]} td')

    print('\n' + '-' * 118)
    print('STOP-FILL ASSUMPTION SENSITIVITY — the nominal -10% fill is itself optimistic. Same rule,')
    print("two fill assumptions for an intraday stop touch: NOMINAL (exactly -10%) vs that day's CLOSE.")
    print('Gap-through-at-open fills at the open under both. Gross CAGR, executable entry.')
    print('-' * 118)
    print(f'{"window":<9} {"M":>2} {"CAGR nominal fill":>18} {"CAGR close fill":>17} {"gap":>9} '
          f'{"mean stop loss nom":>19} {"mean stop loss close":>21}')
    for wname, ws, we in WINDOWS:
        for M in MS:
            rn = simulate(all_dates, px, ranked, ws, we, M, 0.0, 'open', 'close',
                          a.target, a.bracket_stop, None, 'bracket')
            rp = simulate(all_dates, px, ranked, ws, we, M, 0.0, 'open', 'close',
                          a.target, a.bracket_stop, None, 'bracket_pess')
            mn, mp = curve_metrics(rn['rets']), curve_metrics(rp['rets'])
            sn = [q['ret'] for q in rn['closed'] if q['reason'] in ('stop', 'stop_gap')]
            sp = [q['ret'] for q in rp['closed'] if q['reason'] in ('stop', 'stop_gap')]
            print(f'{wname:<9} {M:>2} {pct(mn["cagr"]):>18} {pct(mp["cagr"]):>17} '
                  f'{100*(mp["cagr"]-mn["cagr"]):>+8.2f}pp '
                  f'{(pct(sum(sn)/len(sn)) if sn else "n/a"):>19} '
                  f'{(pct(sum(sp)/len(sp)) if sp else "n/a"):>21}')

    # ------------------------------------------------ diagnostics: the two optimisms
    print('\n' + '=' * 118)
    print('DIAGNOSTICS — the two OPTIMISTIC variants. NOT TRADABLE, printed only to size the bias.')
    print('=' * 118)
    print(f'{"window":<9} {"variant":<34} {"M":>2} {"CAGR exec/close":>16} {"CAGR LOOKAHEAD-entry":>21} '
          f'{"CAGR HIGH-touch exit":>21}')
    for wname, ws, we in WINDOWS:
        for vlabel, vstop, vmax, vstyle in variants:
            for M in MS:
                base = curve_metrics(simulate(all_dates, px, ranked, ws, we, M, 0.0, 'open', 'close',
                                              a.target, vstop, vmax, vstyle)['rets'])
                look = curve_metrics(simulate(all_dates, px, ranked, ws, we, M, 0.0, 'close', 'close',
                                              a.target, vstop, vmax, vstyle)['rets'])
                high = curve_metrics(simulate(all_dates, px, ranked, ws, we, M, 0.0, 'open', 'high',
                                              a.target, vstop, vmax, vstyle)['rets'])
                print(f'{wname:<9} {vlabel:<34} {M:>2} {pct(base["cagr"]):>16} '
                      f'{pct(look["cagr"]):>21} {pct(high["cagr"]):>21}')

    # ------------------------------------------------ start-date sensitivity
    print('\n' + '=' * 118)
    print('START-DATE SENSITIVITY — the same rule, run to 2026-08-27, started on each of the first 20')
    print('possible trading days. With only a handful of positions per run the outcome is a few coin')
    print('flips, and this is how wide the spread of those flips actually is. All variants, gross, exec entry.')
    print('"beat SPY" counts how many of the 20 start dates finished above SPY over that run\'s own window.')
    print('=' * 118)
    starts = [d for d in all_dates if d >= '2024-07-25'][:20]
    print(f'{"variant":<34} {"M":>2} {"runs":>5} {"min CAGR":>9} {"p25":>9} {"median":>9} {"p75":>9} '
          f'{"max":>9} {"mean":>9} {"beat SPY":>9}')
    for vlabel, vstop, vmax, vstyle in variants:
        for M in MS:
            cg, beat = [], 0
            for st in starts:
                r = simulate(all_dates, px, ranked, st, WINDOWS[0][2], M, 0.0, 'open', 'close',
                             a.target, vstop, vmax, vstyle)
                m = curve_metrics(r['rets'])
                sm = curve_metrics(spy_series(spy, r['dates'], all_dates))
                cg.append(m['cagr'])
                beat += 1 if m['cagr'] > sm['cagr'] else 0
            cg.sort()
            q = lambda f: cg[min(len(cg) - 1, int(f * len(cg)))]
            print(f'{vlabel:<34} {M:>2} {len(cg):>5} {pct(cg[0]):>9} {pct(q(.25)):>9} '
                  f'{pct(q(.5)):>9} {pct(q(.75)):>9} {pct(cg[-1]):>9} '
                  f'{pct(sum(cg)/len(cg)):>9} {beat:>4}/{len(cg):<4}')

    # ------------------------------------------------ position census
    print('\n' + '=' * 118)
    print('POSITION CENSUS — Full 2y, gross, executable entry. n is the number of INDEPENDENT stock')
    print('bets the rule actually placed in two years; every headline number above rests on exactly this many.')
    print('=' * 118)
    print(f'{"variant":<34} {"M":>2} {"n pos":>6} {"hit +20%":>9} {"open":>5} {"stop":>5} {"stopgap":>8} '
          f'{"maxhold":>8} {"mean pos ret":>13} {"median":>9} {"worst":>9}')
    for vlabel, vstop, vmax, vstyle in variants:
        for M in MS:
            r = simulate(all_dates, px, ranked, WINDOWS[0][1], WINDOWS[0][2], M, 0.0, 'open', 'close',
                         a.target, vstop, vmax, vstyle)
            allp = r['closed'] + r['open']
            rets = sorted(p['ret'] for p in allp)
            cnt = lambda k: sum(1 for p in allp if p['reason'] == k)
            print(f'{vlabel:<34} {M:>2} {len(allp):>6} {cnt("target"):>9} {cnt("open"):>5} '
                  f'{cnt("stop"):>5} {cnt("stop_gap"):>8} {cnt("maxhold"):>8} '
                  f'{pct(sum(rets)/len(rets)):>13} {pct(rets[len(rets)//2]):>9} {pct(rets[0]):>9}')

    print('\nVARIANTS TESTED: 3 windows x 3 exit-rule variants x 4 M x 3 cost levels for the headline, '
          'plus 2 optimistic diagnostics. The best of that many cells is expected to look good by '
          'chance; nothing here is selected on outcome.')


if __name__ == '__main__':
    main()
