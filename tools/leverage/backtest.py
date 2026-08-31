#!/usr/bin/env python3
"""Constant leverage + moving-average circuit breaker -- BACKTEST ENGINE.

Self-contained, standard library only, re-runnable:

    python3 tools/leverage/backtest.py

Reads   data/kairos/etf/{QQQ,QLD,TQQQ,SPY}.csv   (d,o,c  split-adjusted)
        data/kairos/DGS3MO.csv                   (3-month T-bill, FRED)
Writes  data/leverage/daily_series.csv           (audit trail, best config)
Prints  every results table quoted in research/leverage_ma.md

=============================================================================
WHAT IS BEING TESTED
=============================================================================
A binary daily decision -- carry a FIXED leverage target L, or sit in T-bills --
governed by a moving-average circuit breaker on QQQ. Two dimensions crossed:

  1. Base leverage L in {1.0, 1.5, 2.0, 2.5, 3.0} when invested.
     Reached via the LOWEST-MULTIPLE LADDER: L<=1 -> QQQ + cash;
     1<L<=2 -> QQQ/QLD blend; 2<L<=3 -> QLD/TQQQ blend.  Rebalanced ONLY when
     the breaker flips, never on a daily schedule.

  2. Circuit-breaker rule (7):
       bh          -- no filter, always invested (degenerate baseline; this is
                      the rule that WON the prior five-factor study, so it is
                      in the grid by construction, not as an afterthought)
       ma50        -- invested while QQQ > 50dma
       ma100       -- invested while QQQ > 100dma
       ma200       -- invested while QQQ > 200dma
       ma50_and_200-- invested while QQQ > BOTH 50dma and 200dma
       fast_out    -- asymmetric: EXIT on a 50dma break, RE-ENTER only above
                      200dma  (fast out, slow in)
       slow_out    -- asymmetric: EXIT on a 200dma break, RE-ENTER above 50dma
                      (slow out, fast in)

  3. Buffer / no-trade band on the MA crossing, b in {0%, 1%, 2%}:
       enter when close > ma*(1+b), exit when close < ma*(1-b), otherwise HOLD
       the previous state. b=0 is the naive crossing.

  5 L x 7 rules x 3 buffers = 105 grid cells.  The 5x3 = 15 `bh` cells ignore
  the buffer (no MA is consulted), so they collapse to 5 distinct strategies:
  105 cells, 95 DISTINCT configurations.  See the multiple-testing note below.

NO CONVICTION SCALING, NO SHORTS -- both are ruled out by the prior study
(research/kairos_five_factor.md): the five-factor conviction score was INVERTED
at the daily horizon (higher conviction preceded WORSE forward returns,
confirmed four ways), and the short side lost more than cash (SQQQ -4.43% while
QQQ fell -5.21%).  Exposure here is therefore FIXED when on, and cash when off.

=============================================================================
THE BAR
=============================================================================
Primary comparison is buy-and-hold TQQQ (the thing being timed) and
buy-and-hold QQQ (the simplest alternative).  The explicit bar the owner set:
DOES ANYTHING BEAT UNLEVERAGED QQQ BUY-AND-HOLD ON SHARPE?

The prior study's key reframing, which this one inherits: over 2020+, QQQ B&H
had a BETTER Sharpe than TQQQ B&H (0.74 vs 0.72) at less than half the drawdown
(-35.62% vs -81.75%).  Leverage bought return, not risk-adjusted return.  So a
CAGR win over QQQ is not evidence of anything; a Sharpe win would be.

=============================================================================
NO LOOKAHEAD
=============================================================================
The breaker state is computed from day t's CLOSE (close and moving averages
both use closes up to and including t, nothing later).  It is acted on either:
  NEXT-OPEN (primary, fully implementable): filled at day t+1's OPEN.  Cash
    accrues overnight, the rebalance happens at that open, the book is valued
    at that day's close.
  SAME-CLOSE / MOC (secondary): filled at day t's own close as an MOC order.
    Defensible for a pure price rule -- the 50/100/200dma and the close are all
    knowable a few minutes before the bell -- but it is the more optimistic of
    the two, so next-open is primary and both are reported.
Programmatically asserted: every row's target leverage derives from the
STRICTLY PRIOR row's breaker state.

=============================================================================
DATA INTEGRITY
=============================================================================
* REAL TQQQ/QLD price history, never a synthetic multiple of QQQ.  Actual
  traded prices embed the real expense ratio, the daily-reset decay and the
  real bid/ask history.
* TQQQ's ~280 pre-inception bars (volume 0, flat OHLC, flagged `interpolated`
  by the source API) were dropped upstream by tools/kairos/extract_dumps.py.
  Asserted here: TQQQ's first bar is 2010-02-11, its true inception.
* Backtest window therefore starts 2010-02-11.  QQQ history from 2009-01-02 is
  loaded ONLY to warm up the 200dma, so the very first tradable day already
  has a full-length MA.  Warm-up bars are never traded.
* DGS3MO has ~200 blank rows (market holidays / FRED gaps); forward-filled.
* Price-only returns, no dividends, on every leg AND every benchmark.  QQQ's
  ~0.5%/yr yield is thus missing from the QQQ B&H bar too -- this biases
  slightly IN FAVOUR of the strategies and AGAINST the benchmark they must beat.

=============================================================================
POSITION-BASED ACCOUNTING
=============================================================================
The engine holds SHARES and lets weights drift between rebalances.  This is
load-bearing, not a detail: with DAILY rebalancing a leverage target is
route-independent (the prior study measured 2x-via-TQQQ+cash vs 2x-via-QLD at
0.16%/yr apart -- noise).  The routes only differ when positions are HELD, and
the lower-multiple route then wins by ~0.8-0.9% per 126-day hold.  This
strategy holds, so the ladder is used and rebalancing happens only on a flip.

=============================================================================
COSTS
=============================================================================
Swept at 0 / 5 / 10 / 20 bp ROUND TRIP, charged as bps/2 on the notional of
each leg, so a complete exit-and-re-enter cycle pays the quoted round-trip
figure.  Applied to ACTUAL turnover, not a per-trade flat fee.  Base = 10bp.

=============================================================================
SEARCH / HOLDOUT
=============================================================================
SEARCH  = 2010-02-11 .. 2019-12-31   (parameters chosen here, if at all)
HOLDOUT = 2020-01-01 .. end          (opened ONCE, all parameters frozen)

NOTE, stated plainly because it conditions every number below: 2010-2019 is an
almost uninterrupted Nasdaq bull market.  A crash filter has almost nothing to
prove there and will tend to look useless or actively harmful.  The holdout
contains the 2020 COVID crash, the 2022 bear and the 2025 drawdown -- i.e.
essentially all of the stress this strategy exists to handle.  A good holdout
result is therefore partly luck about which period got which stress, and a weak
search result is not damning.  Both are reported; neither is hidden.

=============================================================================
MULTIPLE TESTING
=============================================================================
95 distinct configurations are evaluated (105 grid cells).  THE BEST OF 95 IS
EXPECTED TO LOOK GOOD BY CHANCE.  The full grid is printed, not just winners,
and no configuration is recommended on the strength of topping a table.  The
load-bearing question is what the SEARCH period would have selected in advance
and how that selection then behaved on the holdout.
"""
import csv
import os
import math

ROOT = "/home/user/Robinhood"
ETF = os.path.join(ROOT, "data", "kairos", "etf")
RF_CSV = os.path.join(ROOT, "data", "kairos", "DGS3MO.csv")
OUTDIR = os.path.join(ROOT, "data", "leverage")

INCEPTION = "2010-02-11"          # TQQQ's true first traded bar
SEARCH_END = "2019-12-31"
HOLDOUT_START = "2020-01-01"

TRADING_DAYS = 252
BASE_COST_BPS = 10.0              # round trip
COST_GRID = [0.0, 5.0, 10.0, 20.0]

LEV_GRID = [1.0, 1.5, 2.0, 2.5, 3.0]
BUFFER_GRID = [0.00, 0.01, 0.02]
BREAKERS = ["bh", "ma50", "ma100", "ma200", "ma50_and_200", "fast_out", "slow_out"]
ASSET_MULT = {"QQQ": 1.0, "QLD": 2.0, "TQQQ": 3.0}


# ----------------------------------------------------------------------- loading
def read_etf(sym):
    with open(os.path.join(ETF, f"{sym}.csv")) as fh:
        return {r["d"]: (float(r["o"]), float(r["c"])) for r in csv.DictReader(fh)}


def read_rf():
    """DGS3MO, forward-filled across FRED's blank/'.' holiday rows."""
    out, last = {}, None
    with open(RF_CSV) as fh:
        for r in csv.DictReader(fh):
            v = r["DGS3MO"].strip()
            if v not in ("", "."):
                last = float(v)
            if last is not None:
                out[r["observation_date"]] = last
    return out


def sma(vals, n):
    """Simple moving average; None until n observations exist.  Uses only
    values at or before each index -- no centring, no lookahead."""
    out, s = [], 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def load_panel():
    qqq, qld, tqqq, spy = (read_etf(s) for s in ("QQQ", "QLD", "TQQQ", "SPY"))
    rf = read_rf()
    assert min(tqqq) == INCEPTION, f"TQQQ first bar {min(tqqq)} != {INCEPTION}"

    # QQQ full history (from 2009-01-02) warms the 200dma up.
    wdates = sorted(qqq)
    closes = [qqq[d][1] for d in wdates]
    ma = {n: sma(closes, n) for n in (50, 100, 200)}

    rows, last_rf = [], 0.0
    for i, d in enumerate(wdates):
        if d < INCEPTION:
            continue                                   # warm-up only, never traded
        if not (d in qld and d in tqqq and d in spy):
            continue
        last_rf = rf.get(d, last_rf)
        rows.append({
            "date": d,
            "qqq_o": qqq[d][0], "qqq_c": qqq[d][1],
            "qld_o": qld[d][0], "qld_c": qld[d][1],
            "tqqq_o": tqqq[d][0], "tqqq_c": tqqq[d][1],
            "spy_o": spy[d][0], "spy_c": spy[d][1],
            "ma50": ma[50][i], "ma100": ma[100][i], "ma200": ma[200][i],
            "rf": last_rf,
        })
    for r in rows:
        assert r["ma200"] is not None, f"200dma missing on {r['date']}"
    return rows


# ---------------------------------------------------------------- breaker states
def breaker_states(rows, rule, buf):
    """Binary invested/flat state decided at each row's CLOSE.

    Buffered crossing: go ON above ma*(1+buf), go OFF below ma*(1-buf), and
    otherwise HOLD the prior state.  This is the no-trade band; it is what
    stops a price oscillating around its average from generating a trade a day.
    Seed state = the unbuffered condition on the first row.
    """
    st, out = None, []
    for r in rows:
        c = r["qqq_c"]
        if rule == "bh":
            s = True
        elif rule in ("ma50", "ma100", "ma200"):
            m = r["ma" + rule[2:]]
            if st is None:
                s = c > m
            elif c > m * (1 + buf):
                s = True
            elif c < m * (1 - buf):
                s = False
            else:
                s = st
        elif rule == "ma50_and_200":
            m50, m200 = r["ma50"], r["ma200"]
            if st is None:
                s = c > m50 and c > m200
            elif c > m50 * (1 + buf) and c > m200 * (1 + buf):
                s = True
            elif c < m50 * (1 - buf) or c < m200 * (1 - buf):
                s = False
            else:
                s = st
        elif rule == "fast_out":            # exit on 50dma break, re-enter above 200dma
            m50, m200 = r["ma50"], r["ma200"]
            if st is None:
                s = c > m50 and c > m200
            elif st and c < m50 * (1 - buf):
                s = False
            elif (not st) and c > m200 * (1 + buf):
                s = True
            else:
                s = st
        elif rule == "slow_out":            # exit on 200dma break, re-enter above 50dma
            m50, m200 = r["ma50"], r["ma200"]
            if st is None:
                s = c > m200
            elif st and c < m200 * (1 - buf):
                s = False
            elif (not st) and c > m50 * (1 + buf):
                s = True
            else:
                s = st
        else:
            raise ValueError(rule)
        out.append(s)
        st = s
    return out


def route_ladder(L):
    """Reach L with the LOWEST-multiple combination; cash only below 1x."""
    if L <= 0:
        return {}
    if L <= 1.0:
        return {"QQQ": L}
    if L <= 2.0:
        return {"QQQ": 2.0 - L, "QLD": L - 1.0}
    return {"QLD": 3.0 - L, "TQQQ": L - 2.0}


# ------------------------------------------------------------------------ engine
def daily_rf(annual_pct):
    return (1.0 + annual_pct / 100.0) ** (1.0 / TRADING_DAYS) - 1.0


def px(row, a, f):
    return row[f"{a.lower()}_{f}"]


def run(rows, states, L, cost_bps=BASE_COST_BPS, execution="next_open", collect=False):
    """Position-based simulation.  Holds SHARES; weights drift between flips.

    cost_bps is a ROUND-TRIP figure; bps/2 is charged on each leg's notional.
    """
    side_bps = cost_bps / 2.0
    shares, cash = {}, 1.0
    last_L, equity_prev = 0.0, 1.0
    curve, rets, rfs, levs = [], [], [], []
    n_trades, turnover, recs = 0, 0.0, []

    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]
        L_t = L if states[i - 1] else 0.0        # <- STRICTLY PRIOR row's state
        rf_d = daily_rf(prev["rf"])
        traded = 0

        def pv(row, field):
            return cash + sum(n * px(row, a, field) for a, n in shares.items())

        def rebalance(row, field):
            nonlocal shares, cash, last_L, n_trades, traded, turnover
            eq = pv(row, field)
            tw = route_ladder(L_t)
            notional = sum(abs(tw.get(a, 0.0) * eq - shares.get(a, 0.0) * px(row, a, field))
                           for a in set(list(tw) + list(shares)))
            eq -= side_bps * 1e-4 * notional
            turnover += notional / eq if eq > 0 else 0.0
            shares = {a: w * eq / px(row, a, field) for a, w in tw.items() if w > 0}
            cash = eq - sum(n * px(row, a, field) for a, n in shares.items())
            last_L, n_trades, traded = L_t, n_trades + 1, 1

        if execution == "next_open":
            cash *= (1.0 + rf_d)                 # overnight accrual, then trade
            if L_t != last_L:
                rebalance(cur, "o")
        else:                                     # same_close / MOC at prev close
            if L_t != last_L:
                rebalance(prev, "c")
            cash *= (1.0 + rf_d)

        equity = pv(cur, "c")
        eff = (sum(n * px(cur, a, "c") * ASSET_MULT[a] for a, n in shares.items())
               / equity) if equity > 0 else 0.0
        r = equity / equity_prev - 1.0
        equity_prev = equity
        curve.append(equity); rets.append(r); rfs.append(rf_d); levs.append(eff)

        if collect:
            recs.append({
                "date": cur["date"],
                "qqq_close": f"{cur['qqq_c']:.6f}",
                "ma50": f"{cur['ma50']:.6f}", "ma100": f"{cur['ma100']:.6f}",
                "ma200": f"{cur['ma200']:.6f}",
                "breaker_state_today": int(states[i]),
                "breaker_state_used": int(states[i - 1]),
                "target_leverage": f"{L_t:.4f}",
                "actual_leverage": f"{eff:.4f}",
                "w_qqq": f"{shares.get('QQQ',0.0)*cur['qqq_c']/equity:.4f}",
                "w_qld": f"{shares.get('QLD',0.0)*cur['qld_c']/equity:.4f}",
                "w_tqqq": f"{shares.get('TQQQ',0.0)*cur['tqqq_c']/equity:.4f}",
                "w_cash": f"{cash/equity:.4f}",
                "traded_flag": traded,
                "rf_daily": f"{rf_d:.8f}",
                "portfolio_ret": f"{r:.6f}",
                "equity_curve": f"{equity:.6f}",
            })

    m = metrics(curve, rets, rfs)
    yrs = (len(rows) - 1) / TRADING_DAYS
    m.update({"trades": n_trades, "turnover": turnover,
              "trades_per_yr": n_trades / yrs if yrs else 0.0,
              "mean_lev": sum(levs) / len(levs) if levs else 0.0,
              "pct_invested": 100.0 * sum(1 for x in levs if x > 0) / len(levs)})
    if collect:
        dd = drawdown_series(curve)
        for k, rec in enumerate(recs):
            rec["drawdown"] = f"{dd[k]:.6f}"
        return m, recs
    return m


def drawdown_series(curve):
    out, peak = [], -1e18
    for v in curve:
        peak = max(peak, v)
        out.append(v / peak - 1.0)
    return out


def longest_dd_months(curve):
    """Longest stretch (in months, 21 trading days) spent below a prior peak."""
    peak, worst, run_len = -1e18, 0, 0
    for v in curve:
        if v >= peak:
            peak, run_len = v, 0
        else:
            run_len += 1
            worst = max(worst, run_len)
    return worst / 21.0


def worst_rolling_12m(curve):
    """Worst 252-trading-day return over the curve."""
    n = TRADING_DAYS
    if len(curve) <= n:
        return float("nan")
    return min(curve[i] / curve[i - n] - 1.0 for i in range(n, len(curve)))


def metrics(curve, rets, rf_list):
    if not rets:
        return {}
    yrs = len(rets) / TRADING_DAYS
    cagr = curve[-1] ** (1.0 / yrs) - 1.0 if yrs > 0 and curve[-1] > 0 else float("nan")
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / max(1, len(rets) - 1))
    ex = [rets[i] - rf_list[i] for i in range(len(rets))]
    mex = sum(ex) / len(ex)
    sdex = math.sqrt(sum((r - mex) ** 2 for r in ex) / max(1, len(ex) - 1))
    mdd = min(drawdown_series(curve))
    return {"cagr": cagr, "vol": sd * math.sqrt(TRADING_DAYS),
            "sharpe": (mex / sdex) * math.sqrt(TRADING_DAYS) if sdex > 0 else float("nan"),
            "mdd": mdd, "calmar": cagr / abs(mdd) if mdd < 0 else float("nan"),
            "final": curve[-1], "years": yrs,
            "worst12m": worst_rolling_12m(curve),
            "dd_months": longest_dd_months(curve)}


def buy_hold(rows, asset):
    eq, curve, rets, rfs = 1.0, [], [], []
    for i in range(1, len(rows)):
        r = px(rows[i], asset, "c") / px(rows[i - 1], asset, "c") - 1.0
        eq *= (1.0 + r)
        curve.append(eq); rets.append(r); rfs.append(daily_rf(rows[i - 1]["rf"]))
    m = metrics(curve, rets, rfs)
    m.update({"trades": 1, "turnover": 1.0, "trades_per_yr": 0.0,
              "mean_lev": ASSET_MULT.get(asset, 1.0), "pct_invested": 100.0})
    return m


def slow_out_gated(rows, buf):
    """Robustness counterfactual for `slow_out`: identical rule, except re-entry
    additionally requires QQQ to be above its 200dma.  This removes the one-day
    flicker exposures the raw rule generates below the 200dma and isolates how
    much of its result depends on them."""
    st, out = None, []
    for r in rows:
        c, m50, m200 = r["qqq_c"], r["ma50"], r["ma200"]
        if st is None:
            s = c > m200
        elif st and c < m200 * (1 - buf):
            s = False
        elif (not st) and c > m50 * (1 + buf) and c > m200:
            s = True
        else:
            s = st
        out.append(s); st = s
    return out


def min_hold(states, n):
    """Force every 'invested' run to last at least n bars.  A robustness probe for
    the asymmetric rules: if an edge survives being forbidden to trade daily, it is
    a position; if it evaporates, it was a flicker."""
    out, i = list(states), 0
    while i < len(out):
        if out[i]:
            j = i
            while j < len(out) and out[j]:
                j += 1
            if j - i < n:
                for k in range(i, min(j + n, len(out))):
                    out[k] = True
                i = min(j + n, len(out))
            else:
                i = j
        else:
            i += 1
    return out


def sl(rows, lo=None, hi=None):
    return [r for r in rows if (lo is None or r["date"] >= lo) and (hi is None or r["date"] <= hi)]


def sub(rows, states, lo, hi):
    """Slice rows AND the aligned state list together, keeping one prior row so
    the first in-window day is still driven by a strictly-prior signal."""
    idx = [i for i, r in enumerate(rows)
           if (lo is None or r["date"] >= lo) and (hi is None or r["date"] <= hi)]
    i0, i1 = max(0, idx[0] - 1), idx[-1]
    return rows[i0:i1 + 1], states[i0:i1 + 1]


# ------------------------------------------------------------------ presentation
def fmt(m):
    return (f"{100*m['cagr']:7.2f}% {100*m['vol']:7.2f}% {m['sharpe']:6.2f} "
            f"{100*m['mdd']:8.2f}% {m['calmar']:6.2f} {m['trades_per_yr']:6.1f}")


HDR = f"{'config':34s} {'CAGR':>8s} {'vol':>8s} {'Sharpe':>6s} {'maxDD':>9s} {'Calmr':>6s} {'tr/yr':>6s}"


def main():
    rows = load_panel()
    print(f"panel: {len(rows)} rows  {rows[0]['date']} .. {rows[-1]['date']}")
    srow = sl(rows, None, SEARCH_END)
    hrow = sl(rows, HOLDOUT_START, None)
    print(f"search : {len(srow)} rows  {srow[0]['date']} .. {srow[-1]['date']}")
    print(f"holdout: {len(hrow)} rows  {hrow[0]['date']} .. {hrow[-1]['date']}")

    # ---- lookahead assertion -------------------------------------------------
    st = breaker_states(rows, "ma200", 0.0)
    bad = sum(1 for i in range(2, len(rows))
              if st[i - 1] != (rows[i - 1]["qqq_c"] > rows[i - 1]["ma200"]))
    print(f"\nLOOKAHEAD CHECK 1 (ma200, buffer 0): the state acted on for row i equals the "
          f"condition evaluated at row i-1's close in {len(rows)-2-bad}/{len(rows)-2} rows "
          f"(mismatches: {bad}; must be 0).")
    # Truncation invariance: a state computed on data truncated at row k must equal
    # the state computed on the full series at row k, for EVERY rule and buffer.
    # If any rule peeked forward, truncation would change its answer.
    worst = 0
    for rule in BREAKERS:
        for b in BUFFER_GRID:
            full = breaker_states(rows, rule, b)
            for k in (900, 1800, 2700, 3600):
                if breaker_states(rows[:k + 1], rule, b)[k] != full[k]:
                    worst += 1
    print(f"LOOKAHEAD CHECK 2 (all {len(BREAKERS)} rules x {len(BUFFER_GRID)} buffers, "
          f"truncation invariance at 4 cut points): {worst} mismatches (must be 0).")

    # ---- benchmarks ----------------------------------------------------------
    print("\n" + "=" * 96)
    print("BENCHMARKS (buy and hold, price-only, no dividends)")
    print("=" * 96)
    print(HDR)
    for label, rset in (("SEARCH", srow), ("HOLDOUT", hrow), ("FULL", rows)):
        for a in ("QQQ", "QLD", "TQQQ", "SPY"):
            print(f"{label + ' ' + a + ' B&H':34s} " + fmt(buy_hold(rset, a)))
        print("-" * 96)

    qqq_s = buy_hold(srow, "QQQ"); qqq_h = buy_hold(hrow, "QQQ")
    tqqq_s = buy_hold(srow, "TQQQ"); tqqq_h = buy_hold(hrow, "TQQQ")

    # ---- full grid -----------------------------------------------------------
    states_cache = {(rule, b): breaker_states(rows, rule, b)
                    for rule in BREAKERS for b in BUFFER_GRID}
    grid = []
    for L in LEV_GRID:
        for rule in BREAKERS:
            for b in BUFFER_GRID:
                stt = states_cache[(rule, b)]
                sr, ss = sub(rows, stt, None, SEARCH_END)
                hr, hs = sub(rows, stt, HOLDOUT_START, None)
                grid.append({
                    "L": L, "rule": rule, "buf": b,
                    "name": f"L{L:.1f}_{rule}_b{int(b*100)}",
                    "s": run(sr, ss, L), "h": run(hr, hs, L),
                })

    print("\n" + "=" * 132)
    print(f"FULL GRID -- {len(grid)} cells "
          f"({len(LEV_GRID)}L x {len(BREAKERS)}rules x {len(BUFFER_GRID)}buffers); "
          f"the {len(LEV_GRID)*len(BUFFER_GRID)} 'bh' cells ignore the buffer, "
          f"so {len(grid) - len(LEV_GRID)*(len(BUFFER_GRID)-1)} are DISTINCT.")
    print(f"ladder route, next-open execution, {BASE_COST_BPS:.0f}bp round trip")
    print("=" * 132)
    h = (f"{'config':22s} | {'SEARCH  CAGR':>12s} {'Shrp':>5s} {'maxDD':>8s} {'Clmr':>5s} {'t/yr':>5s}"
         f" | {'HOLDOUT CAGR':>12s} {'Shrp':>5s} {'maxDD':>8s} {'Clmr':>5s} {'t/yr':>5s} {'%inv':>5s}")
    print(h); print("-" * 132)
    for g in grid:
        s, hh = g["s"], g["h"]
        print(f"{g['name']:22s} | {100*s['cagr']:11.2f}% {s['sharpe']:5.2f} {100*s['mdd']:7.2f}% "
              f"{s['calmar']:5.2f} {s['trades_per_yr']:5.1f} | "
              f"{100*hh['cagr']:11.2f}% {hh['sharpe']:5.2f} {100*hh['mdd']:7.2f}% "
              f"{hh['calmar']:5.2f} {hh['trades_per_yr']:5.1f} {hh['pct_invested']:5.1f}")

    # ---- THE BAR -------------------------------------------------------------
    print("\n" + "=" * 96)
    print("THE BAR: does anything beat QQQ BUY-AND-HOLD on Sharpe?")
    print("=" * 96)
    for lab, key, bm in (("SEARCH", "s", qqq_s), ("HOLDOUT", "h", qqq_h)):
        beat = [g for g in grid if g[key]["sharpe"] > bm["sharpe"]]
        print(f"\n{lab}: QQQ B&H Sharpe = {bm['sharpe']:.2f} "
              f"(CAGR {100*bm['cagr']:.2f}%, maxDD {100*bm['mdd']:.2f}%)")
        print(f"  configs beating it on Sharpe: {len(beat)} of {len(grid)}")
        for g in sorted(beat, key=lambda x: -x[key]["sharpe"])[:12]:
            print(f"    {g['name']:22s} Sharpe {g[key]['sharpe']:.2f}  "
                  f"CAGR {100*g[key]['cagr']:7.2f}%  maxDD {100*g[key]['mdd']:7.2f}%")
    for lab, key, bm in (("SEARCH", "s", tqqq_s), ("HOLDOUT", "h", tqqq_h)):
        beat = [g for g in grid if g[key]["sharpe"] > bm["sharpe"]]
        print(f"\n{lab}: TQQQ B&H Sharpe = {bm['sharpe']:.2f} -- "
              f"beaten on Sharpe by {len(beat)} of {len(grid)}")

    # ---- what would SEARCH have picked? --------------------------------------
    print("\n" + "=" * 110)
    print("PRE-REGISTRATION TEST: rank by SEARCH, then read the HOLDOUT")
    print("=" * 110)
    for crit in ("sharpe", "cagr", "calmar"):
        top = sorted(grid, key=lambda g: -g["s"][crit])[:5]
        print(f"\ntop 5 by SEARCH {crit}:")
        for g in top:
            print(f"  {g['name']:22s} search {crit} {g['s'][crit]:6.2f} "
                  f"(CAGR {100*g['s']['cagr']:6.2f}%) -> holdout Sharpe {g['h']['sharpe']:5.2f} "
                  f"CAGR {100*g['h']['cagr']:7.2f}% maxDD {100*g['h']['mdd']:7.2f}%")

    # ---- 50dma vs 200dma head to head ---------------------------------------
    print("\n" + "=" * 118)
    print("THE 50dma QUESTION -- 50 vs 100 vs 200 vs both vs asymmetric, held at each L (buffer 0%)")
    print("=" * 118)
    print(f"{'L':>4s} {'rule':14s} | {'SEARCH CAGR':>11s} {'Shrp':>5s} {'t/yr':>5s} | "
          f"{'HOLDOUT CAGR':>12s} {'Shrp':>5s} {'maxDD':>8s} {'t/yr':>5s} {'cost drag':>9s}")
    for L in LEV_GRID:
        for rule in BREAKERS:
            g = next(x for x in grid if x["L"] == L and x["rule"] == rule and x["buf"] == 0.0)
            stt = states_cache[(rule, 0.0)]
            hr, hs = sub(rows, stt, HOLDOUT_START, None)
            drag = run(hr, hs, L, 0.0)["cagr"] - run(hr, hs, L, 20.0)["cagr"]
            print(f"{L:4.1f} {rule:14s} | {100*g['s']['cagr']:10.2f}% {g['s']['sharpe']:5.2f} "
                  f"{g['s']['trades_per_yr']:5.1f} | {100*g['h']['cagr']:11.2f}% "
                  f"{g['h']['sharpe']:5.2f} {100*g['h']['mdd']:7.2f}% "
                  f"{g['h']['trades_per_yr']:5.1f} {100*drag:8.2f}%")
        print("-" * 118)

    # ---- buffer effect -------------------------------------------------------
    print("\n" + "=" * 104)
    print("BUFFER / NO-TRADE BAND (holdout, L=3.0, 10bp) -- turnover control")
    print("=" * 104)
    print(f"{'rule':14s} {'buf':>5s} {'tr/yr':>6s} {'turnover':>9s} {'CAGR@0bp':>9s} "
          f"{'@10bp':>8s} {'@20bp':>8s} {'drag':>7s} {'Sharpe':>7s}")
    for rule in BREAKERS:
        for b in BUFFER_GRID:
            stt = states_cache[(rule, b)]
            hr, hs = sub(rows, stt, HOLDOUT_START, None)
            m0, m10, m20 = (run(hr, hs, 3.0, c) for c in (0.0, 10.0, 20.0))
            print(f"{rule:14s} {int(b*100):4d}% {m10['trades_per_yr']:6.1f} "
                  f"{m10['turnover']:9.1f} {100*m0['cagr']:8.2f}% {100*m10['cagr']:7.2f}% "
                  f"{100*m20['cagr']:7.2f}% {100*(m0['cagr']-m20['cagr']):6.2f}% "
                  f"{m10['sharpe']:7.2f}")

    # ---- cost sensitivity ----------------------------------------------------
    print("\n" + "=" * 96)
    print("COST SENSITIVITY (holdout CAGR, round-trip bp)")
    print("=" * 96)
    print(f"{'config':24s} " + " ".join(f"{c:>8.0f}bp" for c in COST_GRID) + f" {'drag':>8s}")
    for L in (2.0, 3.0):
        for rule in BREAKERS:
            stt = states_cache[(rule, 0.0)]
            hr, hs = sub(rows, stt, HOLDOUT_START, None)
            cs = [run(hr, hs, L, c)["cagr"] for c in COST_GRID]
            print(f"{f'L{L:.1f}_{rule}_b0':24s} " + " ".join(f"{100*c:9.2f}%" for c in cs)
                  + f" {100*(cs[0]-cs[-1]):7.2f}%")

    # ---- execution timing ----------------------------------------------------
    print("\n" + "=" * 96)
    print("EXECUTION TIMING: next-open (primary) minus same-close MOC, CAGR gap")
    print("=" * 96)
    print(f"{'config':24s} {'SEARCH':>9s} {'HOLDOUT':>9s} {'FULL':>9s}")
    for rule in BREAKERS:
        stt = states_cache[(rule, 0.0)]
        line = []
        for lo, hi in ((None, SEARCH_END), (HOLDOUT_START, None), (None, None)):
            rr, ss2 = sub(rows, stt, lo, hi)
            line.append(run(rr, ss2, 3.0, BASE_COST_BPS, "next_open")["cagr"]
                        - run(rr, ss2, 3.0, BASE_COST_BPS, "same_close")["cagr"])
        print(f"{f'L3.0_{rule}_b0':24s} " + " ".join(f"{100*x:8.2f}%" for x in line))

    # ---- per-year for a shortlist -------------------------------------------
    # Fixed shortlist at L=3.0 -- the leverage at which the 50dma claim was framed --
    # so the 50 vs 100 vs 200 vs asymmetric comparison is visible year by year at
    # constant leverage. Chosen BEFORE looking at the ranking, not after.
    short_names = ["L3.0_ma50_b1", "L3.0_ma200_b1", "L3.0_slow_out_b1", "L2.0_ma200_b1"]
    short = [next(x for x in grid if x["name"] == n) for n in short_names]
    print("\n" + "=" * 132)
    print("PER-CALENDAR-YEAR RETURNS -- fixed shortlist at constant leverage, so the 50dma-vs-200dma")
    print("difference is visible year by year and it is plain whether any edge is broad or concentrated.")
    print("=" * 132)
    years = sorted({r["date"][:4] for r in rows})
    print(f"{'year':6s} " + " ".join(f"{n:>20s}" for n in short_names)
          + f" {'TQQQ B&H':>10s} {'QQQ B&H':>10s}")
    for y in years:
        seg = sl(rows, f"{y}-01-01", f"{y}-12-31")
        if len(seg) < 20:
            continue
        cells = []
        for g in short:
            stt = states_cache[(g["rule"], g["buf"])]
            rr, ss2 = sub(rows, stt, f"{y}-01-01", f"{y}-12-31")
            cells.append(run(rr, ss2, g["L"])["final"] - 1.0)
        i0 = rows.index(seg[0]); i1 = rows.index(seg[-1])
        yr = rows[max(0, i0 - 1):i1 + 1]
        bt = buy_hold(yr, "TQQQ")["final"] - 1.0
        bq = buy_hold(yr, "QQQ")["final"] - 1.0
        print(f"{y:6s} " + " ".join(f"{100*c:19.2f}%" for c in cells)
              + f" {100*bt:9.2f}% {100*bq:9.2f}%")

    # ---- drawdown depth AND duration ----------------------------------------
    print("\n" + "=" * 112)
    print("DRAWDOWN DEPTH *AND* DURATION -- holdout (a strategy sold on drawdown must be judged on it)")
    print("=" * 112)
    print(f"{'config':24s} {'maxDD':>9s} {'worst 12m':>11s} {'longest DD (months)':>21s} "
          f"{'CAGR':>8s} {'Sharpe':>7s}")
    show = short_names + [g["name"] for g in sorted(grid, key=lambda x: -x["h"]["sharpe"])[:2]] \
        + [f"L{L:.1f}_bh_b0" for L in LEV_GRID]
    seen = set()
    for nm in show:
        if nm in seen:
            continue
        seen.add(nm)
        g = next(x for x in grid if x["name"] == nm)
        m = g["h"]
        print(f"{nm:24s} {100*m['mdd']:8.2f}% {100*m['worst12m']:10.2f}% "
              f"{m['dd_months']:20.1f} {100*m['cagr']:7.2f}% {m['sharpe']:7.2f}")
    for a in ("QQQ", "TQQQ"):
        m = buy_hold(hrow, a)
        print(f"{a + ' B&H':24s} {100*m['mdd']:8.2f}% {100*m['worst12m']:10.2f}% "
              f"{m['dd_months']:20.1f} {100*m['cagr']:7.2f}% {m['sharpe']:7.2f}")

    # ---- 2025 spot check ----------------------------------------------------
    print("\n" + "=" * 96)
    print("2025 SPOT CHECK (the year the 50dma is said to have won), L=3.0, buffer 0%")
    print("=" * 96)
    for rule in BREAKERS:
        stt = states_cache[(rule, 0.0)]
        rr, ss2 = sub(rows, stt, "2025-01-01", "2025-12-31")
        m = run(rr, ss2, 3.0)
        print(f"  L3.0_{rule:14s} 2025 return {100*(m['final']-1):8.2f}%  "
              f"trades {m['trades']:3d}")

    # ---- Sharpe is flat in L ------------------------------------------------
    print("\n" + "=" * 96)
    print("IS SHARPE A FUNCTION OF LEVERAGE?  holdout Sharpe by rule x L (buffer 1%)")
    print("=" * 96)
    print(f"{'rule':14s} " + " ".join(f"{'L' + f'{L:.1f}':>7s}" for L in LEV_GRID) + f" {'spread':>8s}")
    for rule in BREAKERS:
        vals = [next(x for x in grid if x["L"] == L and x["rule"] == rule
                     and x["buf"] == 0.01)["h"]["sharpe"] for L in LEV_GRID]
        print(f"{rule:14s} " + " ".join(f"{v:7.2f}" for v in vals)
              + f" {max(vals)-min(vals):8.2f}")
    print("Leverage moves CAGR and drawdown almost proportionally and leaves Sharpe "
          "nearly unchanged.\nThe BREAKER sets the risk-adjusted return; L only sets how "
          "much of it you take on.")

    # ---- state-machine health -----------------------------------------------
    print("\n" + "=" * 108)
    print("STATE-MACHINE HEALTH -- how long does an 'invested' run actually last?")
    print("=" * 108)
    print(f"{'rule':14s} {'buf':>4s} {'flips':>6s} {'inv runs':>9s} {'median run':>11s} "
          f"{'1-day runs':>11s} {'days inv':>9s} {'inv while <200dma':>18s}")
    for rule in BREAKERS:
        for b in BUFFER_GRID:
            stt = states_cache[(rule, b)]
            flips = sum(1 for i in range(1, len(stt)) if stt[i] != stt[i - 1])
            runs, cur = [], 0
            for x in stt:
                if x:
                    cur += 1
                elif cur:
                    runs.append(cur); cur = 0
            if cur:
                runs.append(cur)
            runs.sort()
            below = sum(1 for i, r in enumerate(rows) if stt[i] and r["qqq_c"] < r["ma200"])
            med = runs[len(runs) // 2] if runs else 0
            print(f"{rule:14s} {int(b*100):3d}% {flips:6d} {len(runs):9d} {med:11d} "
                  f"{sum(1 for r in runs if r == 1):11d} {sum(stt):9d} {below:18d}")
    print("A median invested run of 1 DAY means the rule is not holding a position -- it is\n"
          "flickering. The two asymmetric rules do this by construction: after exiting below\n"
          "the 200dma, `slow_out` re-enters on a 50dma cross while still below the 200dma, at\n"
          "which point its own exit test is ALREADY TRUE, so it exits again the next bar.")

    # ---- what those flicker days are worth ----------------------------------
    print("\n" + "=" * 100)
    print("FLICKER DECOMPOSITION -- slow_out's exposure split by whether QQQ was above its 200dma")
    print("=" * 100)
    for b in BUFFER_GRID:
        stt = states_cache[("slow_out", b)]
        pa, pb, na, nb = 1.0, 1.0, 0, 0
        for i in range(1, len(rows)):
            if not stt[i - 1]:
                continue
            r = rows[i]["tqqq_c"] / rows[i - 1]["tqqq_c"] - 1.0
            if rows[i - 1]["qqq_c"] < rows[i - 1]["ma200"]:
                pb *= (1 + r); nb += 1
            else:
                pa *= (1 + r); na += 1
        print(f"  buffer {int(b*100)}%: above-200dma days n={na:5d} cum TQQQ {pa:9.2f}x   |   "
              f"below-200dma (flicker) days n={nb:4d} cum TQQQ {pb:6.3f}x")
    print("\nCounterfactual -- the SAME rule with sub-200dma entries forbidden (`_gated`):")
    print(f"{'config':26s} {'search CAGR':>12s} {'Shrp':>5s} {'holdout CAGR':>13s} {'Shrp':>5s} "
          f"{'maxDD':>8s} {'t/yr':>5s}")
    for b in (0.0, 0.01):
        g = slow_out_gated(rows, b)
        for L in (2.0, 3.0):
            sr, ss = sub(rows, g, None, SEARCH_END)
            hr, hs = sub(rows, g, HOLDOUT_START, None)
            ms, mh = run(sr, ss, L), run(hr, hs, L)
            print(f"{f'L{L:.1f}_slow_out_gated_b{int(b*100)}':26s} {100*ms['cagr']:11.2f}% "
                  f"{ms['sharpe']:5.2f} {100*mh['cagr']:12.2f}% {mh['sharpe']:5.2f} "
                  f"{100*mh['mdd']:7.2f}% {mh['trades_per_yr']:5.1f}")
    print("Removing a few dozen isolated single-day exposures costs ~9pp of holdout CAGR and\n"
          "~0.10 of Sharpe. An edge that rests on ~75 scattered one-day bets is a draw, not a\n"
          "mechanism -- and it is precisely the exposure most sensitive to fill assumptions.")

    # ---- minimum-hold robustness --------------------------------------------
    print("\n" + "=" * 104)
    print("MINIMUM-HOLD ROBUSTNESS -- force every invested run to last >= n bars (L=3.0, buffer 1%)")
    print("=" * 104)
    print(f"{'rule':10s} {'minhold':>8s} {'search CAGR':>12s} {'Shrp':>5s} "
          f"{'holdout CAGR':>13s} {'Shrp':>5s} {'t/yr':>6s}")
    for rule in ("slow_out", "fast_out", "ma200"):
        base = states_cache[(rule, 0.01)]
        for n in (1, 3, 5, 10):
            stt = min_hold(base, n) if n > 1 else base
            sr, ss = sub(rows, stt, None, SEARCH_END)
            hr, hs = sub(rows, stt, HOLDOUT_START, None)
            ms, mh = run(sr, ss, 3.0), run(hr, hs, 3.0)
            print(f"{rule:10s} {n:7d}d {100*ms['cagr']:11.2f}% {ms['sharpe']:5.2f} "
                  f"{100*mh['cagr']:12.2f}% {mh['sharpe']:5.2f} {mh['trades_per_yr']:6.1f}")
    print("`slow_out` loses its entire advantage the moment it is forbidden to hold for one\n"
          "day only (holdout Sharpe 1.10 -> 0.96 at a 3-day floor) while its SEARCH Sharpe\n"
          "RISES (0.82 -> 0.88). The flicker helped only on the holdout: that is the signature\n"
          "of luck, not of a mechanism. `ma200`, which never flickers, is unmoved.")

    # ---- 2025 under both fill assumptions ------------------------------------
    print("\n" + "=" * 104)
    print("2025 EXECUTION SENSITIVITY -- calendar 2025 return at L=3.0, next-open vs same-close")
    print("=" * 104)
    print(f"{'rule':10s} {'buf':>4s} {'0bp open':>10s} {'0bp close':>10s} "
          f"{'10bp open':>10s} {'10bp close':>11s} {'open-close gap':>15s}")
    for rule in BREAKERS:
        for b in (0.0, 0.01):
            stt = states_cache[(rule, b)]
            rr, ss = sub(rows, stt, "2025-01-01", "2025-12-31")
            v = [run(rr, ss, 3.0, c, e)["final"] - 1.0
                 for c in (0.0, 10.0) for e in ("next_open", "same_close")]
            print(f"{rule:10s} {int(b*100):3d}% {100*v[0]:9.2f}% {100*v[1]:9.2f}% "
                  f"{100*v[2]:9.2f}% {100*v[3]:10.2f}% {100*(v[2]-v[3]):14.2f}%")
    r25 = sl(rows, "2025-01-01", "2025-12-31")
    yr = rows[rows.index(r25[0]) - 1:rows.index(r25[-1]) + 1]
    print(f"{'TQQQ B&H':10s} {'':4s} {100*(buy_hold(yr,'TQQQ')['final']-1):9.2f}%"
          f"   (QQQ B&H {100*(buy_hold(yr,'QQQ')['final']-1):.2f}%)")
    print("\nThe 50dma rule's own 2025 answer moves from +27.65% to +45.70% on the fill\n"
          "assumption alone. A rule whose single-year result swings 18 points on whether you\n"
          "fill at today's close or tomorrow's open does not have a 16-year edge to defend.")

    # ---- export best-justified config ---------------------------------------
    export_name, export_reason = choose_export(grid)
    g = next(x for x in grid if x["name"] == export_name)
    stt = states_cache[(g["rule"], g["buf"])]
    _, recs = run(rows, stt, g["L"], BASE_COST_BPS, "next_open", collect=True)
    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, "daily_series.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(recs[0].keys()))
        w.writeheader(); w.writerows(recs)
    print(f"\nwrote {path}  ({len(recs)} rows) for config {export_name}")
    print(f"reason: {export_reason}")


def choose_export(grid):
    """The single BEST-JUSTIFIED config -- deliberately NOT the best-performing one.

    Ranking 95 configurations and exporting the top row is the exact error this
    repo's methodology exists to prevent.  The export is chosen on grounds that
    were knowable without the holdout:

      * MECHANISM.  The rule must actually hold a position.  The two asymmetric
        rules post a median invested run of ONE DAY and derive a large part of
        their result from a few dozen isolated single-day bets (see the flicker
        decomposition); they are excluded on that basis, not on performance.
      * TURNOVER.  A 1% buffer roughly halves trading with no loss of signal.
      * LEVERAGE.  Holdout Sharpe is nearly flat in L, so raising L buys return
        and drawdown in proportion and nothing else.  L=2.0 keeps drawdown in
        the neighbourhood of QQQ B&H rather than TQQQ B&H.

    That yields L2.0_ma200_b1.  It is exported because it is the most defensible
    thing in the grid to look at closely -- NOT because it is recommended.  It
    did not clear the search-period bar, and the write-up says so.
    """
    name = "L2.0_ma200_b1"
    return name, ("ma200 + 1% buffer at L=2.0 -- the only family with a stable state "
                  "machine (median invested run 56 days, 2 one-day runs), 1.7 trades/yr, "
                  "chosen on mechanism and turnover, NOT on holdout rank")


if __name__ == "__main__":
    main()
