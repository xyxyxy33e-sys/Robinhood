#!/usr/bin/env python3
"""Backtest the §1.3 leg rule over data/bars/.

WHY THIS FILE WAS REWRITTEN (2026-08-28)
----------------------------------------
It used to carry its OWN implementation of the leg rule, in a local analyze().
That copy and the live rule in tools/eval_entry.py drifted apart, and nobody
noticed for a week because both produced plausible numbers. The differences:

  * the backtest's "new extreme" looked back 3 BARS; live looks back over the
    WHOLE SESSION (h > max of every prior bar's high),
  * the backtest never required the 3-bar streak at all — it checked only that
    the current bar closed in the trade's direction,
  * the backtest had no session-extreme (`seq`) condition,
  * the backtest did not model the CHASE GUARD, which in live trading is the
    single most active blocker: it stopped all seven §1.3 qualifications this
    week, so every trade the old harness "took" was one live would have refused.

The headline "-5.1% per trade at the live 1.5 threshold" quoted in every daily
report since 2026-08-22 therefore described a rule the strategy does not run.

The fix is structural, not a patch: eval_entry.evaluate_ohlcv() is now the only
implementation of the rule, and this file imports it. The two cannot drift again
because there is only one of them.

STILL NOT BACKTESTABLE: open interest, bid/ask spread and depth. The API exposes
no history for them, so §2.3 cannot be simulated. Spread enters only as the
FRIC round-trip friction constant in --pnl, which is a flat assumption.

Usage:
  python3 tools/backtest_legs.py            # fires + forward returns
  python3 tools/backtest_legs.py --pnl      # modelled P&L through the exit cascade
  python3 tools/backtest_legs.py --sweep    # MFE/MAE sensitivity to the threshold
Options: --no-guard  evaluate without the chase guard (to price what it costs)
Env: LEV, STOP, ARM, TRAIL, FLOOR, FRIC
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_entry import evaluate_ohlcv

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'bars')

# Entry window, UTC HHMM. 1345 = 09:45 ET (first bar after the open is complete);
# 1700 = 13:00 ET, the live entry cutoff.
T_START, T_END = '1345', '1700'


def load(p):
    return [{'t': r['t'], **{k: float(r[k]) for k in 'ohlcv'}}
            for r in csv.DictReader(open(p))]


def cfg(threshold):
    return dict(min_day_change_pct=2.0,
                late_entry_min_volume_ratio=threshold,
                late_entry_min_bars=3,
                chase_guard_all_session_pct=1.0)


def judge(bars, i, prior_close, direction, threshold):
    """Evaluate bar i exactly as the live strategy would, given the session so
    far. Returns the eval_entry dict, or None when the bar is too early for the
    rule to be defined (eval_entry refuses below 10 bars for the same reason)."""
    if i + 1 < 10:
        return None
    b = [(x['o'], x['h'], x['l'], x['c'], x['v']) for x in bars[:i + 1]]
    return evaluate_ohlcv(b, prior_close, direction, cfg(threshold))


def cases():
    out = []
    man = os.path.join(D, 'manifest.csv')
    if os.path.exists(man):
        for row in csv.DictReader(open(man)):
            out.append((row['file'], float(row['prior_close']), row['direction']))
    legacy = [('2026-07-23_TSLA.csv', 374.01, 'put'),
              ('2026-07-23_GOOGL.csv', 342.09, 'put'),
              ('2026-07-31_AAPL.csv', 333.43, 'put'),
              ('2026-08-04_PLTR.csv', 125.65, 'call'),
              ('2026-08-06_U.csv', 35.47, 'call'),
              ('2026-08-12_NBIS.csv', 193.23, 'call'),
              ('2026-08-13_BIRK.csv', 36.74, 'call'),
              ('2026-08-14_NU.csv', 13.93, 'call')]
    have = {c[0] for c in out}
    out += [c for c in legacy if c[0] not in have]
    return [c for c in out if os.path.exists(os.path.join(D, c[0]))]


def signals(threshold, use_guard=True):
    """First qualifying bar per name-day, as the live rule would see it."""
    for f, pc, direction in cases():
        bars = load(os.path.join(D, f))
        for i, x in enumerate(bars):
            if x['t'] < T_START or x['t'] > T_END:
                continue
            d = judge(bars, i, pc, direction, threshold)
            if not d or not d['qualified']:
                continue
            if use_guard and d['guard_blocks']:
                continue
            if i >= len(bars) - 1:
                continue
            yield f[:-4], bars, i, direction, d
            break


def fwd(bars, i, direction, n=12):
    e = bars[i]['c']
    j = min(i + n, len(bars) - 1)
    raw = (bars[j]['c'] / e - 1) * 100
    return raw if direction == 'call' else -raw


LEV = float(os.environ.get('LEV', '7.9'))
THETA = -3.3
FRIC = float(os.environ.get('FRIC', '-3.0'))
STOP = float(os.environ.get('STOP', '-25'))
ARM = float(os.environ.get('ARM', '12'))
TRAIL = float(os.environ.get('TRAIL', '20'))
FLOOR = float(os.environ.get('FLOOR', '10'))
TP = float(os.environ.get('TP', '50'))


def sim(bars, i, direction):
    """Apply the real exit cascade to a modelled option position."""
    up = direction == 'call'
    e = bars[i]['c']; hwm = 0.0; armed = False; n = 0; adj = FRIC
    for y in bars[i + 1:]:
        n += 1
        adj = THETA * (n * 5 / 390.0) + FRIC
        pnl = (((y['c'] - e) / e * 100) if up else ((e - y['c']) / e * 100)) * LEV
        hi = (((y['h'] - e) / e * 100) if up else ((e - y['l']) / e * 100)) * LEV
        lo = (((y['l'] - e) / e * 100) if up else ((e - y['h']) / e * 100)) * LEV
        hwm = max(hwm, hi)
        if lo <= STOP:
            return STOP + adj
        if hi >= TP:
            return TP + adj
        if hwm >= ARM:
            armed = True
        if armed and pnl <= max(FLOOR, hwm - TRAIL):
            return max(FLOOR, hwm - TRAIL) + adj
        if not armed and hwm >= 8 and pnl <= -3:
            return -3 + adj
    close = (((bars[-1]['c'] - e) / e * 100) if up else ((e - bars[-1]['c']) / e * 100))
    return close * LEV + adj


THRESHOLDS = (1.0, 1.2, 1.25, 1.3, 1.5, 1.75, 2.0)

if __name__ == '__main__':
    guard_on = '--no-guard' not in sys.argv

    if '--pnl' in sys.argv:
        print(f"modelled P&L, one trade per name-day, {LEV}x leverage, "
              f"friction {FRIC:+.1f}%, chase guard {'ON' if guard_on else 'OFF'}")
        print(f"{'thresh':>7}{'trades':>8}{'avg':>9}{'total':>9}{'wins':>7}")
        for th in THRESHOLDS:
            tr = [sim(b, i, d) for _, b, i, d, _ in signals(th, guard_on)]
            if tr:
                print(f"{th:>7.2f}{len(tr):>8}{sum(tr) / len(tr):>+8.1f}%"
                      f"{sum(tr):>+8.0f}%{sum(1 for t in tr if t > 0):>4}/{len(tr)}")
            else:
                print(f"{th:>7.2f}{0:>8}{'—':>9}{'—':>9}{'—':>7}")
        raise SystemExit

    if '--audit' in sys.argv:
        # Block accounting: of the bars that satisfy §1.3, how many does the
        # chase guard stop, and is guard_pct just the bar's own giveback?
        n_qual = n_blocked = n_tauto = 0; worst = 0.0
        for f, pc, direction in cases():
            bars = load(os.path.join(D, f))
            for i, x in enumerate(bars):
                if x['t'] < T_START or x['t'] > T_END or i >= len(bars) - 1:
                    continue
                d = judge(bars, i, pc, direction, 1.5)
                if not d or not d['qualified']:
                    continue
                n_qual += 1
                if d['guard_blocks']:
                    n_blocked += 1
                    worst = max(worst, d['guard_pct'])
                bar = bars[i]
                own = ((bar['h'] - bar['c']) / bar['h'] * 100 if direction == 'call'
                       else (bar['c'] - bar['l']) / bar['l'] * 100)
                if abs(own - d['guard_pct']) < 1e-6:
                    n_tauto += 1
        print(f"corpus name-days ................ {len(cases())}")
        print(f"§1.3 qualifying bars ............ {n_qual}")
        print(f"blocked by the chase guard ...... {n_blocked}  "
              f"({100.0 * n_blocked / n_qual:.0f}% of qualifications)" if n_qual else "")
        print(f"guard_pct == bar's own giveback .. {n_tauto}/{n_qual}")
        print(f"largest guard_pct observed ...... {worst:.3f}%  "
              f"(threshold is 1.000%)")
        if n_qual and n_blocked == n_qual:
            print("\nThe guard blocks EVERY qualification in the corpus. `seq` "
                  "requires the bar to set\nthe session extreme; the guard "
                  "requires distance from it. They are mutually exclusive\nby "
                  "construction, at any threshold. One of them has to go — an "
                  "owner decision.")
        raise SystemExit

    if '--sweep' in sys.argv:
        print(f"{'thresh':>7}{'fires':>7}{'avgMFE':>9}{'avgMAE':>9}")
        for th in THRESHOLDS:
            f_ = []
            for _, b, i, d, _ in signals(th, guard_on):
                up = d == 'call'; e = b[i]['c']; fut = b[i + 1:]
                if not fut:
                    continue
                f_.append((max((y['h'] - e) / e * 100 if up else (e - y['l']) / e * 100 for y in fut),
                           min((y['l'] - e) / e * 100 if up else (e - y['h']) / e * 100 for y in fut)))
            if f_:
                print(f"{th:>7.2f}{len(f_):>7}"
                      f"{sum(r[0] for r in f_) / len(f_):>+8.2f}%"
                      f"{sum(r[1] for r in f_) / len(f_):>+8.2f}%")
        raise SystemExit

    for label, g in (('guard ON ', True), ('guard OFF', False)):
        s = list(signals(1.5, g))
        if s:
            r = [fwd(b, i, d) for _, b, i, d, _ in s]
            print(f"{label} fires={len(r):3} avg_fwd60={sum(r) / len(r):+.2f}% "
                  f"wins={sum(1 for x in r if x > 0)}/{len(r)}")
        else:
            print(f"{label} fires=  0")
    print(f"\nname-days in corpus: {len(cases())}")
