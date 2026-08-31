#!/usr/bin/env python3
"""Backfill outcome_30m / outcome_eod in data/leg_log.csv from cached 5-min bars.

entry.md §1.3b requires these columns; without them the leg log cannot validate a
single threshold, which is the file's entire stated purpose. As of 2026-08-21 they
were populated on 4.1% / 4.9% of rows, so every threshold in this strategy was
being argued from anecdote.

Outcomes are DIRECTION-ADJUSTED underlying moves measured from the close of the
evaluated bar: positive = the trade direction was right. They are underlying moves,
not option P&L — option P&L needs OI/spread/greeks the API does not serve
historically (see the note in backtest_legs.py).

Bars are read from data/bars/YYYY-MM-DD_SYM.csv (t,o,h,l,c,v; t = UTC HHMM).
Rows whose bar file is absent are left untouched. Idempotent: re-running only
fills blanks unless --force is given.

Usage:  python3 tools/backfill_outcomes.py [--force] [--dry-run]
"""
import csv, os, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
LEG  = os.path.join(ROOT, 'data', 'leg_log.csv')
BARS = os.path.join(ROOT, 'data', 'bars')

def load_bars(date, sym):
    p = os.path.join(BARS, f'{date}_{sym}.csv')
    if not os.path.exists(p): return None
    out = []
    for r in csv.DictReader(open(p)):
        out.append({'t': r['t'], 'c': float(r['c']), 'h': float(r['h']), 'l': float(r['l'])})
    return out or None

def et_to_utc_hhmm(t):
    """leg_log times are US/Eastern; bar keys are UTC HHMM. EDT = UTC-4."""
    try: hh, mm = t.strip().split(':')[:2]; hh = int(hh); mm = int(mm)
    except Exception: return None
    return '%02d%02d' % ((hh + 4) % 24, mm - mm % 5)

def main():
    force   = '--force'   in sys.argv
    dry     = '--dry-run' in sys.argv
    rows    = list(csv.DictReader(open(LEG)))
    fields  = list(rows[0].keys())
    filled = skipped_nobars = skipped_have = 0

    for r in rows:
        have = str(r.get('outcome_30m','')).strip() not in ('', 'n/a')
        if have and not force: skipped_have += 1; continue
        date = r['date'].strip(); sym = r['symbol'].strip().upper()
        bars = load_bars(date, sym)
        if not bars: skipped_nobars += 1; continue
        key = et_to_utc_hhmm(r['time_et'])
        if not key: skipped_nobars += 1; continue
        idx = next((i for i, b in enumerate(bars) if b['t'] >= key), None)
        if idx is None or idx >= len(bars) - 1: skipped_nobars += 1; continue

        sign = -1 if r['direction'].strip().lower() == 'put' else 1
        entry = bars[idx]['c']
        j = min(idx + 6, len(bars) - 1)                 # +30 min = 6 five-minute bars
        m30 = (bars[j]['c'] / entry - 1) * 100 * sign
        eod = (bars[-1]['c'] / entry - 1) * 100 * sign
        fut = bars[idx+1:]
        mfe = max((b['h']/entry-1)*100*sign if sign>0 else (entry/b['l']-1)*100 for b in fut)
        mae = min((b['l']/entry-1)*100*sign if sign>0 else (entry/b['h']-1)*100 for b in fut)
        r['outcome_30m'] = f'{m30:+.2f}%'
        r['outcome_eod'] = f'{eod:+.2f}% (mfe {mfe:+.2f}% mae {mae:+.2f}%)'
        filled += 1

    print(f'filled {filled}  already-had {skipped_have}  no-bars/unusable {skipped_nobars}  total {len(rows)}')
    if dry: print('(dry run, nothing written)'); return
    with open(LEG, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f'wrote {LEG}')

if __name__ == '__main__':
    main()
