#!/usr/bin/env python3
"""Kairos five-factor regime system -- BACKTEST ENGINE.

Self-contained and re-runnable:  python3 tools/kairos/backtest.py
Reads  data/kairos/factors.csv   (built by tools/kairos/factors.py)
Writes data/kairos/daily_series*.csv and prints every results table.

=============================================================================
WHAT IS BEING TESTED
=============================================================================
A daily decision: what fraction of capital sits in TQQQ (3x Nasdaq-100) versus
a T-bill. The fraction is driven by a 0-5 count of "healthy" factors (Credit,
VIX, Breadth, Trend, Utilities), reported equivalently as a symmetric net score
of -5..+5 (net = 2*count - 5; each factor contributes +1 healthy / -1 unhealthy),
which is the same shape as Raincheck's disclosed -9..+9 Market Signal.

=============================================================================
THE BENCHMARK THAT MATTERS
=============================================================================
The primary comparison is BUY-AND-HOLD TQQQ over the identical window.
Beating SPY or QQQ with a 3x leveraged instrument is not evidence of skill --
it is what leverage does in a rising market. A regime filter is only long TQQQ
or in cash; while it is long it IS buy-and-hold TQQQ and contributes nothing.
One hundred percent of any edge must come from what it avoids while flat.
SPY and QQQ buy-and-hold are reported too (the marketing sites compare to them)
but they are the secondary line, not the headline.

=============================================================================
NO LOOKAHEAD
=============================================================================
Factors are computed from day t's CLOSE. Two execution assumptions are reported:

  NEXT-OPEN (primary, fully implementable): the signal from day t's close is
    filled at day t+1's OPEN. Day t+1 is split into an overnight segment
    (close_t -> open_t+1) carried at the OLD weight and an intraday segment
    (open_t+1 -> close_t+1) carried at the NEW weight. Nothing uses information
    unavailable at the time of the fill.

  SAME-CLOSE / MOC (secondary): the signal from day t's close is filled at day
    t's close, as a market-on-close order decided at ~3:50pm. This requires the
    3:50pm values of the factors to stand in for their official closes. VIX is a
    real-time index so this is a mild approximation; the credit series is lagged
    a full trading day in factors.py precisely so it is never an issue.

Both are reported so the gap between them is visible rather than assumed away.

=============================================================================
COSTS
=============================================================================
Charged as basis points on the NOTIONAL TRADED, i.e. cost = bps * |dw|, so a
graded mapping that shuffles 10% of the book pays a tenth of what a full 0->100%
flip pays. TQQQ is among the most liquid ETFs in existence (spreads ~1bp on a
$70 share), so 2bp round-trip-equivalent is the base case; 5/10/20bp are stress
cases that also stand in for the wider spreads of TQQQ's early years (2010-2012).

=============================================================================
SEARCH / HOLDOUT
=============================================================================
SEARCH  = inception (2010-02-11) .. 2019-12-31
HOLDOUT = 2020-01-01 .. end (2026-08-27), opened once, unmodified.
The holdout is deliberately aligned with Kairos's claimed 2020-2026 window.
NOTE: the search period is a near-uninterrupted Nasdaq bull market, where a risk
filter has almost nothing to prove and will tend to look useless or harmful; the
holdout contains the 2020, 2022 and 2025 drawdowns. A good holdout result is
therefore partly luck about which period got which stress, and a weak search
result is not damning. Both are reported side by side and neither is hidden.
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
BAND_GRID = [0.0, 0.10, 0.20]
TRADING_DAYS = 252


# --------------------------------------------------------------- allocation maps
def make_mappings():
    """score (0..5) -> target TQQQ weight. Every mapping is a fixed function of the
    score; none is fitted to returns."""
    m = {}
    for T in range(0, 6):
        m[f"binary_T{T}"] = tuple(1.0 if s >= T else 0.0 for s in range(6))
    m["linear"] = tuple(s / 5.0 for s in range(6))
    m["convex_sq"] = tuple((s / 5.0) ** 2 for s in range(6))
    m["convex_step"] = (0.0, 0.0, 0.0, 1 / 3, 2 / 3, 1.0)
    # Capped at 70%: Raincheck discloses deploying only ~67-75% to TQQQ even at
    # maximum conviction, with the remainder in T-bills / covered-call ETF.
    m["cap70_linear"] = tuple(0.70 * s / 5.0 for s in range(6))
    m["cap70_binary_T4"] = tuple(0.70 if s >= 4 else 0.0 for s in range(6))
    m["cap70_convex_step"] = tuple(0.70 * x for x in (0.0, 0.0, 0.0, 1 / 3, 2 / 3, 1.0))
    return m


def make_mappings2():
    """Raincheck-style ablation: Trend + Breadth ONLY, score2 in 0..2."""
    return {
        "TB_binary_T1": (0.0, 1.0, 1.0),
        "TB_binary_T2": (0.0, 0.0, 1.0),
        "TB_linear": (0.0, 0.5, 1.0),
        "TB_cap70_T2": (0.0, 0.0, 0.70),
    }


# ------------------------------------------------------------------------ engine
def run(rows, weights_by_score, score_key, cost_bps, band, execution,
        collect=False):
    """Simulate. rows must be the full contiguous slice for the period.

    Returns dict of metrics; if collect, also a per-day record list.
    """
    equity = 1.0
    cur_w = 0.0
    curve = []
    rets = []
    rf_list = []
    n_trades = 0
    turnover = 0.0
    invested_days = 0.0
    recs = []

    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]
        target = weights_by_score[int(prev[score_key])]
        rf_d = daily_rf(float(prev["dgs3mo"]))
        c0 = float(prev["tqqq_close"])
        c1 = float(cur["tqqq_close"])
        o1 = float(cur["tqqq_open"])
        traded = 0
        start_eq = equity

        if execution == "next_open":
            # overnight at the OLD weight
            equity *= (1.0 + cur_w * (o1 / c0 - 1.0) + (1.0 - cur_w) * rf_d)
            # rebalance at the open
            if abs(target - cur_w) > band:
                dw = abs(target - cur_w)
                equity *= (1.0 - cost_bps * 1e-4 * dw)
                turnover += dw
                n_trades += 1
                cur_w = target
                traded = 1
            # intraday at the NEW weight
            equity *= (1.0 + cur_w * (c1 / o1 - 1.0))
        else:  # same_close / MOC -- decided and filled at prev close
            if abs(target - cur_w) > band:
                dw = abs(target - cur_w)
                equity *= (1.0 - cost_bps * 1e-4 * dw)
                turnover += dw
                n_trades += 1
                cur_w = target
                traded = 1
            equity *= (1.0 + cur_w * (c1 / c0 - 1.0) + (1.0 - cur_w) * rf_d)

        r = equity / start_eq - 1.0
        rets.append(r)
        rf_list.append(rf_d)
        curve.append(equity)
        invested_days += cur_w

        if collect:
            recs.append({
                "date": cur["date"],
                "hy_oas": cur["hy_oas"],
                "credit_baa10y": cur["credit_baa10y"],
                "credit_med252": cur["credit_med252"],
                "vix": cur["vix"],
                "breadth_pct": cur["breadth_pct"],
                "qqq_close": cur["qqq_close"],
                "qqq_200dma": cur["qqq_200dma"],
                "xlu_spy_ratio": cur["xlu_spy_ratio"],
                "xlu_spy_rel60": cur["xlu_spy_rel60"],
                "credit_ok": cur["credit_ok"],
                "vix_ok": cur["vix_ok"],
                "breadth_ok": cur["breadth_ok"],
                "trend_ok": cur["trend_ok"],
                "utilities_ok": cur["utilities_ok"],
                "score": cur["score"],
                "net_score": 2 * int(cur["score"]) - 5,
                "signal_score_used": prev[score_key],
                "target_weight": f"{target:.4f}",
                "actual_weight": f"{cur_w:.4f}",
                "traded_flag": traded,
                "tqqq_ret": f"{c1 / c0 - 1.0:.6f}",
                "tbill_ret": f"{rf_d:.8f}",
                "portfolio_ret": f"{r:.6f}",
                "equity_curve": f"{equity:.6f}",
            })

    m = metrics(curve, rets, rf_list, len(rows) - 1)
    m["trades"] = n_trades
    m["turnover"] = turnover
    m["pct_invested"] = 100.0 * invested_days / max(1, len(rets))
    yrs = (len(rows) - 1) / TRADING_DAYS
    m["trades_per_yr"] = n_trades / yrs if yrs > 0 else 0.0
    if collect:
        dd = drawdown_series(curve)
        for k, rec in enumerate(recs):
            rec["drawdown"] = f"{dd[k]:.6f}"
        return m, recs
    return m


def daily_rf(annual_pct):
    """DGS3MO is an annualised percentage. Compound to a daily rate."""
    return (1.0 + annual_pct / 100.0) ** (1.0 / TRADING_DAYS) - 1.0


def drawdown_series(curve):
    out = []
    peak = -1e18
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
    var = sum((r - mu) ** 2 for r in rets) / max(1, len(rets) - 1)
    sd = math.sqrt(var)
    vol = sd * math.sqrt(TRADING_DAYS)
    ex = [rets[i] - rf_list[i] for i in range(len(rets))]
    mex = sum(ex) / len(ex)
    vex = sum((r - mex) ** 2 for r in ex) / max(1, len(ex) - 1)
    sdex = math.sqrt(vex)
    sharpe = (mex / sdex) * math.sqrt(TRADING_DAYS) if sdex > 0 else float("nan")
    mdd = min(drawdown_series(curve))
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": mdd,
            "final": curve[-1], "years": yrs}


def buy_hold(rows, price_key, cost_bps=0.0):
    """Buy and hold a price series, fully invested throughout."""
    equity = 1.0
    curve, rets, rfs = [], [], []
    for i in range(1, len(rows)):
        c0 = float(rows[i - 1][price_key])
        c1 = float(rows[i][price_key])
        r = c1 / c0 - 1.0
        equity *= (1.0 + r)
        curve.append(equity)
        rets.append(r)
        rfs.append(daily_rf(float(rows[i - 1]["dgs3mo"])))
    m = metrics(curve, rets, rfs, len(rows) - 1)
    m.update({"trades": 1, "turnover": 1.0, "pct_invested": 100.0, "trades_per_yr": 0.0})
    return m


def tbill_only(rows):
    equity = 1.0
    curve, rets, rfs = [], [], []
    for i in range(1, len(rows)):
        rf_d = daily_rf(float(rows[i - 1]["dgs3mo"]))
        equity *= (1.0 + rf_d)
        curve.append(equity)
        rets.append(rf_d)
        rfs.append(rf_d)
    m = metrics(curve, rets, rfs, len(rows) - 1)
    m.update({"trades": 0, "turnover": 0.0, "pct_invested": 0.0, "trades_per_yr": 0.0})
    return m


# ------------------------------------------------------------------- presentation
def fmt(m):
    return (f"{100*m['cagr']:7.2f}% {100*m['vol']:7.2f}% {m['sharpe']:6.2f} "
            f"{100*m['mdd']:8.2f}% {m['trades']:6d} {m['trades_per_yr']:6.1f} "
            f"{m['turnover']:8.1f} {m['pct_invested']:6.1f}%")


HDR = (f"{'strategy':24s} {'CAGR':>8s} {'vol':>8s} {'Sharpe':>6s} {'maxDD':>9s} "
       f"{'trades':>6s} {'tr/yr':>6s} {'turnovr':>8s} {'%inv':>7s}")


def slice_rows(rows, lo=None, hi=None):
    return [r for r in rows
            if (lo is None or r["date"] >= lo) and (hi is None or r["date"] <= hi)]


def year_table(rows, mapping, score_key, cost_bps, band, execution):
    """Calendar-year returns for the strategy and each benchmark."""
    years = sorted({r["date"][:4] for r in rows})
    out = []
    for y in years:
        seg = slice_rows(rows, f"{y}-01-01", f"{y}-12-31")
        if len(seg) < 20:
            continue
        # include the prior day so the first day's return is measured correctly
        idx = rows.index(seg[0])
        seg_full = rows[max(0, idx - 1):rows.index(seg[-1]) + 1]
        s = run(seg_full, mapping, score_key, cost_bps, band, execution)
        out.append({
            "year": y,
            "strat": s["final"] - 1.0,
            "tqqq": buy_hold(seg_full, "tqqq_close")["final"] - 1.0,
            "qqq": buy_hold(seg_full, "qqq_close")["final"] - 1.0,
            "spy": buy_hold(seg_full, "spy_close")["final"] - 1.0,
            "avg_w": s["pct_invested"],
        })
    return out


def main():
    with open(FACTORS) as f:
        rows = list(csv.DictReader(f))
    print(f"factor panel: {len(rows)} days  {rows[0]['date']} .. {rows[-1]['date']}\n")

    periods = {
        "SEARCH  (2010-02-11..2019-12-31)": slice_rows(rows, None, SEARCH_END),
        "HOLDOUT (2020-01-01..2026-08-27)": slice_rows(rows, HOLDOUT_START, None),
        "FULL    (2010-02-11..2026-08-27)": rows,
    }
    maps = make_mappings()
    maps2 = make_mappings2()

    # ---------------------------------------------------------------- benchmarks
    print("=" * 118)
    print("BENCHMARKS  (buy-and-hold, no timing).  PRIMARY COMPARATOR = TQQQ B&H")
    print("=" * 118)
    for pname, prow in periods.items():
        print(f"\n--- {pname}   n={len(prow)} days ---")
        print(HDR)
        print(f"{'TQQQ buy-and-hold':24s} {fmt(buy_hold(prow, 'tqqq_close'))}")
        print(f"{'QQQ buy-and-hold':24s} {fmt(buy_hold(prow, 'qqq_close'))}")
        print(f"{'SPY buy-and-hold':24s} {fmt(buy_hold(prow, 'spy_close'))}")
        print(f"{'T-bill only':24s} {fmt(tbill_only(prow))}")

    # ------------------------------------------------- main sweep, base cost/band
    for band in BAND_GRID:
        print("\n" + "=" * 118)
        print(f"FIVE-FACTOR SWEEP -- execution=next_open, cost={BASE_COST_BPS}bp, "
              f"no-trade band={band:.0%}")
        print("=" * 118)
        for pname, prow in periods.items():
            print(f"\n--- {pname} ---")
            print(HDR)
            for name, wmap in maps.items():
                m = run(prow, wmap, "score", BASE_COST_BPS, band, "next_open")
                print(f"{name:24s} {fmt(m)}")
            for name, wmap in maps2.items():
                m = run(prow, wmap, "score2_trend_breadth", BASE_COST_BPS, band, "next_open")
                print(f"{name:24s} {fmt(m)}")

    # ------------------------------------------------------- execution comparison
    print("\n" + "=" * 118)
    print("EXECUTION TIMING: next_open (implementable) vs same_close (3:50pm MOC), "
          f"cost={BASE_COST_BPS}bp band=0%")
    print("=" * 118)
    for pname, prow in periods.items():
        print(f"\n--- {pname} ---")
        print(f"{'strategy':24s} {'CAGR nxtopen':>13s} {'CAGR MOC':>10s} {'gap':>8s} "
              f"{'Shrp nxtopen':>13s} {'Shrp MOC':>10s}")
        for name in ("binary_T3", "binary_T4", "binary_T5", "linear", "convex_step",
                     "cap70_linear"):
            a = run(prow, maps[name], "score", BASE_COST_BPS, 0.0, "next_open")
            b = run(prow, maps[name], "score", BASE_COST_BPS, 0.0, "same_close")
            print(f"{name:24s} {100*a['cagr']:12.2f}% {100*b['cagr']:9.2f}% "
                  f"{100*(b['cagr']-a['cagr']):7.2f}% {a['sharpe']:13.2f} {b['sharpe']:10.2f}")

    # ------------------------------------------------------------ cost sensitivity
    print("\n" + "=" * 118)
    print("COST SENSITIVITY (CAGR), execution=next_open, band=0%")
    print("=" * 118)
    for pname, prow in periods.items():
        print(f"\n--- {pname} ---")
        print(f"{'strategy':24s} " + " ".join(f"{c:>7.0f}bp" for c in COST_GRID))
        for name, wmap in list(maps.items()) + list(maps2.items()):
            key = "score2_trend_breadth" if name.startswith("TB_") else "score"
            cells = []
            for c in COST_GRID:
                m = run(prow, wmap, key, c, 0.0, "next_open")
                cells.append(f"{100*m['cagr']:8.2f}%")
            print(f"{name:24s} " + " ".join(cells))

    # ---------------------------------------------- turnover: graded vs binary
    print("\n" + "=" * 118)
    print("TURNOVER / COST DRAG: graded vs binary, WITH and WITHOUT no-trade band")
    print("   (drag = CAGR at 0bp minus CAGR at 20bp, i.e. what costs would eat)")
    print("=" * 118)
    for pname, prow in periods.items():
        print(f"\n--- {pname} ---")
        print(f"{'strategy':22s} {'band':>5s} {'trades':>7s} {'tr/yr':>6s} "
              f"{'turnover':>9s} {'CAGR@0bp':>9s} {'CAGR@20bp':>10s} {'drag':>7s}")
        for name in ("binary_T3", "binary_T4", "binary_T5", "linear", "convex_sq",
                     "convex_step", "cap70_linear", "TB_binary_T2"):
            wmap = maps2[name] if name.startswith("TB_") else maps[name]
            key = "score2_trend_breadth" if name.startswith("TB_") else "score"
            for band in BAND_GRID:
                a = run(prow, wmap, key, 0.0, band, "next_open")
                b = run(prow, wmap, key, 20.0, band, "next_open")
                print(f"{name:22s} {band:5.0%} {a['trades']:7d} {a['trades_per_yr']:6.1f} "
                      f"{a['turnover']:9.1f} {100*a['cagr']:8.2f}% {100*b['cagr']:9.2f}% "
                      f"{100*(a['cagr']-b['cagr']):6.2f}%")

    # --------------------------------------------------------------- year by year
    print("\n" + "=" * 118)
    print("YEAR BY YEAR (calendar-year total return), strategy = binary_T4 and linear, "
          f"next_open, {BASE_COST_BPS}bp, band=0%")
    print("=" * 118)
    for stratname in ("binary_T2", "binary_T3", "binary_T4", "linear",
                      "cap70_linear", "TB_binary_T1"):
        wmap = maps2[stratname] if stratname.startswith("TB_") else maps[stratname]
        skey = "score2_trend_breadth" if stratname.startswith("TB_") else "score"
        yt = year_table(rows, wmap, skey, BASE_COST_BPS, 0.0, "next_open")
        print(f"\n--- strategy = {stratname} ---")
        print(f"{'year':6s} {'strategy':>10s} {'TQQQ B&H':>10s} {'QQQ B&H':>10s} "
              f"{'SPY B&H':>10s} {'avg wt':>8s}  {'vs TQQQ':>9s}")
        for r in yt:
            print(f"{r['year']:6s} {100*r['strat']:9.2f}% {100*r['tqqq']:9.2f}% "
                  f"{100*r['qqq']:9.2f}% {100*r['spy']:9.2f}% {r['avg_w']:7.1f}% "
                  f"{100*(r['strat']-r['tqqq']):8.2f}%")

    # ------------------------------------------------------- daily series exports
    exports = {
        "daily_series.csv": ("binary_T4", "score", 0.0),
        "daily_series_linear.csv": ("linear", "score", 0.0),
        "daily_series_linear_band20.csv": ("linear", "score", 0.20),
        "daily_series_cap70_linear.csv": ("cap70_linear", "score", 0.0),
        "daily_series_trendbreadth_T2.csv": ("TB_binary_T2", "score2_trend_breadth", 0.0),
    }
    print("\n" + "=" * 118)
    print("DAILY SERIES EXPORTS")
    print("=" * 118)
    for fn, (name, key, band) in exports.items():
        wmap = maps2[name] if name.startswith("TB_") else maps[name]
        _, recs = run(rows, wmap, key, BASE_COST_BPS, band, "next_open", collect=True)
        path = os.path.join(DATA, fn)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
            w.writeheader()
            w.writerows(recs)
        print(f"  {path}  ({len(recs)} rows, mapping={name}, band={band:.0%})")

    # ------------------------------------------------------------- score analytics
    print("\n" + "=" * 118)
    print("SCORE DISTRIBUTION AND FORWARD RETURNS (full window)")
    print("   net_score = 2*count-5, the symmetric -5..+5 form")
    print("=" * 118)
    print(f"{'score':>5s} {'net':>4s} {'days':>6s} {'%days':>7s} "
          f"{'next-day TQQQ mean':>19s} {'ann.':>9s}")
    for s in range(6):
        idx = [i for i in range(len(rows) - 1) if int(rows[i]["score"]) == s]
        if not idx:
            continue
        fr = [float(rows[i + 1]["tqqq_close"]) / float(rows[i]["tqqq_close"]) - 1.0
              for i in idx]
        mean = sum(fr) / len(fr)
        print(f"{s:5d} {2*s-5:+4d} {len(idx):6d} {100.0*len(idx)/len(rows):6.1f}% "
              f"{100*mean:18.4f}% {100*((1+mean)**252-1):8.1f}%")


if __name__ == "__main__":
    main()
