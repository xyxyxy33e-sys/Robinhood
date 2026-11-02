#!/usr/bin/env python3
"""v4 candidate comparison (run 2026-11-02 on data/daily/closes.csv through 2026-10-30).

Same engine and caveats as backtest.py: close-to-close fills, 5 bp per side, and a universe
picked in 2026 with hindsight, so compare against 'EW buy&hold' of the same 29 names.
New here:
  * coarse sector buckets and a per-bucket cap on the reversal book;
  * the 30/70 momentum/reversal blend (two sleeves, each rebalanced on its own schedule);
  * an out-of-sample window: 2026-10-05..2026-10-30 was not in the data v3 was chosen on.
"""
import csv, math, os, statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = list(csv.reader(open(os.path.join(ROOT, 'data', 'daily', 'closes.csv'))))
hdr = rows[0][1:]; D = [r[0] for r in rows[1:]]; P = [[float(x) for x in r[1:]] for r in rows[1:]]
S = [s for s in hdr if s != 'SPY']; ix = {s: i for i, s in enumerate(hdr)}
T = len(D)

# Coarse buckets: names in one bucket tend to fall together.
BUCKET = {}
for b, names in {
    'ai_infra': 'AMD AVGO MU NVDA TSM ANET VRT',
    'software': 'CRM CRWD MSFT NET NOW ORCL PLTR',
    'internet': 'AMZN APP GOOGL META NFLX SHOP',
    'fin':      'COIN HOOD JPM V',
    'other':    'AAPL LLY UNH XOM TSLA',
}.items():
    for s in names.split(): BUCKET[s] = b
assert set(BUCKET) == set(S), set(S) ^ set(BUCKET)

def ret(t, s, k): return P[t][ix[s]] / P[t - k][ix[s]] - 1
ens = lambda t, s: -sum(ret(t, s, k) for k in (4, 5, 6, 7, 8)) / 5   # v3 score (higher = more oversold)
mom = lambda t, s: ret(t, s, 126)

def pick(score, n, buf=None, cap=None):
    """Top-n by score, held names kept while in top-buf, at most `cap` per bucket."""
    def f(t, w):
        r = sorted(S, key=lambda s: -score(t, s))
        out, cnt = [], {}
        def ok(s): return cap is None or cnt.get(BUCKET[s], 0) < cap
        def add(s): out.append(s); cnt[BUCKET[s]] = cnt.get(BUCKET[s], 0) + 1
        if buf:
            for s in r[:buf]:
                if s in w and len(out) < n and ok(s): add(s)
        for s in r:
            if len(out) >= n: break
            if s not in out and ok(s): add(s)
        return out
    return f

def series(fn, cost=0.0005, start=11, end=None, every=1):
    """Daily net returns of an equal-weight book rebalanced every `every` days."""
    end = end or T - 1; w = {}; out = []
    for t in range(start, end):
        c = 0
        if (t - start) % every == 0:
            tgt = fn(t, w); tw = {s: 1 / len(tgt) for s in tgt}
            c = sum(abs(tw.get(s, 0) - w.get(s, 0)) for s in set(tw) | set(w)) * cost; w = tw
        r = sum(wt * (P[t + 1][ix[s]] / P[t][ix[s]] - 1) for s, wt in w.items())
        out.append((1 - c) * (1 + r) - 1)
        g = {s: wt * P[t + 1][ix[s]] / P[t][ix[s]] for s, wt in w.items()}; tot = sum(g.values())
        w = {s: v / tot for s, v in g.items()}
    return out

def stats(dr):
    nav = pk = 1; mdd = 0
    for r in dr: nav *= 1 + r; pk = max(pk, nav); mdd = min(mdd, nav / pk - 1)
    vol = st.pstdev(dr) * math.sqrt(252)
    return (nav - 1) * 100, (st.mean(dr) * 252 / vol if vol else 0), mdd * 100

def blend(a, b, wa):  # fixed-weight mix of two sleeves' daily returns
    return [wa * x + (1 - wa) * y for x, y in zip(a, b)]

def build(start, end=None):
    ew = series(lambda t, w: (w and list(w)) or S, start=start, end=end, every=10 ** 9)
    spy = series(lambda t, w: ['SPY'], start=start, end=end, every=10 ** 9)
    v3 = series(pick(ens, 8, 12), start=start, end=end)
    v3c3 = series(pick(ens, 8, 12, cap=3), start=start, end=end)
    v3c2 = series(pick(ens, 8, 12, cap=2), start=start, end=end)
    m = series(pick(mom, 8), start=start, end=end, every=21)
    mc = series(pick(mom, 8, cap=3), start=start, end=end, every=21)
    return [
        ('SPY', spy), ('EW buy&hold (29)', ew),
        ('v3 reversal (live)', v3),
        ('v3 + cap 3/bucket', v3c3),
        ('v3 + cap 2/bucket', v3c2),
        ('Momentum monthly', m),
        ('Blend 30/70 mom/rev', blend(m, v3, .3)),
        ('Blend 30/70 + cap 3', blend(mc, v3c3, .3)),
        ('Blend 50/50 + cap 3', blend(mc, v3c3, .5)),
    ]

def at(date):  # index of first row on/after date
    return next(i for i, d in enumerate(D) if d >= date)

WINDOWS = [
    ('Full history (126d warm-up for momentum)', 126, None),
    ('In-sample Apr..Oct 2 (what v3 was chosen on)', 126, at('2026-10-05')),
    ('OUT-OF-SAMPLE Oct 5..Oct 30 (live period)', at('2026-10-02'), None),
]
if __name__ == '__main__':
    for title, a, b in WINDOWS:
        print(f"\n=== {title}: {D[a]} -> {D[(b or T - 1)]} ===")
        print(f"{'':26}{'TOT%':>8}{'SHRP':>6}{'MDD%':>7}")
        for name, dr in build(a, b):
            tot, sh, mdd = stats(dr)
            print(f"{name:26}{tot:+8.1f}{sh:6.2f}{mdd:+7.1f}")

    # Regime gate: scale the v3 book down when the equal-weight universe index closes below
    # its k-day average. Added after looking at the October losses, so treat its
    # out-of-sample numbers as hindsight, not evidence.
    idx = [sum(P[t][ix[s]] / P[0][ix[s]] for s in S) / len(S) for t in range(T)]
    def gated(k, off, start, end=None):
        v = series(pick(ens, 8, 12), start=start, end=end); out = []; prev = 1
        for i, t in enumerate(range(start, end or T - 1)):
            e = 1 if idx[t] > sum(idx[t - j] for j in range(k)) / k else off
            out.append(e * v[i] - abs(e - prev) * 0.0005); prev = e
        return out
    print("\n=== Regime gate on v3 (universe vs its 20-day average) ===")
    print(f"{'':26}" + "".join(f"{w[0].split(' ')[0]:>22}" for w in WINDOWS))
    for off in (1.0, 0.5, 0.0):
        cells = []
        for _, a, b in WINDOWS:
            tot, sh, mdd = stats(gated(20, off, a, b)); cells.append(f"{tot:+8.1f}% mdd{mdd:+6.1f}")
        print(f"{'exposure when below: '+str(off):26}" + "".join(f"{c:>22}" for c in cells))
