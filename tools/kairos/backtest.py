#!/usr/bin/env python3
"""Kairos five-factor regime system -- BACKTEST ENGINE.

Self-contained and re-runnable:  python3 tools/kairos/backtest.py
Reads  data/kairos/factors.csv   (built by tools/kairos/factors.py)
Writes data/kairos/daily_series*.csv and prints every results table.

=============================================================================
WHAT IS BEING TESTED
=============================================================================
A daily decision: how much leveraged Nasdaq exposure to carry. The five factors
(Credit, VIX, Breadth, Trend, Utilities) produce a 0-5 healthy count, reported
equivalently as a symmetric net score of -5..+5 (net = 2*count - 5, each factor
+1 healthy / -1 unhealthy) -- the same shape as Raincheck's disclosed -9..+9
Market Signal. A policy turns that score into a target effective leverage L in
[0,3]; a route turns L into actual fund positions; a position-based engine holds
those positions between rebalances.

=============================================================================
THE BENCHMARK THAT MATTERS
=============================================================================
The primary comparison is BUY-AND-HOLD TQQQ over the identical window.
Beating SPY or QQQ with a 3x leveraged instrument is not evidence of skill --
it is what leverage does in a rising market. While a regime filter is long, it
IS buy-and-hold TQQQ and contributes nothing; 100% of any edge must come from
what it avoids while flat. SPY/QQQ buy-and-hold are reported because the
marketing sites compare to them, but they are the secondary line.

=============================================================================
NO LOOKAHEAD
=============================================================================
Factors come from day t's CLOSE. Two execution assumptions are reported:
  NEXT-OPEN (primary, fully implementable): signal from day t's close is filled
    at day t+1's OPEN. Cash accrues overnight, the rebalance happens at the open,
    and the position is valued at that day's close.
  SAME-CLOSE / MOC (secondary): filled at day t's close as a ~3:50pm MOC order.
    This needs 3:50pm factor values to stand in for official closes; VIX is a
    real-time index so it is a mild approximation, and the credit series is
    lagged a full trading day in factors.py so it is never an issue there.

=============================================================================
POSITION-BASED ACCOUNTING (why it is not weight-based)
=============================================================================
The engine holds SHARES and lets weights drift between rebalances. This is not a
detail: with DAILY rebalancing a target leverage L is route-independent (1/3 TQQQ
+ 2/3 cash rebalanced daily reproduces 1x QQQ to within 0.02%/yr over this
window -- leveraged-ETF decay is a consequence of NOT rebalancing). The routes
only differ when positions are held between signal flips, which is what this
strategy does. Rebalancing therefore happens ONLY when the target moves by more
than the no-trade band, never on a daily schedule.

=============================================================================
SEARCH / HOLDOUT
=============================================================================
SEARCH  = inception (2010-02-11) .. 2019-12-31
HOLDOUT = 2020-01-01 .. end (2026-08-27), opened once, unmodified.
The holdout is deliberately aligned with Kairos's claimed 2020-2026 window.
NOTE: the search period is a near-uninterrupted Nasdaq bull market where a risk
filter has almost nothing to prove and will tend to look useless or harmful; the
holdout contains the 2020, 2022 and 2025 drawdowns. A good holdout result is
therefore partly luck about which period got which stress, and a weak search
result is not damning. Both are reported and neither is hidden.
"""
import csv
import os
import math

ROOT = "/home/user/Robinhood"
DATA = os.path.join(ROOT, "data", "kairos")
FACTORS = os.path.join(DATA, "factors.csv")

SEARCH_END = "2019-12-31"
HOLDOUT_START = "2020-01-01"

BASE_COST_BPS = 2.0
COST_GRID = [0.0, 2.0, 5.0, 10.0, 20.0]
# No-trade bands are expressed in LEVERAGE units on a 0-3 scale, so 0.3 == 10%
# of full range and 0.6 == 20%.
BAND_GRID = [0.0, 0.3, 0.6]
TRADING_DAYS = 252

MAXL = 3.0
CAP_L = 2.10        # 70% of 3x -- the cap a real product in this space uses
ASSET_MULT = {"QQQ": 1.0, "QLD": 2.0, "TQQQ": 3.0}


# ------------------------------------------------------------------------ routes
def route_ladder(L):
    """Reach L with the LOWEST-multiple combination available; hold cash only for
    the portion below 1x."""
    if L <= 0:
        return {}
    if L <= 1.0:
        return {"QQQ": L}                        # remainder cash
    if L <= 2.0:
        return {"QQQ": 2.0 - L, "QLD": L - 1.0}  # fully invested
    return {"QLD": 3.0 - L, "TQQQ": L - 2.0}     # fully invested


def route_pure_tqqq(L):
    """Naive route: scale a single 3x fund against cash."""
    return {"TQQQ": L / 3.0} if L > 0 else {}


ROUTES = {"ladder": route_ladder, "pure_tqqq": route_pure_tqqq}


# ---------------------------------------------------------------------- policies
# A policy maps the factor row sequence to a target-leverage series. Each element
# L[i] is the target DECIDED AT ROW i's CLOSE, acted on at i+1 per the execution
# assumption. Policies are pure functions of the score history -- never of returns.
def make_static_maps():
    m = {}
    for T in range(0, 6):
        m[f"binary_T{T}"] = tuple(MAXL if s >= T else 0.0 for s in range(6))
    m["linear"] = tuple(MAXL * s / 5.0 for s in range(6))
    m["convex_sq"] = tuple(MAXL * (s / 5.0) ** 2 for s in range(6))
    m["convex_step"] = tuple(MAXL * x for x in (0.0, 0.0, 0.0, 1 / 3, 2 / 3, 1.0))
    m["cap70_linear"] = tuple(CAP_L * s / 5.0 for s in range(6))
    m["cap70_binary_T4"] = tuple(CAP_L if s >= 4 else 0.0 for s in range(6))
    m["cap70_convex_step"] = tuple(CAP_L * x for x in (0.0, 0.0, 0.0, 1 / 3, 2 / 3, 1.0))
    return m


def make_static_maps2():
    """Raincheck-style ablation: Trend + Breadth ONLY, score2 in 0..2."""
    return {
        "TB_binary_T1": (0.0, MAXL, MAXL),
        "TB_binary_T2": (0.0, 0.0, MAXL),
        "TB_linear": (0.0, MAXL / 2, MAXL),
        "TB_cap70_T2": (0.0, 0.0, CAP_L),
    }


def pol_static(mapping, score_key="score"):
    def f(rows):
        return [mapping[int(r[score_key])] for r in rows]
    return f


def pol_hysteresis(enter_at, exit_at, maxl=MAXL, score_key="score"):
    """Enter when score >= enter_at, stay in until score <= exit_at (enter>exit).
    The dead zone suppresses flip-flopping WITHOUT delaying a genuine entry, which
    is the point: a fixed confirmation delay would pay an entry cost on every real
    signal to fix a problem that only affects the noisy ones."""
    def f(rows):
        out, inpos = [], False
        for r in rows:
            s = int(r[score_key])
            if not inpos and s >= enter_at:
                inpos = True
            elif inpos and s <= exit_at:
                inpos = False
            out.append(maxl if inpos else 0.0)
        return out
    return f


def pol_ema(span, maxl=MAXL, score_key="score"):
    """EMA-smooth the score, then map linearly to leverage. Filters noise
    continuously rather than with a fixed lag, and yields a naturally graded
    weight instead of steps."""
    a = 2.0 / (span + 1.0)
    def f(rows):
        out, e = [], None
        for r in rows:
            s = float(r[score_key])
            e = s if e is None else a * s + (1 - a) * e
            out.append(maxl * max(0.0, min(1.0, e / 5.0)))
        return out
    return f


def pol_min_hold(base, n_days):
    """Once the target goes positive, hold it at least n_days regardless of score.
    The crudest way to cut flip count; included as a baseline."""
    def f(rows):
        raw = base(rows)
        out, held, cur = [], 0, 0.0
        for i, L in enumerate(raw):
            if cur > 0 and held < n_days:
                out.append(cur)
                held += 1
                continue
            if L != cur:
                cur, held = L, 1
            else:
                held += 1
            out.append(cur)
        return out
    return f


def pol_age_ramp(score_key="score", thresh=3, maxl=MAXL):
    """Ramp leverage UP with the age of the healthy streak.
    REPORTED BUT NOT RECOMMENDED: the measured forward-return profile is U-shaped,
    with the BEST forward returns in the first ~20 days of a fresh healthy regime
    and a dead zone at 61-120 days. An age-ramp is underweight exactly when
    returns are strongest and fully weighted through the dead zone, so it is
    fighting the data. Included because it was asked for; see the streak table."""
    def f(rows):
        out, age = [], 0
        for r in rows:
            age = age + 1 if int(r[score_key]) >= thresh else 0
            if age == 0:
                out.append(0.0)
            elif age <= 5:
                out.append(maxl / 3)
            elif age <= 20:
                out.append(2 * maxl / 3)
            else:
                out.append(maxl)
        return out
    return f


# ------------------------------------------------------------------------ engine
def daily_rf(annual_pct):
    """DGS3MO is an annualised percentage; compound to a daily rate."""
    return (1.0 + annual_pct / 100.0) ** (1.0 / TRADING_DAYS) - 1.0


def px(row, asset, field):
    return float(row[f"{asset.lower()}_{field}"])


def run(rows, policy, route="ladder", cost_bps=BASE_COST_BPS, band=0.0,
        execution="next_open", collect=False):
    """Position-based simulation. Holds SHARES; weights drift between rebalances."""
    targets = policy(rows)
    rfun = ROUTES[route]
    shares = {}
    cash = 1.0
    last_L = 0.0
    equity_prev = 1.0
    curve, rets, rfs, levs = [], [], [], []
    n_trades = 0
    turnover = 0.0
    recs = []

    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]
        L_t = targets[i - 1]                     # decided at prev close
        rf_d = daily_rf(float(prev["dgs3mo"]))
        traded = 0

        def portfolio_value(row, field):
            return cash + sum(n * px(row, a, field) for a, n in shares.items())

        if execution == "next_open":
            cash *= (1.0 + rf_d)                 # overnight accrual
            if abs(L_t - last_L) > band:
                eq = portfolio_value(cur, "open")
                tw = rfun(L_t)
                traded_notional = sum(
                    abs(tw.get(a, 0.0) * eq - shares.get(a, 0.0) * px(cur, a, "open"))
                    for a in set(list(tw) + list(shares)))
                eq -= cost_bps * 1e-4 * traded_notional
                turnover += traded_notional / eq if eq > 0 else 0.0
                shares = {a: w * eq / px(cur, a, "open") for a, w in tw.items() if w > 0}
                cash = eq - sum(n * px(cur, a, "open") for a, n in shares.items())
                last_L, n_trades, traded = L_t, n_trades + 1, 1
        else:                                     # same_close / MOC at prev close
            if abs(L_t - last_L) > band:
                eq = portfolio_value(prev, "close")
                tw = rfun(L_t)
                traded_notional = sum(
                    abs(tw.get(a, 0.0) * eq - shares.get(a, 0.0) * px(prev, a, "close"))
                    for a in set(list(tw) + list(shares)))
                eq -= cost_bps * 1e-4 * traded_notional
                turnover += traded_notional / eq if eq > 0 else 0.0
                shares = {a: w * eq / px(prev, a, "close") for a, w in tw.items() if w > 0}
                cash = eq - sum(n * px(prev, a, "close") for a, n in shares.items())
                last_L, n_trades, traded = L_t, n_trades + 1, 1
            cash *= (1.0 + rf_d)

        equity = portfolio_value(cur, "close")
        risk_val = sum(n * px(cur, a, "close") for a, n in shares.items())
        eff_lev = (sum(n * px(cur, a, "close") * ASSET_MULT[a]
                       for a, n in shares.items()) / equity) if equity > 0 else 0.0
        r = equity / equity_prev - 1.0
        equity_prev = equity
        curve.append(equity)
        rets.append(r)
        rfs.append(rf_d)
        levs.append(eff_lev)

        if collect:
            recs.append({
                "date": cur["date"], "hy_oas": cur["hy_oas"],
                "credit_baa10y": cur["credit_baa10y"], "credit_med252": cur["credit_med252"],
                "vix": cur["vix"], "breadth_pct": cur["breadth_pct"],
                "qqq_close": cur["qqq_close"], "qqq_200dma": cur["qqq_200dma"],
                "xlu_spy_ratio": cur["xlu_spy_ratio"], "xlu_spy_rel60": cur["xlu_spy_rel60"],
                "credit_ok": cur["credit_ok"], "vix_ok": cur["vix_ok"],
                "breadth_ok": cur["breadth_ok"], "trend_ok": cur["trend_ok"],
                "utilities_ok": cur["utilities_ok"],
                "score": cur["score"], "net_score": 2 * int(cur["score"]) - 5,
                "signal_score_used": prev["score"],
                "target_leverage": f"{L_t:.4f}",
                "actual_leverage": f"{eff_lev:.4f}",
                "w_qqq": f"{shares.get('QQQ',0.0)*px(cur,'QQQ','close')/equity:.4f}",
                "w_qld": f"{shares.get('QLD',0.0)*px(cur,'QLD','close')/equity:.4f}",
                "w_tqqq": f"{shares.get('TQQQ',0.0)*px(cur,'TQQQ','close')/equity:.4f}",
                "w_cash": f"{cash/equity:.4f}",
                "risk_frac": f"{risk_val/equity:.4f}",
                "traded_flag": traded,
                "tqqq_ret": f"{px(cur,'TQQQ','close')/px(prev,'TQQQ','close')-1.0:.6f}",
                "tbill_ret": f"{rf_d:.8f}",
                "portfolio_ret": f"{r:.6f}",
                "equity_curve": f"{equity:.6f}",
            })

    m = metrics(curve, rets, rfs, len(rows) - 1)
    yrs = (len(rows) - 1) / TRADING_DAYS
    m.update({"trades": n_trades, "turnover": turnover,
              "trades_per_yr": n_trades / yrs if yrs else 0.0,
              "mean_lev": sum(levs) / len(levs) if levs else 0.0})
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


def metrics(curve, rets, rf_list, ndays):
    if not rets:
        return {}
    yrs = ndays / TRADING_DAYS
    cagr = curve[-1] ** (1.0 / yrs) - 1.0 if yrs > 0 and curve[-1] > 0 else float("nan")
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / max(1, len(rets) - 1))
    ex = [rets[i] - rf_list[i] for i in range(len(rets))]
    mex = sum(ex) / len(ex)
    sdex = math.sqrt(sum((r - mex) ** 2 for r in ex) / max(1, len(ex) - 1))
    return {"cagr": cagr, "vol": sd * math.sqrt(TRADING_DAYS),
            "sharpe": (mex / sdex) * math.sqrt(TRADING_DAYS) if sdex > 0 else float("nan"),
            "mdd": min(drawdown_series(curve)), "final": curve[-1], "years": yrs}


def buy_hold(rows, asset):
    equity, curve, rets, rfs = 1.0, [], [], []
    for i in range(1, len(rows)):
        r = px(rows[i], asset, "close") / px(rows[i - 1], asset, "close") - 1.0
        equity *= (1.0 + r)
        curve.append(equity); rets.append(r)
        rfs.append(daily_rf(float(rows[i - 1]["dgs3mo"])))
    m = metrics(curve, rets, rfs, len(rows) - 1)
    m.update({"trades": 1, "turnover": 1.0, "trades_per_yr": 0.0,
              "mean_lev": ASSET_MULT.get(asset, 1.0)})
    return m


def tbill_only(rows):
    equity, curve, rets, rfs = 1.0, [], [], []
    for i in range(1, len(rows)):
        rf_d = daily_rf(float(rows[i - 1]["dgs3mo"]))
        equity *= (1.0 + rf_d)
        curve.append(equity); rets.append(rf_d); rfs.append(rf_d)
    m = metrics(curve, rets, rfs, len(rows) - 1)
    m.update({"trades": 0, "turnover": 0.0, "trades_per_yr": 0.0, "mean_lev": 0.0})
    return m


# ------------------------------------------------------------------- presentation
HDR = (f"{'strategy':26s} {'CAGR':>8s} {'vol':>8s} {'Sharpe':>6s} {'maxDD':>9s} "
       f"{'trades':>6s} {'tr/yr':>6s} {'turnovr':>8s} {'meanLev':>8s}")


def fmt(m):
    return (f"{100*m['cagr']:7.2f}% {100*m['vol']:7.2f}% {m['sharpe']:6.2f} "
            f"{100*m['mdd']:8.2f}% {m['trades']:6d} {m['trades_per_yr']:6.1f} "
            f"{m['turnover']:8.1f} {m['mean_lev']:8.2f}")


def slice_rows(rows, lo=None, hi=None):
    return [r for r in rows
            if (lo is None or r["date"] >= lo) and (hi is None or r["date"] <= hi)]


def all_policies():
    """Every policy under test, as name -> (policy_fn, note)."""
    sm, sm2 = make_static_maps(), make_static_maps2()
    p = {}
    for k, v in sm.items():
        p[k] = pol_static(v)
    for k, v in sm2.items():
        p[k] = pol_static(v, "score2_trend_breadth")
    # hysteresis grid (enter H, exit L), H > L
    for H, Lo in [(5, 3), (4, 2), (4, 1), (3, 1), (3, 0), (2, 0), (5, 2), (4, 3)]:
        p[f"hyst_H{H}_L{Lo}"] = pol_hysteresis(H, Lo)
    p["hyst_H4_L2_cap70"] = pol_hysteresis(4, 2, maxl=CAP_L)
    for span in (3, 5, 10):
        p[f"ema{span}"] = pol_ema(span)
    p["ema5_cap70"] = pol_ema(5, maxl=CAP_L)
    for n in (5, 10, 21):
        p[f"minhold{n}_T3"] = pol_min_hold(pol_static(sm["binary_T3"]), n)
    p["age_ramp_T3"] = pol_age_ramp()
    return p


def year_table(rows, policy, route, cost_bps, band, execution):
    years = sorted({r["date"][:4] for r in rows})
    out = []
    for y in years:
        seg = slice_rows(rows, f"{y}-01-01", f"{y}-12-31")
        if len(seg) < 20:
            continue
        i0, i1 = rows.index(seg[0]), rows.index(seg[-1])
        sf = rows[max(0, i0 - 1):i1 + 1]
        s = run(sf, policy, route, cost_bps, band, execution)
        out.append({"year": y, "strat": s["final"] - 1.0,
                    "tqqq": buy_hold(sf, "TQQQ")["final"] - 1.0,
                    "qqq": buy_hold(sf, "QQQ")["final"] - 1.0,
                    "spy": buy_hold(sf, "SPY")["final"] - 1.0,
                    "lev": s["mean_lev"]})
    return out


def streak_table(rows, thresh=3):
    """Forward TQQQ returns bucketed by the age of the healthy-regime streak.

    CLUSTERING CAVEAT: these are OVERLAPPING daily observations, not independent
    draws. Each bucket contains many days drawn from far fewer distinct runs, so
    naive t-statistics are inflated by roughly sqrt(n_days / n_runs). The run
    counts are printed alongside so any t-stat can be deflated; none is quoted
    here as if it were independent evidence.
    """
    ages, age = [], 0
    for r in rows:
        age = age + 1 if int(r["score"]) >= thresh else 0
        ages.append(age)
    buckets = [(1, 5), (6, 20), (21, 60), (61, 120), (121, 10 ** 9)]
    H1, H3 = 21, 63
    out = []
    for lo, hi in buckets:
        idx = [i for i in range(len(rows)) if lo <= ages[i] <= hi]
        runs = sum(1 for i in idx if i == 0 or ages[i - 1] != ages[i] - 1
                   or not (lo <= ages[i - 1] <= hi))
        def fwd(h):
            v = [px(rows[i + h], "TQQQ", "close") / px(rows[i], "TQQQ", "close") - 1.0
                 for i in idx if i + h < len(rows)]
            return sum(v) / len(v) if v else float("nan")
        out.append({"bucket": f"{lo}-{'inf' if hi > 10**8 else hi}",
                    "days": len(idx), "runs": runs, "f1m": fwd(H1), "f3m": fwd(H3)})
    return out


def regime_stats(rows, thresh=3):
    """Flip count and run-length distribution for the raw signal."""
    inpos = [int(r["score"]) >= thresh for r in rows]
    flips = sum(1 for i in range(1, len(inpos)) if inpos[i] != inpos[i - 1])
    runs, cur = [], 0
    for i, v in enumerate(inpos):
        if v:
            cur += 1
        elif cur:
            runs.append(cur); cur = 0
    if cur:
        runs.append(cur)
    runs.sort()
    med = runs[len(runs) // 2] if runs else 0
    short = sum(1 for r in runs if r <= 5)
    return flips, len(runs), med, short


def main():
    with open(FACTORS) as f:
        rows = list(csv.DictReader(f))
    print(f"factor panel: {len(rows)} days  {rows[0]['date']} .. {rows[-1]['date']}\n")

    periods = {
        "SEARCH  (2010-02-11..2019-12-31)": slice_rows(rows, None, SEARCH_END),
        "HOLDOUT (2020-01-01..2026-08-27)": slice_rows(rows, HOLDOUT_START, None),
        "FULL    (2010-02-11..2026-08-27)": rows,
    }
    pols = all_policies()

    # ---------------------------------------------------------------- benchmarks
    print("=" * 122)
    print("BENCHMARKS (buy-and-hold, no timing).  PRIMARY COMPARATOR = TQQQ B&H")
    print("=" * 122)
    for pname, prow in periods.items():
        print(f"\n--- {pname}   n={len(prow)} days ---")
        print(HDR)
        for label, a in (("TQQQ buy-and-hold", "TQQQ"), ("QLD buy-and-hold", "QLD"),
                         ("QQQ buy-and-hold", "QQQ"), ("SPY buy-and-hold", "SPY")):
            print(f"{label:26s} {fmt(buy_hold(prow, a))}")
        print(f"{'T-bill only':26s} {fmt(tbill_only(prow))}")

    # ------------------------------------------------- main sweep by route & band
    for route in ("ladder", "pure_tqqq"):
        for band in BAND_GRID:
            print("\n" + "=" * 122)
            print(f"SWEEP -- route={route}, execution=next_open, cost={BASE_COST_BPS}bp, "
                  f"no-trade band={band:.2f} leverage units ({band/3:.0%} of range)")
            print("=" * 122)
            for pname, prow in periods.items():
                print(f"\n--- {pname} ---")
                print(HDR)
                for name, pol in pols.items():
                    print(f"{name:26s} {fmt(run(prow, pol, route, BASE_COST_BPS, band))}")

    # ------------------------------------------------------- route A/B comparison
    print("\n" + "=" * 122)
    print("ROUTE COMPARISON: ladder (QQQ/QLD/TQQQ) vs pure_tqqq (TQQQ+cash), "
          f"cost={BASE_COST_BPS}bp band=0")
    print("   Positive 'ladder edge' = the QQQ/QLD/TQQQ ladder beat scaling one 3x fund.")
    print("=" * 122)
    for pname, prow in periods.items():
        print(f"\n--- {pname} ---")
        print(f"{'policy':26s} {'CAGR ladder':>12s} {'CAGR pure':>11s} {'edge':>8s} "
              f"{'Shrp ladder':>12s} {'Shrp pure':>10s} {'DD ladder':>10s} {'DD pure':>9s}")
        for name in ("binary_T2", "binary_T3", "binary_T4", "linear", "convex_step",
                     "cap70_linear", "hyst_H4_L2", "ema5", "TB_binary_T1"):
            a = run(prow, pols[name], "ladder", BASE_COST_BPS, 0.0)
            b = run(prow, pols[name], "pure_tqqq", BASE_COST_BPS, 0.0)
            print(f"{name:26s} {100*a['cagr']:11.2f}% {100*b['cagr']:10.2f}% "
                  f"{100*(a['cagr']-b['cagr']):7.2f}% {a['sharpe']:12.2f} "
                  f"{b['sharpe']:10.2f} {100*a['mdd']:9.2f}% {100*b['mdd']:8.2f}%")

    # ------------------------------------------------------- execution comparison
    print("\n" + "=" * 122)
    print(f"EXECUTION TIMING: next_open vs same_close(MOC), ladder, "
          f"cost={BASE_COST_BPS}bp band=0")
    print("=" * 122)
    for pname, prow in periods.items():
        print(f"\n--- {pname} ---")
        print(f"{'policy':26s} {'CAGR nxtopen':>13s} {'CAGR MOC':>10s} {'gap':>8s} "
              f"{'Shrp nxtopen':>13s} {'Shrp MOC':>10s}")
        for name in ("binary_T2", "binary_T3", "binary_T4", "linear",
                     "hyst_H4_L2", "ema5"):
            a = run(prow, pols[name], "ladder", BASE_COST_BPS, 0.0, "next_open")
            b = run(prow, pols[name], "ladder", BASE_COST_BPS, 0.0, "same_close")
            print(f"{name:26s} {100*a['cagr']:12.2f}% {100*b['cagr']:9.2f}% "
                  f"{100*(b['cagr']-a['cagr']):7.2f}% {a['sharpe']:13.2f} {b['sharpe']:10.2f}")

    # ------------------------------------------------------------ cost sensitivity
    print("\n" + "=" * 122)
    print("COST SENSITIVITY (CAGR), ladder, next_open, band=0")
    print("=" * 122)
    for pname, prow in periods.items():
        print(f"\n--- {pname} ---")
        print(f"{'policy':26s} " + " ".join(f"{c:>7.0f}bp" for c in COST_GRID))
        for name, pol in pols.items():
            cells = [f"{100*run(prow, pol, 'ladder', c, 0.0)['cagr']:8.2f}%"
                     for c in COST_GRID]
            print(f"{name:26s} " + " ".join(cells))

    # ---------------------------------------------- turnover: graded vs binary
    print("\n" + "=" * 122)
    print("TURNOVER / COST DRAG: graded vs binary, WITH and WITHOUT no-trade band "
          "(ladder, next_open)")
    print("   drag = CAGR@0bp - CAGR@20bp, i.e. what costs would eat")
    print("=" * 122)
    for pname, prow in periods.items():
        print(f"\n--- {pname} ---")
        print(f"{'policy':22s} {'band':>5s} {'trades':>7s} {'tr/yr':>6s} "
              f"{'turnover':>9s} {'CAGR@0bp':>9s} {'CAGR@20bp':>10s} {'drag':>7s}")
        for name in ("binary_T2", "binary_T3", "binary_T4", "linear", "convex_sq",
                     "cap70_linear", "hyst_H4_L2", "ema5", "minhold21_T3",
                     "TB_binary_T1"):
            for band in BAND_GRID:
                a = run(prow, pols[name], "ladder", 0.0, band)
                b = run(prow, pols[name], "ladder", 20.0, band)
                print(f"{name:22s} {band:5.2f} {a['trades']:7d} {a['trades_per_yr']:6.1f} "
                      f"{a['turnover']:9.1f} {100*a['cagr']:8.2f}% {100*b['cagr']:9.2f}% "
                      f"{100*(a['cagr']-b['cagr']):6.2f}%")

    # ------------------------------------------------- regime churn & streak table
    print("\n" + "=" * 122)
    print("REGIME CHURN AND FORWARD RETURNS BY STREAK AGE (signal: score >= 3)")
    print("=" * 122)
    flips, nruns, med, short = regime_stats(rows, 3)
    yrs = len(rows) / TRADING_DAYS
    print(f"  regime flips: {flips} over {len(rows)} days ({flips/yrs:.1f}/yr); "
          f"completed healthy runs: {nruns}; median run length: {med} days; "
          f"runs <= 5 days: {short} ({100.0*short/max(1,nruns):.0f}%)")
    print("\n  Forward TQQQ return by age of the healthy streak (OVERLAPPING daily obs):")
    print(f"  {'streak age':>12s} {'days':>6s} {'runs':>6s} {'fwd 1m':>9s} {'fwd 3m':>9s} "
          f"{'infl. factor':>13s}")
    for b in streak_table(rows, 3):
        infl = math.sqrt(b["days"] / b["runs"]) if b["runs"] else float("nan")
        print(f"  {b['bucket']:>12s} {b['days']:6d} {b['runs']:6d} "
              f"{100*b['f1m']:8.2f}% {100*b['f3m']:8.2f}% {infl:12.2f}x")
    print("  'infl. factor' = sqrt(days/runs): divide any naive t-stat by this before")
    print("  treating it as evidence; the observations are overlapping, not independent.")

    # --------------------------------------------------------------- year by year
    print("\n" + "=" * 122)
    print(f"YEAR BY YEAR (calendar-year total return), ladder, next_open, "
          f"{BASE_COST_BPS}bp, band=0")
    print("=" * 122)
    for name in ("binary_T2", "binary_T3", "hyst_H4_L2", "ema5", "linear",
                 "cap70_linear", "TB_binary_T1"):
        yt = year_table(rows, pols[name], "ladder", BASE_COST_BPS, 0.0, "next_open")
        print(f"\n--- policy = {name} ---")
        print(f"{'year':6s} {'strategy':>10s} {'TQQQ B&H':>10s} {'QQQ B&H':>10s} "
              f"{'SPY B&H':>10s} {'meanLev':>8s}  {'vs TQQQ':>9s}")
        for r in yt:
            print(f"{r['year']:6s} {100*r['strat']:9.2f}% {100*r['tqqq']:9.2f}% "
                  f"{100*r['qqq']:9.2f}% {100*r['spy']:9.2f}% {r['lev']:7.2f} "
                  f"{100*(r['strat']-r['tqqq']):8.2f}%")

    # ------------------------------------------------------- daily series exports
    exports = {
        "daily_series.csv": ("hyst_H4_L2", "ladder", 0.0),
        "daily_series_binary_T3.csv": ("binary_T3", "ladder", 0.0),
        "daily_series_linear.csv": ("linear", "ladder", 0.0),
        "daily_series_linear_band20.csv": ("linear", "ladder", 0.6),
        "daily_series_ema5.csv": ("ema5", "ladder", 0.0),
        "daily_series_cap70_linear.csv": ("cap70_linear", "ladder", 0.0),
        "daily_series_puretqqq_binary_T3.csv": ("binary_T3", "pure_tqqq", 0.0),
        "daily_series_trendbreadth_T1.csv": ("TB_binary_T1", "ladder", 0.0),
    }
    print("\n" + "=" * 122)
    print("DAILY SERIES EXPORTS")
    print("=" * 122)
    for fn, (name, route, band) in exports.items():
        _, recs = run(rows, pols[name], route, BASE_COST_BPS, band, "next_open",
                      collect=True)
        path = os.path.join(DATA, fn)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
            w.writeheader(); w.writerows(recs)
        print(f"  {path}  ({len(recs)} rows, policy={name}, route={route}, band={band})")

    # ------------------------------------------------------------- score analytics
    print("\n" + "=" * 122)
    print("SCORE DISTRIBUTION AND NEXT-DAY TQQQ RETURN (full window)")
    print("   net_score = 2*count-5, the symmetric -5..+5 form")
    print("=" * 122)
    print(f"{'score':>5s} {'net':>4s} {'days':>6s} {'%days':>7s} "
          f"{'next-day TQQQ mean':>19s} {'annualised':>11s}")
    for s in range(6):
        idx = [i for i in range(len(rows) - 1) if int(rows[i]["score"]) == s]
        if not idx:
            continue
        fr = [px(rows[i + 1], "TQQQ", "close") / px(rows[i], "TQQQ", "close") - 1.0
              for i in idx]
        mean = sum(fr) / len(fr)
        print(f"{s:5d} {2*s-5:+4d} {len(idx):6d} {100.0*len(idx)/len(rows):6.1f}% "
              f"{100*mean:18.4f}% {100*((1+mean)**252-1):10.1f}%")


if __name__ == "__main__":
    main()
