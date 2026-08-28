#!/usr/bin/env python3
"""Selector library shared by the Year-A search and the Year-B holdout.

Kept in its own file for ONE reason: the holdout runner must be able to build the
locked candidate from the IDENTICAL code the search used, without importing the
search grid (importing the grid would risk running Year-A-tuned code paths, and
more importantly it keeps the locked candidate's definition in a file that is not
edited after the holdout is opened).

A selector is a callable select(P, i) -> [symbols] where i is the bar index of the
TRADE day. Every signal inside is computed on bar j = i-1 (the previous close) or
earlier. The trade-day bar is touched only to confirm the name has a real opening
print, which is information available at the moment the market-on-open order fills.

ELIGIBILITY (identical for every candidate, so ranking differences are the only
thing being compared):
  - point-in-time additions filter: date_added <= trade date
  - unbroken close history over the full lookback the signal needs, ending at j
  - a positive open on the trade day
  - prior close >= $5, 21-day median dollar volume >= $5m   (liquidity screen only)

RANK BLENDING. Signals are combined on RANKS, not on raw z-scores, because the raw
distributions have wildly different scales and tails (63-day momentum ranges over
hundreds of percent; realized vol over a factor of ten) and a z-score blend would be
silently dominated by whichever signal had the fatter tail that month. Blended score
= sum(weight_k * rank_k), lowest = most preferred.

SEQUENTIAL (SCREEN-THEN-RANK) mixes are provided as a separate composition because
they are a genuinely different rule from a rank blend, not a reparameterization:
"take the top M by A, then the best K of those by B" concentrates in the intersection
where a blend accepts a name that is extreme on one signal and mediocre on the other.

MARKET GATE. A gate is a market-level condition evaluated on bar j; when it is False
the selector returns an empty list and the simulator holds CASH (0% return, no cost)
for that whole rebalance period. Cash periods are counted and printed, never hidden.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mix_engine import (MIN_PRICE, MIN_DOLLAR_VOL, dollar_vol, rank_map,
                        sig_momentum, sig_vol, sig_beta, sig_high_prox, sig_sma_dist,
                        spy_above_sma)


def eligible(P, i, need_back):
    """Names that may be selected for a trade at bar i's open."""
    j = i - 1
    d = P.dates[i]
    out = []
    for s in P.syms:
        if P.pit and P.members.get(s, '9999') > d:
            continue
        if P.o[s][i] is None or P.o[s][i] <= 0:
            continue
        if not P.hist_ok(s, j, need_back):
            continue
        if P.c[s][j] < MIN_PRICE:
            continue
        if dollar_vol(P, s, j) < MIN_DOLLAR_VOL:
            continue
        out.append(s)
    return out


# --------------------------------------------------------------- signal adapters
def MOM(lb, skip=0):
    return (f'mom{lb}' + (f's{skip}' if skip else ''), lb + skip,
            lambda P, s, j: sig_momentum(P, s, j, lb + skip, skip), False)


def LOWMOM(lb, skip=0):
    """Cross-sectional REVERSAL: the weakest trailing return is most preferred."""
    return (f'lowmom{lb}' + (f's{skip}' if skip else ''), lb + skip,
            lambda P, s, j: sig_momentum(P, s, j, lb + skip, skip), True)


def LOWVOL(lb):
    return (f'lowvol{lb}', lb, lambda P, s, j: sig_vol(P, s, j, lb), True)


def HIVOL(lb):
    return (f'hivol{lb}', lb, lambda P, s, j: sig_vol(P, s, j, lb), False)


def LOWBETA(lb):
    return (f'lowbeta{lb}', lb, lambda P, s, j: sig_beta(P, s, j, lb), True)


def HIPROX(lb):
    return (f'hiprox{lb}', lb, lambda P, s, j: sig_high_prox(P, s, j, lb), False)


def TREND(lb):
    return (f'trend{lb}', lb, lambda P, s, j: sig_sma_dist(P, s, j, lb), False)


def LIQ(lb=21):
    return (f'liq{lb}', lb, lambda P, s, j: dollar_vol(P, s, j, lb), False)


# --------------------------------------------------------------- compositions
def blend(sigs, k, weights=None, gate=None, need_back=63, above_own_sma=None):
    """Rank-blend selector. sigs = [SIGNAL tuples]. weights default to equal."""
    ws = weights or [1.0] * len(sigs)
    need = max([need_back] + [s[1] for s in sigs] + ([above_own_sma] if above_own_sma else []))
    cache = {}

    def select(P, i):
        if i in cache:
            return cache[i]
        j = i - 1
        if gate is not None and not gate(P, j):
            cache[i] = []
            return []
        elig = eligible(P, i, need)
        if above_own_sma:
            elig = [s for s in elig if sig_sma_dist(P, s, j, above_own_sma) > 0]
        if len(elig) < k:
            cache[i] = []
            return []
        total = {s: 0.0 for s in elig}
        for w, (_, _, fn, asc) in zip(ws, sigs):
            pairs = [(s, fn(P, s, j)) for s in elig]
            pairs = [(s, v) for s, v in pairs if v is not None]
            rm = rank_map(pairs, asc)
            for s in elig:
                total[s] += w * rm.get(s, len(elig))
        picks = sorted(elig, key=lambda s: total[s])[:k]
        cache[i] = picks
        return picks
    return select


def screen_then_rank(first, second, m, k, gate=None, need_back=63, above_own_sma=None):
    """Take the top m names by `first`, then the best k of those by `second`."""
    need = max(need_back, first[1], second[1], above_own_sma or 0)
    cache = {}

    def select(P, i):
        if i in cache:
            return cache[i]
        j = i - 1
        if gate is not None and not gate(P, j):
            cache[i] = []
            return []
        elig = eligible(P, i, need)
        if above_own_sma:
            elig = [s for s in elig if sig_sma_dist(P, s, j, above_own_sma) > 0]
        if len(elig) < k:
            cache[i] = []
            return []
        p1 = [(s, first[2](P, s, j)) for s in elig]
        p1 = [(s, v) for s, v in p1 if v is not None]
        r1 = rank_map(p1, first[3])
        short = sorted((s for s, _ in p1), key=lambda s: r1[s])[:max(m, k)]
        p2 = [(s, second[2](P, s, j)) for s in short]
        p2 = [(s, v) for s, v in p2 if v is not None]
        r2 = rank_map(p2, second[3])
        picks = sorted((s for s, _ in p2), key=lambda s: r2[s])[:k]
        cache[i] = picks
        return picks
    return select


def spy_trend_gate(lb):
    def g(P, j):
        v = spy_above_sma(P, j, lb)
        return bool(v) if v is not None else True
    return g
