#!/usr/bin/env python3
"""Engine for the from-scratch search for a LONG-ONLY, UNLEVERED MIX of rules,
built from the 503 cached S&P 500 names, that beats buy-and-hold SPY net of costs.

This file holds NO results and runs NO grid. It provides the universe, the signal
library, an exact share-level portfolio simulator, and the report block. The two
runners are:
    tools/mix_search_yeara.py   -- the SEARCH period (Year A). Explore here only.
    tools/mix_holdout_yearb.py  -- the LOCKED HOLDOUT (Year B). Runs ONCE.

Data loading, weighting and the basic statistics are IMPORTED from
tools/sp500_losers_backtest.py; beta/alpha and the curve metrics are imported from
tools/sp500_losers_equity_curve.py. Nothing is reimplemented.

=====================================================================================
METHODOLOGY -- every choice, and why. Read before trusting any number this produces.
=====================================================================================

0. WHAT KILLED THE SIX EARLIER TESTS TODAY, AND HOW THIS FILE AVOIDS EACH
   a. Leg pooling. Never done here: one PORTFOLIO is one observation, and every
      statistic runs on the series of DAILY PORTFOLIO RETURNS (n = trading days).
   b. Wrong benchmark. The benchmark is REAL SPY buy-and-hold over the IDENTICAL
      dates with the IDENTICAL first-day exposure convention (see 5), not an
      all-period average and not an equal-weight universe of the strategy's own picks.
   c. Lookahead. Every signal is computed through the CLOSE OF THE DAY BEFORE the
      trade and executed at the NEXT OPEN. No rule ever ranks on a close it also
      fills at. See 3.
   d. Overlap. Holding periods here are non-overlapping BY CONSTRUCTION: there is one
      portfolio at a time, rebalanced every P trading days, so the daily return series
      has no double-counted days. Autocorrelation of the daily series is reported.
   e. Volatility drag. Every candidate is a COMPOUNDED equity curve, never a mean
      daily return. A zero-mean 50%-vol strategy loses ~12%/yr; the curve shows it.
   f. Beta masquerading as skill. CAPM beta and alpha vs SPY are reported for every
      candidate with a t-stat on alpha, and beta is a hard screen (see the runner).
   g. Survivorship. Discussed in 8; it is NOT correctable here and every number is an
      upper bound.

1. UNIVERSE AND POINT-IN-TIME ELIGIBILITY.
   All 503 names in data/sp500_members.csv plus SPY. A name is eligible to be SELECTED
   on trade day t only if (i) --pit is on and its date_added <= t (today's membership
   applied backward is the survivorship problem; the additions half of it is
   correctable and is corrected), (ii) it has an unbroken bar history covering the
   longest lookback the signal needs, ending at the close of day t-1, (iii) it has a
   bar with a positive open on day t (known at the open, so not lookahead), and
   (iv) it passes the price/liquidity floors (see 6).

2. PORTFOLIO CONSTRUCTION. Equal-weighted, long-only, fully invested, UNLEVERED. K
   names, rebalanced every P trading days. Equal weight rather than signal weight
   because drop/score weighting mechanically concentrates into the highest-volatility
   names -- the exact failure mode the drop-weighted loser basket showed this morning.
   Cash is held only when a rule explicitly says so (the market-trend gate), and those
   days are counted and printed, never silently skipped.

3. TIMING, EXACTLY. On a rebalance day t: ranks are computed from bars through the
   CLOSE OF DAY t-1; the old book is sold at the OPEN of day t and the new book is
   bought at the OPEN of day t. Between rebalances the book is untouched. This is
   executable: the ranking exists the previous evening, and the order is a
   market-on-open. Nothing in this file ever uses day-t's close to decide day-t's book.

4. THE SIMULATOR IS SHARE-LEVEL, NOT RETURN-LEVEL. Equity is tracked as an actual
   share count per name. On a rebalance day the book is marked at that day's OPEN
   (this correctly captures the overnight gap on the OLD book), cost is charged, and
   the new shares are bought at the same open. On every day the day's closing equity is
   sum(shares * close). Daily return = equity_t / equity_{t-1} - 1. This is exact and
   it handles the intraday handover that a return-level approximation smears.
   Missing bar mid-hold: the name's last available close is carried forward (0% for
   that day) rather than dropping the name, which would silently rebalance for free.
   Missing bars are counted and printed.

5. THE BENCHMARK AND THE CAPM REGRESSOR ARE THE SAME SERIES, AND EXPOSURE IS MATCHED.
   The strategy enters at the OPEN of the first day of the window, so its first-day
   return is open->close. SPY is given the identical convention: first day open->close,
   every later day close->close. After day 1 the strategy holds overnight exactly as
   SPY does, so SPY CLOSE-TO-CLOSE is the matched-exposure regressor here -- unlike the
   daily-flip studies, where the strategy was flat overnight and o2c was required.
   The same SPY series is both the buy-and-hold competitor and the CAPM regressor, so
   the return comparison and the alpha cannot disagree about what "the market" was.
   SPY bars are split-adjusted only: ~1.2%/yr of dividend is MISSING from the SPY line,
   so every comparison below is GENEROUS TO THE STRATEGY by roughly that much.

6. QUALITY / LIQUIDITY FLOORS, applied as a screen and never as a standalone signal:
   minimum prior close of $5 and a minimum 21-day median dollar volume. These exist to
   stop the ranking from being won by names that cannot absorb an order; they are not
   claimed to add return.

7. COSTS. Charged on turnover at each rebalance, multiplicatively on the equity marked
   at the open: cost_fraction = c * one_way_turnover, where one_way_turnover =
   0.5 * sum|w_new - w_old| and c is the ROUND-TRIP cost (5bp, 10bp). A complete
   replacement of the book is turnover 1.0 and costs exactly c. Inception costs c.
   THIS IS THE STRUCTURAL DIFFERENCE FROM THE DAILY-FLIP STUDIES: at P=21 there are
   ~12 rebalances a year, so 5bp round-trip costs ~6bp/yr of drag instead of the
   ~1200bp/yr that 250 daily round trips cost. Turnover is printed so the reader can
   check the cost arithmetic rather than trust it.

8. SURVIVORSHIP, AND WHY ITS SIGN IS NOT OBVIOUS FOR THESE RULES.
   data/sp500_members.csv is TODAY's membership applied backward; names deleted from the
   index during the window are invisible. For the buy-the-losers rules this was an
   unambiguous upward bias. For a MOMENTUM or LOW-VOL rule the sign is murkier -- a
   momentum rule would mostly not have bought the collapsing deletions anyway, but it
   WOULD have bought acquisition targets that popped and then vanished. Either way the
   sample is missing exactly the names whose paths ended badly, and the bias worsens the
   further back the window runs, so Year A is more biased than Year B. All results are an
   UPPER BOUND, and no correction is available in this repo.

9. DATA CONSTRAINT ON LOOKBACKS (this is why there is no 200dma or 52-week-high test).
   The cache begins 2024-07-25, only 24 trading days before Year A starts (2024-08-28).
   A 252-day or 200-day lookback simply does not exist for most of the search period.
   To keep every searched variant comparable on the SAME dates, the search grid caps all
   lookbacks at 63 trading days and the Year-A evaluation window therefore starts at the
   64th bar of the cache (2024-10-23) rather than 2024-08-28. Longer-lookback variants
   are run as a clearly-labelled secondary set on their own shorter window. Signals that
   need a full year of history are NOT TESTABLE on the search period and are excluded
   rather than fitted on the holdout, where history does exist.
"""
import math, os, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sp500_losers_backtest import load_members, load_bars, stats, fmt_pct, BARS, MEMBERS
from sp500_losers_equity_curve import beta_alpha, curve_metrics

TRADING_DAYS = 252
START_EQUITY = 10_000.0
MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 5e6          # 21-day median dollar volume floor
COSTS_BP = (0.0, 5.0, 10.0)


# ------------------------------------------------------------------ panel
class Panel:
    """Aligned price matrix: dates x symbols, with helpers for lookback windows."""

    def __init__(self, pit=True):
        self.members = load_members()
        self.px, self.missing = load_bars(list(self.members) + ['SPY'])
        self.spy = self.px.pop('SPY')
        self.pit = pit
        self.dates = sorted({d for s in self.px for d in self.px[s]} | set(self.spy))
        self.idx = {d: i for i, d in enumerate(self.dates)}
        # per-symbol dense arrays aligned to self.dates (None where no bar)
        self.o, self.c, self.h, self.v = {}, {}, {}, {}
        for s, bars in self.px.items():
            o = [None] * len(self.dates); c = list(o); h = list(o); v = list(o)
            for d, b in bars.items():
                i = self.idx.get(d)
                if i is None:
                    continue
                if b[0] > 0 and b[3] > 0:
                    o[i], h[i], c[i], v[i] = b[0], b[1], b[3], b[4]
            self.o[s], self.c[s], self.h[s], self.v[s] = o, c, h, v
        self.syms = sorted(self.px)
        self.spy_c = [self.spy[d][3] if d in self.spy else None for d in self.dates]
        self.spy_o = [self.spy[d][0] if d in self.spy else None for d in self.dates]

    def window(self, start, end):
        return [i for i, d in enumerate(self.dates) if start <= d <= end]

    def hist_ok(self, s, i, back):
        """True if symbol s has an unbroken close series over bars [i-back, i]."""
        c = self.c[s]
        if i - back < 0:
            return False
        return all(c[j] is not None for j in range(i - back, i + 1))


# ------------------------------------------------------------------ signals
def sig_momentum(P, s, i, lb, skip=0):
    """Return over [i-lb, i-skip], computed through close of bar i. Higher = stronger."""
    c = P.c[s]
    a, b = c[i - lb], c[i - skip]
    return b / a - 1.0


def sig_vol(P, s, i, lb):
    """Annualized realized vol of simple daily returns over the last lb bars."""
    c = P.c[s]
    r = [c[j] / c[j - 1] - 1.0 for j in range(i - lb + 1, i + 1)]
    return statistics.pstdev(r) * math.sqrt(TRADING_DAYS)


def sig_beta(P, s, i, lb):
    c, sc = P.c[s], P.spy_c
    rs, rm = [], []
    for j in range(i - lb + 1, i + 1):
        if sc[j] is None or sc[j - 1] is None:
            return None
        rs.append(c[j] / c[j - 1] - 1.0); rm.append(sc[j] / sc[j - 1] - 1.0)
    mm = sum(rm) / len(rm); ms = sum(rs) / len(rs)
    var = sum((x - mm) ** 2 for x in rm)
    if var <= 0:
        return None
    return sum((a - ms) * (b - mm) for a, b in zip(rs, rm)) / var


def sig_high_prox(P, s, i, lb):
    """close / highest high over the last lb bars. 1.0 = at the high."""
    hh = max(x for x in P.h[s][i - lb + 1:i + 1] if x is not None)
    return P.c[s][i] / hh if hh > 0 else None


def sig_sma_dist(P, s, i, lb):
    """close / SMA(lb) - 1. Positive = above its own moving average."""
    c = P.c[s][i - lb + 1:i + 1]
    m = sum(c) / len(c)
    return P.c[s][i] / m - 1.0 if m > 0 else None


def dollar_vol(P, s, i, lb=21):
    vals = [P.c[s][j] * P.v[s][j] for j in range(i - lb + 1, i + 1)
            if P.c[s][j] is not None and P.v[s][j] is not None]
    return statistics.median(vals) if vals else 0.0


def spy_above_sma(P, i, lb):
    """SPY close at bar i vs its own lb-bar SMA. Market-level trend gate."""
    c = P.spy_c
    if i - lb + 1 < 0 or any(c[j] is None for j in range(i - lb + 1, i + 1)):
        return None
    return c[i] > sum(c[i - lb + 1:i + 1]) / lb


# ------------------------------------------------------------------ ranking helper
def rank_map(pairs, ascending):
    """pairs = [(sym, score)]. Returns {sym: rank}, rank 0 = most preferred."""
    ordered = sorted(pairs, key=lambda x: x[1], reverse=not ascending)
    return {s: r for r, (s, _) in enumerate(ordered)}


# ------------------------------------------------------------------ simulator
def simulate(P, win_idx, select, rebal_every, costs_bp=COSTS_BP, equity0=START_EQUITY):
    """Run one candidate. `select(P, i)` is called on each rebalance day with the
    bar index i of the TRADE day; it must rank using data through bar i-1 only and
    return a list of symbols (possibly empty -> hold cash that period).

    Returns per-cost dicts of daily returns plus diagnostics.
    """
    out = {}
    diag = dict(rebalances=0, turnover=[], cash_periods=0, carried_bars=0,
                picks_per_rebal=[], names=set(), rebal_dates=[])
    for bp in costs_bp:
        c = bp / 10000.0
        shares, cash_mode = {}, True
        eq_prev, rets, first = equity0, [], True
        for k, i in enumerate(win_idx):
            reb = (k % rebal_every == 0)
            if reb:
                # mark the OLD book at today's open (captures the overnight gap)
                if cash_mode:
                    eq_open = eq_prev
                else:
                    eq_open = sum(n * (P.o[s][i] if P.o[s][i] else P.c[s][i]) for s, n in shares.items())
                picks = select(P, i)
                w_old = {}
                if not cash_mode and eq_open > 0:
                    for s, n in shares.items():
                        p = P.o[s][i] if P.o[s][i] else P.c[s][i]
                        w_old[s] = n * p / eq_open
                w_new = {s: 1.0 / len(picks) for s in picks} if picks else {}
                turn = 0.5 * sum(abs(w_new.get(s, 0.0) - w_old.get(s, 0.0))
                                 for s in set(w_old) | set(w_new))
                eq_open *= (1.0 - c * turn)
                shares = {}
                if picks:
                    for s in picks:
                        p = P.o[s][i]
                        shares[s] = eq_open * w_new[s] / p
                    cash_mode = False
                else:
                    cash_mode = True
                if bp == costs_bp[0]:
                    diag['rebalances'] += 1
                    diag['turnover'].append(turn)
                    diag['picks_per_rebal'].append(len(picks))
                    diag['rebal_dates'].append(P.dates[i])
                    diag['names'].update(picks)
                    if not picks:
                        diag['cash_periods'] += 1
                eq_close = eq_open if cash_mode else _mark(P, shares, i, diag, bp == costs_bp[0])
            else:
                eq_close = eq_prev if cash_mode else _mark(P, shares, i, diag, bp == costs_bp[0])
            if first:
                # day 1: the strategy is bought at the open, so its first return is
                # open->close. eq_prev was the pre-trade cash, which is the right base.
                first = False
            rets.append(eq_close / eq_prev - 1.0)
            eq_prev = eq_close
        out[bp] = rets
    return out, diag


def _mark(P, shares, i, diag, count):
    """Mark the book at bar i's close, carrying the last close where a bar is missing."""
    tot = 0.0
    for s, n in shares.items():
        c = P.c[s][i]
        if c is None:
            j = i
            while j >= 0 and P.c[s][j] is None:
                j -= 1
            c = P.c[s][j] if j >= 0 else 0.0
            if count:
                diag['carried_bars'] += 1
        tot += n * c
    return tot


def spy_series(P, win_idx):
    """SPY with the SAME exposure convention as the strategy: first day open->close,
    every later day close->close. This is both the buy-and-hold competitor and the
    matched-exposure CAPM regressor."""
    out = []
    for k, i in enumerate(win_idx):
        if k == 0:
            out.append(P.spy_c[i] / P.spy_o[i] - 1.0)
        else:
            out.append(P.spy_c[i] / P.spy_c[win_idx[k - 1]] - 1.0)
    return out


# ------------------------------------------------------------------ evaluation
def autocorr1(xs):
    n = len(xs)
    m = sum(xs) / n
    num = sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, n))
    den = sum((x - m) ** 2 for x in xs)
    return num / den if den > 0 else float('nan')


def evaluate(name, P, win_idx, select, rebal_every, costs_bp=COSTS_BP):
    rets, diag = simulate(P, win_idx, select, rebal_every, costs_bp)
    spy = spy_series(P, win_idx)
    m0 = curve_metrics(rets[costs_bp[0]])
    ba = beta_alpha(rets[costs_bp[0]], spy)
    row = dict(name=name, diag=diag, spy=spy, rets=rets,
               gross=m0, beta=ba['beta'], alpha_ann=ba['alpha_ann'], alpha_t=ba['t'],
               ac1=autocorr1(rets[costs_bp[0]]),
               nets={bp: curve_metrics(rets[bp]) for bp in costs_bp},
               spy_metrics=curve_metrics(spy))
    return row


HDR = (f'{"candidate":<34} {"CAGR":>8} {"@5bp":>8} {"@10bp":>8} {"vol":>7} '
       f'{"Sh":>6} {"maxDD":>8} {"beta":>6} {"alpha/yr":>9} {"t(a)":>6} {"turn":>6}')


def fmt_row(r):
    g, n5, n10 = r['gross'], r['nets'][5.0], r['nets'][10.0]
    d = r['diag']
    turn = sum(d['turnover']) / len(d['turnover']) if d['turnover'] else 0.0
    return (f'{r["name"]:<34} {100*g["cagr"]:>7.2f}% {100*n5["cagr"]:>7.2f}% '
            f'{100*n10["cagr"]:>7.2f}% {100*g["vol"]:>6.2f}% {g["sharpe"]:>6.2f} '
            f'{100*g["mdd"]:>7.2f}% {r["beta"]:>6.2f} {100*r["alpha_ann"]:>8.2f}% '
            f'{r["alpha_t"]:>6.2f} {turn:>6.2f}')
