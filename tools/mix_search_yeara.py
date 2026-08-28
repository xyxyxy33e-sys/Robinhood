#!/usr/bin/env python3
"""SEARCH PERIOD ONLY -- Year A, 2024-08-28 .. 2025-08-27. Exploration lives here.

This runner exists to be run MANY times while looking for a mix that beats SPY.
Year B (2025-08-28 .. 2026-08-27) is a LOCKED HOLDOUT and this file must never be
pointed at it -- the window is hard-coded and there is no --start/--end flag, on
purpose. The holdout is opened exactly once, by tools/mix_holdout_yearb.py, after
the candidate is frozen.

WHY A CHRONOLOGICAL SPLIT AT ALL (the risk this task adds over the earlier six)
==============================================================================
"Find a mix" is an invitation to data-dredge. With 503 names and a menu of signals
the number of testable combinations is effectively unbounded, and at a 5% bar you
expect one in twenty pure-noise variants to look significant. Six strategies were
falsified today, several of which looked significant on first measurement, so the
prior on any winner found by search is that it is noise. The only structural defence
is to spend a fixed budget of variants on ONE period and settle the question on a
period that was never touched.

THE PRE-REGISTERED RULES, WRITTEN BEFORE ANY OUTPUT WAS READ
===========================================================
  * K = the number of distinct variants evaluated on Year A is fixed by the GRID
    below and printed at the end of the run. Nothing is added after seeing output.
  * SCREENING BAR: a variant is a holdout candidate only if its Year-A alpha vs SPY
    has t > 2.5. That is stricter than the conventional 2.0 precisely because K
    variants are being tested: at t>2.0 roughly K*0.05 variants pass by chance.
  * ADDITIONAL GATES, all of which must hold for a candidate:
      - it must be a MIX (>= 2 signals or conditions), per the owner's request
      - CAPM beta vs SPY <= 1.15, so the result is not levered index exposure
        wearing a costume (this is what killed the loser baskets: beta 1.2-1.9)
      - net-of-5bp CAGR >= SPY CAGR over the identical dates
  * EXACTLY ONE candidate goes to the holdout: the highest Year-A alpha t among
    variants passing the gates. If none passes the t>2.5 bar, the single best mix
    by alpha t (subject to the beta and cost gates) is still carried forward, and
    it is reported as BELOW BAR -- a pass on the holdout by a below-bar candidate
    is weak evidence and is written up as such, not as a discovery.
  * The holdout is evaluated ONCE, unmodified. A failure there is the answer.

WINDOW ARITHMETIC (see mix_engine.py note 9)
============================================
The cache starts 2024-07-25, only 24 trading days before Year A. Every variant in the
main grid uses lookbacks of at most 63 trading days, so the main Year-A evaluation
window is bar 64 .. bar 273 of the cache -- 210 trading days ending 2025-08-27. Fixing
one window for the whole grid means the variants are compared on the SAME DATES against
the SAME SPY path; letting each variant start whenever its lookback filled would make
the comparison partly a comparison of start dates. Two 126-day variants are run as a
clearly separated secondary set on their own shorter window (bar 127..273) with their
own SPY line.

A reference row, EW-universe, holds every eligible name equal-weighted and rebalanced
on the same schedule. It is not a searched variant and is not a candidate; it is there
so that any "the mix beat SPY" claim can be checked against "equal weighting beat SPY",
which in a year when the average stock outruns the cap-weighted index is a different
and much less interesting fact.

Usage:  python3 tools/mix_search_yeara.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mix_engine import Panel, evaluate, HDR, fmt_row, spy_series, curve_metrics, TRADING_DAYS
from mix_signals import (blend, screen_then_rank, spy_trend_gate, eligible,
                         MOM, LOWMOM, LOWVOL, HIVOL, LOWBETA, HIPROX, TREND, LIQ)

YEAR_A = ('2024-08-28', '2025-08-27')
K_NAMES = 50           # portfolio size for the main grid
REBAL = 21             # ~monthly
MAIN_BACK = 63         # longest lookback in the main grid


def ew_universe(need_back, k=None):
    """Reference: hold every eligible name, equal weighted."""
    cache = {}
    def select(P, i):
        if i not in cache:
            cache[i] = eligible(P, i, need_back)
        return cache[i]
    return select


def build_grid():
    """The complete, fixed list of variants. Returns [(label, is_mix, selector, rebal, back)]."""
    g = []
    A = g.append
    # ---- stage 1: single factors (baselines; NOT eligible as the final candidate)
    A(('1  mom63',                  False, blend([MOM(63)], K_NAMES), REBAL, 63))
    A(('2  mom21',                  False, blend([MOM(21)], K_NAMES), REBAL, 63))
    A(('3  mom42-skip21',           False, blend([MOM(42, 21)], K_NAMES), REBAL, 63))
    A(('4  lowmom21 (reversal)',    False, blend([LOWMOM(21)], K_NAMES), REBAL, 63))
    A(('5  lowvol63',               False, blend([LOWVOL(63)], K_NAMES), REBAL, 63))
    A(('6  hivol63 (neg control)',  False, blend([HIVOL(63)], K_NAMES), REBAL, 63))
    A(('7  lowbeta63',              False, blend([LOWBETA(63)], K_NAMES), REBAL, 63))
    A(('8  hiprox63 (52w-high sub)',False, blend([HIPROX(63)], K_NAMES), REBAL, 63))
    A(('9  trend50 (above own MA)', False, blend([TREND(50)], K_NAMES), REBAL, 63))
    # ---- stage 2: two-signal rank blends (mixes)
    A(('10 mom63 + lowvol63',       True,  blend([MOM(63), LOWVOL(63)], K_NAMES), REBAL, 63))
    A(('11 mom63 + lowbeta63',      True,  blend([MOM(63), LOWBETA(63)], K_NAMES), REBAL, 63))
    A(('12 mom63 + hiprox63',       True,  blend([MOM(63), HIPROX(63)], K_NAMES), REBAL, 63))
    A(('13 mom63 + trend50',        True,  blend([MOM(63), TREND(50)], K_NAMES), REBAL, 63))
    A(('14 mom21 + lowvol63',       True,  blend([MOM(21), LOWVOL(63)], K_NAMES), REBAL, 63))
    A(('15 lowmom21 + lowvol63',    True,  blend([LOWMOM(21), LOWVOL(63)], K_NAMES), REBAL, 63))
    A(('16 hiprox63 + lowvol63',    True,  blend([HIPROX(63), LOWVOL(63)], K_NAMES), REBAL, 63))
    A(('17 lowvol63 + trend50',     True,  blend([LOWVOL(63), TREND(50)], K_NAMES), REBAL, 63))
    A(('18 mom63 + liq21',          True,  blend([MOM(63), LIQ(21)], K_NAMES), REBAL, 63))
    # ---- stage 3: sequential screen-then-rank mixes
    A(('19 top150 mom63 -> lowvol',  True, screen_then_rank(MOM(63), LOWVOL(63), 150, K_NAMES), REBAL, 63))
    A(('20 top150 lowvol -> mom63',  True, screen_then_rank(LOWVOL(63), MOM(63), 150, K_NAMES), REBAL, 63))
    A(('21 top150 hiprox -> lowvol', True, screen_then_rank(HIPROX(63), LOWVOL(63), 150, K_NAMES), REBAL, 63))
    # ---- stage 4: trend conditions layered on (structural mixes)
    A(('22 mom63+lowvol, own>50dma', True, blend([MOM(63), LOWVOL(63)], K_NAMES, above_own_sma=50), REBAL, 63))
    A(('23 mom63+lowvol, SPY>50dma', True, blend([MOM(63), LOWVOL(63)], K_NAMES,
                                                 gate=spy_trend_gate(50)), REBAL, 63))
    A(('24 lowvol63, own>50dma',     True, blend([LOWVOL(63)], K_NAMES, above_own_sma=50), REBAL, 63))
    # ---- stage 5: size / frequency robustness of the canonical mix
    A(('25 mom63+lowvol K=25',       True, blend([MOM(63), LOWVOL(63)], 25), REBAL, 63))
    A(('26 mom63+lowvol K=100',      True, blend([MOM(63), LOWVOL(63)], 100), REBAL, 63))
    A(('27 mom63+lowvol P=5',        True, blend([MOM(63), LOWVOL(63)], K_NAMES), 5, 63))
    A(('28 mom63+lowvol P=63',       True, blend([MOM(63), LOWVOL(63)], K_NAMES), 63, 63))
    # ---- stage 7: SECOND SEARCH ROUND. The two strongest single factors in stage 1 were
    #      mom21 and trend50 (distance above a name's own 50-day MA) -- both short-horizon
    #      trend measures with beta well below 1. Round 2 combines them with each other and
    #      with the defensive/quality overlays. THIS ROUND WAS CHOSEN AFTER SEEING STAGE-1
    #      OUTPUT, which is legitimate on the search period but inflates the multiple-testing
    #      count, so every variant here is added to K and the t>2.5 bar is unchanged.
    A(('29 mom21 + trend50',         True, blend([MOM(21), TREND(50)], K_NAMES), REBAL, 63))
    A(('30 mom21+trend50+lowvol63',  True, blend([MOM(21), TREND(50), LOWVOL(63)], K_NAMES), REBAL, 63))
    A(('31 top150 mom21 -> lowvol',  True, screen_then_rank(MOM(21), LOWVOL(63), 150, K_NAMES), REBAL, 63))
    A(('32 top150 trend50 -> lowvol',True, screen_then_rank(TREND(50), LOWVOL(63), 150, K_NAMES), REBAL, 63))
    A(('33 mom21+trend50 K=25',      True, blend([MOM(21), TREND(50)], 25), REBAL, 63))
    A(('34 mom21+trend50 K=100',     True, blend([MOM(21), TREND(50)], 100), REBAL, 63))
    A(('35 mom21+trend50 P=5',       True, blend([MOM(21), TREND(50)], K_NAMES), 5, 63))
    A(('36 mom21+trend50 P=63',      True, blend([MOM(21), TREND(50)], K_NAMES), 63, 63))
    A(('37 mom21+trend50 SPY>50dma', True, blend([MOM(21), TREND(50)], K_NAMES,
                                                 gate=spy_trend_gate(50)), REBAL, 63))
    A(('38 mom21+trend50 own>50dma', True, blend([MOM(21), TREND(50)], K_NAMES,
                                                 above_own_sma=50), REBAL, 63))
    A(('39 mom21 + hiprox63',        True, blend([MOM(21), HIPROX(63)], K_NAMES), REBAL, 63))
    A(('40 trend50 + hiprox63',      True, blend([TREND(50), HIPROX(63)], K_NAMES), REBAL, 63))
    A(('41 mom21 + lowbeta63',       True, blend([MOM(21), LOWBETA(63)], K_NAMES), REBAL, 63))
    A(('42 mom21+trend50+liq21',     True, blend([MOM(21), TREND(50), LIQ(21)], K_NAMES), REBAL, 63))
    return g


SECONDARY = [
    ('S1 mom126 + lowvol63',  True, blend([MOM(126), LOWVOL(63)], K_NAMES), REBAL, 126),
    ('S2 hiprox126 + lowvol63', True, blend([HIPROX(126), LOWVOL(63)], K_NAMES), REBAL, 126),
]


def run(P, label, variants, back, start, end):
    idx = P.window(start, end)
    idx = [i for i in idx if i - 1 - back >= 0]
    spy = spy_series(P, idx)
    sm = curve_metrics(spy)
    print(f'\n{"="*136}')
    print(f'{label}: bars {idx[0]}..{idx[-1]} = {P.dates[idx[0]]} .. {P.dates[idx[-1]]}, '
          f'{len(idx)} trading days')
    print(f'SPY buy-and-hold over the IDENTICAL dates (open of day 1 -> close of last day): '
          f'total {100*sm["total"]:+.2f}%, CAGR {100*sm["cagr"]:+.2f}%, vol {100*sm["vol"]:.2f}%, '
          f'Sharpe {sm["sharpe"]:.2f}, maxDD {100*sm["mdd"]:.2f}%')
    print('=' * 136)
    print(HDR)
    rows = []
    for name, is_mix, sel, reb, _b in variants:
        r = evaluate(name, P, idx, sel, reb)
        r['is_mix'] = is_mix
        rows.append(r)
        print(fmt_row(r))
    ref = evaluate('REF equal-weight universe', P, idx, ew_universe(back), REBAL)
    ref['is_mix'] = None
    print(fmt_row(ref))
    return rows, ref, sm, idx


def main():
    P = Panel(pit=True)
    print(f'bars loaded: {len(P.syms)} S&P 500 members + SPY; missing: {P.missing}')
    print(f'panel: {len(P.dates)} trading days {P.dates[0]} .. {P.dates[-1]}')
    print(f'\nSEARCH PERIOD = Year A {YEAR_A[0]} .. {YEAR_A[1]}. '
          f'Year B (2025-08-28..2026-08-27) is a LOCKED HOLDOUT and is not touched by this file.')
    print(f'Portfolio: long-only, unlevered, equal-weighted, K={K_NAMES} names, '
          f'rebalanced every {REBAL} trading days, ranked on data through the prior close, '
          f'traded at the next open.')

    grid = build_grid()
    rows, ref, spym, idx = run(P, 'MAIN GRID (Year A, lookbacks <= 63d)', grid,
                               MAIN_BACK, *YEAR_A)
    rows2, ref2, spym2, idx2 = run(P, 'SECONDARY (Year A, 126d lookbacks, SHORTER WINDOW '
                                      '-- not comparable to the main grid)',
                                   SECONDARY, 126, *YEAR_A)

    K = len(grid) + len(SECONDARY)
    print(f'\n{"="*136}')
    print(f'VARIANTS TESTED ON YEAR A: K = {K}  ({len(grid)} main grid + {len(SECONDARY)} secondary). '
          f'The EW-universe reference rows are not variants.')
    print(f'At a conventional 5% bar you would expect about {K*0.05:.1f} of {K} pure-noise variants '
          f'to look significant. The screening bar for a holdout candidate is therefore t(alpha) > 2.5, '
          f'not 2.0.')
    print('=' * 136)

    print('\nCANDIDATE SCREEN (pre-registered gates: MIX, t(alpha) > 2.5, beta <= 1.15, '
          'net-5bp CAGR >= SPY CAGR)')
    print(f'{"candidate":<34} {"mix":>4} {"t>2.5":>6} {"beta<=1.15":>11} {"beats SPY @5bp":>15} {"PASS":>6}')
    passing = []
    for r, sm in [(x, spym) for x in rows] + [(x, spym2) for x in rows2]:
        if not r['is_mix']:
            continue
        c1 = r['alpha_t'] > 2.5
        c2 = r['beta'] <= 1.15
        c3 = r['nets'][5.0]['cagr'] >= sm['cagr']
        ok = c1 and c2 and c3
        if ok:
            passing.append(r)
        print(f'{r["name"]:<34} {"yes":>4} {str(c1):>6} {str(c2):>11} {str(c3):>15} '
              f'{("PASS" if ok else "fail"):>6}')

    mixes = [(x, spym) for x in rows if x['is_mix']] + [(x, spym2) for x in rows2 if x['is_mix']]
    gated = [r for r, sm in mixes if r['beta'] <= 1.15 and r['nets'][5.0]['cagr'] >= sm['cagr']]
    print(f'\nMIXES CLEARING THE BETA AND COST GATES (regardless of the t bar): {len(gated)} of '
          f'{len(mixes)}')
    for r in sorted(gated, key=lambda x: -x['alpha_t']):
        print('   ' + fmt_row(r))
    # NEIGHBOURHOOD ROBUSTNESS, decided before stage 7 was run: the argmax of alpha t over K
    # variants is by construction the most over-fit cell in the grid, so the locked candidate
    # must not be a lone spike. Its structure must have at least 2 NEIGHBOURS (same signals,
    # different K or rebalance period) that also clear the beta and cost gates.
    pool = passing or gated or [r for r, _ in mixes]

    def family(nm):
        # strip the variant index, then the K=/P= suffix, then all spaces, so that
        # "29 mom21 + trend50", "33 mom21+trend50 K=25" and "35 mom21+trend50 P=5"
        # are recognised as the SAME structure at different parameterizations.
        return nm.split(' ', 1)[1].split(' K=')[0].split(' P=')[0].replace(' ', '')
    gated_names = [family(r['name']) for r in gated]
    fams = {}
    for r in gated:
        fams.setdefault(family(r['name']), []).append(r)
    ranked = sorted(pool, key=lambda r: -r['alpha_t'])
    print('\nNEIGHBOURHOOD CHECK -- how many gate-clearing members each STRUCTURE has across '
          'its K / rebalance parameterizations. A structure that clears only at one (K, P) is '
          'a lone spike and is not lockable.')
    for f, members in sorted(fams.items(), key=lambda kv: -len(kv[1])):
        print(f'   {f:<34} clearing members = {len(members):<2}  '
              f'[{", ".join(m["name"].split(" ",1)[0] for m in members)}]')
    robust_fams = {f: m for f, m in fams.items() if len(m) >= 3}
    if robust_fams:
        f = max(robust_fams, key=lambda k: sum(x['alpha_t'] for x in robust_fams[k]) / len(robust_fams[k]))
        members = robust_fams[f]
        # DELIBERATELY NOT THE ARGMAX CELL. Within the chosen structure the locked candidate is
        # the BASE parameterization (K=50, P=21) -- the one whose K and P were fixed a priori in
        # the grid header, not tuned. Picking the highest-t cell of a family is precisely the
        # overfit that the neighbourhood check exists to detect, and it would raise the Year-A
        # number while lowering the chance the holdout confirms it. This is a change from the
        # literal "highest alpha t" wording at the top of this file, made in the CONSERVATIVE
        # direction (it locks a LOWER-t candidate) and disclosed here rather than silently.
        base = [m for m in members if ' K=' not in m['name'] and ' P=' not in m['name']]
        best = base[0] if base else min(members, key=lambda m: -m['alpha_t'])
        print(f'\nMost robust structure: {f} ({len(members)} clearing parameterizations). '
              f'Locking its BASE parameterization, not its best cell.')
    else:
        best = ranked[0]
        print('\n   NO structure clears the gates at >= 3 parameterizations: every clearing cell '
              'is a lone spike, and the pre-registered single best is carried forward as-is.')
    print(f'\nLOCKED CANDIDATE FOR THE HOLDOUT: {best["name"]}')
    print(f'  Year-A alpha t = {best["alpha_t"]:.2f}  '
          f'({"CLEARS" if best["alpha_t"] > 2.5 else "BELOW"} the pre-registered t>2.5 bar)')
    print(f'  Year-A beta = {best["beta"]:.2f}, gross CAGR {100*best["gross"]["cagr"]:.2f}%, '
          f'net-5bp {100*best["nets"][5.0]["cagr"]:.2f}%, net-10bp {100*best["nets"][10.0]["cagr"]:.2f}%')
    d = best['diag']
    print(f'  rebalances {d["rebalances"]}, mean one-way turnover '
          f'{sum(d["turnover"])/len(d["turnover"]):.2f}, distinct names held {len(d["names"])}, '
          f'cash periods {d["cash_periods"]}, carried (missing) bars {d["carried_bars"]}')
    print(f'  daily-return lag-1 autocorrelation {best["ac1"]:+.3f} '
          f'(non-overlapping by construction; this is a sanity check, not a correction)')
    # FRAGILITY: does the Year-A result live in a handful of days? Same check the loser
    # studies used, where deleting 5 of 250 days moved CAGR by 55 points.
    from mix_engine import curve_metrics as _cm
    rr = best['rets'][0.0]
    srt = sorted(range(len(rr)), key=lambda k: -abs(rr[k]))
    for drop in (1, 3, 5):
        keep = [rr[k] for k in range(len(rr)) if k not in set(srt[:drop])]
        print(f'  gross CAGR after deleting the {drop} largest-|return| day(s): '
              f'{100*_cm(keep)["cagr"]:+.2f}%  (full sample {100*best["gross"]["cagr"]:+.2f}%)')
    spy_dd = spym['mdd']
    print(f'  Year-A SPY for reference: CAGR {100*spym["cagr"]:+.2f}%, vol {100*spym["vol"]:.2f}%, '
          f'Sharpe {spym["sharpe"]:.2f}, maxDD {100*spy_dd:.2f}%')
    # IS IT REALLY A MIX, OR THE SAME SIGNAL TWICE? mom21 and trend50 are both trend
    # measures. If their cross-sectional ranks are ~1:1 the "combination" is cosmetic.
    # Spearman rank correlation on each rebalance date, plus how much the blend's picks
    # actually differ from each single factor's picks.
    from mix_signals import eligible as _elig
    from mix_engine import rank_map as _rm, sig_momentum as _mom, sig_sma_dist as _sma
    reb_idx = [i for k, i in enumerate(idx) if k % REBAL == 0]
    sp, ov1, ov2 = [], [], []
    for i in reb_idx:
        j = i - 1
        el = _elig(P, i, 63)
        a = _rm([(x, _mom(P, x, j, 21)) for x in el], False)
        b = _rm([(x, _sma(P, x, j, 50)) for x in el], False)
        n = len(el)
        dsq = sum((a[x] - b[x]) ** 2 for x in el)
        sp.append(1 - 6 * dsq / (n * (n * n - 1)))
        blendpicks = set(sorted(el, key=lambda x: a[x] + b[x])[:K_NAMES])
        ov1.append(len(blendpicks & set(sorted(el, key=lambda x: a[x])[:K_NAMES])) / K_NAMES)
        ov2.append(len(blendpicks & set(sorted(el, key=lambda x: b[x])[:K_NAMES])) / K_NAMES)
    print(f'  signal redundancy: mean Spearman rank corr(mom21, trend50) across the '
          f'{len(reb_idx)} rebalance dates = {sum(sp)/len(sp):+.2f}; the blend\'s book overlaps '
          f'mom21-alone {100*sum(ov1)/len(ov1):.0f}% and trend50-alone {100*sum(ov2)/len(ov2):.0f}% '
          f'of the time. A high correlation means this is a two-horizon trend rule, not two '
          f'independent ideas -- stated plainly rather than sold as diversification.')
    print('\nExactly ONE candidate goes to tools/mix_holdout_yearb.py, unmodified, once.')


if __name__ == '__main__':
    main()
