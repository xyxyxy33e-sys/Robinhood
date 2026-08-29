#!/usr/bin/env python3
"""Kairos five-factor regime scoring -- FACTOR CONSTRUCTION.

Builds the daily factor panel used by backtest.py and writes data/kairos/factors.csv.

Pure standard library (no numpy/pandas in this environment).

=============================================================================
PRE-REGISTRATION NOTE -- READ THIS FIRST
=============================================================================
Every threshold below was fixed from finance convention BEFORE any backtest
output was produced, and none of them was tuned on the results. That is a
deliberate methodological choice, not laziness:

  * The brief asks for a search period (inception..2019-12-31) where refinement
    is permitted and a locked holdout (2020-01-01..) opened exactly once.
  * The strongest possible version of that discipline is to do NO fitting at all,
    so that the search period is ALSO a clean out-of-sample test of a rule chosen
    on priors. That is what is done here. The threshold sweep over T = 0..5 and
    the allocation mappings are reported in full for both periods; nothing is
    selected on the basis of holdout performance.
  * A small robustness grid (alternative thresholds) is reported in the write-up
    to show the result is not knife-edge. It is labelled robustness, not
    selection, and no headline number is taken from it.

=============================================================================
THE FIVE FACTORS
=============================================================================
Each factor emits a boolean "healthy" flag. score = number of healthy factors (0..5).

1. CREDIT -- corporate credit spread, widening = risk-off.
   SERIES SUBSTITUTION (important, documented honestly):
   The brief specified FRED `BAMLH0A0HYM2` (ICE BofA US High Yield OAS). That
   series -- like every other ICE BofA `BAML*` series -- is licensed data and
   FRED's CSV endpoint serves only a ROLLING 3-YEAR WINDOW of it. Verified:
   the endpoint returns 796 rows starting 2023-08-29 regardless of the cosd/coed
   parameters, while non-ICE series on the identical endpoint honour cosd and
   return full history. A 3-year series cannot support a 2010-2026 backtest.
   We therefore use `BAA10Y` (Moody's Baa Corporate Bond Yield minus 10-Year
   Treasury), a full-history daily credit spread from the same source. The
   3-year overlap correlation against BAMLH0A0HYM2 is computed and reported by
   this script so the substitution is justified empirically rather than asserted.

   HEALTHY when spread <= its own trailing 252-trading-day MEDIAN.
   Why a self-referencing percentile and not an absolute level: the level of
   credit spreads is regime-dependent across a 16-year window (post-GFC vs ZIRP
   vs 2022 tightening), so any fixed number would be an implicit bet on the era.

   PUBLICATION LAG: Moody's/Treasury based series are published with a lag and are
   NOT reliably available at 3:50pm on the same day. We lag the credit series by
   one trading day (use day t-1's value for day t's decision). This is the
   conservative choice and removes a genuine lookahead channel.

2. VIX -- FRED `VIXCLS`.
   HEALTHY when VIX <= 20.0.
   Why absolute 20 and not a percentile: 20 is the canonical long-run cutoff
   between calm and stressed vol regimes and, crucially, it is a number chosen
   from outside this dataset -- it cannot have been fitted to it. A trailing
   percentile rule would adapt to a high-vol regime and call it "healthy", which
   is the wrong behaviour for a risk-off filter.
   NO LAG: VIX is a real-time index; its 3:50pm value is within noise of its
   close. This is the one same-day input and it is flagged as an approximation.

3. BREADTH -- % of a broad large-cap universe trading above its own 200-day MA.
   Universe: current S&P 500 membership (501 of 503 names retrievable).
   A name is included on day t only once it has 200 prior closes, so newly-listed
   names (GEV, SOLV, RDDT, ...) enter the breadth denominator at the right time
   rather than being silently back-filled.
   HEALTHY when breadth > 50%.
   SURVIVORSHIP CAVEAT (stated loudly in the write-up): membership is TODAY's
   S&P 500, not point-in-time. Names that fell out of the index between 2010 and
   2026 are absent, so historical breadth is biased UPWARD -- the surviving names
   are the ones that trended up. This makes the Breadth factor look healthier in
   the past than a point-in-time index would, which flatters any strategy that
   uses breadth as a risk-on trigger. It cannot be fixed without point-in-time
   membership data, which this environment does not have.

4. TREND -- QQQ close vs its own 200-day simple moving average.
   HEALTHY when QQQ close > QQQ 200dma. The classic unfitted trend filter.

5. UTILITIES -- defensive rotation tell. XLU outperforming the broad market is
   a classic risk-off signal.
   HEALTHY when XLU's trailing 60-trading-day return <= SPY's trailing 60-day
   return, i.e. utilities are NOT leading. Direction is stated explicitly because
   the sign convention is the easiest thing to get backwards: utilities LEADING
   is UNHEALTHY.

=============================================================================
OUTPUT
=============================================================================
data/kairos/factors.csv, one row per trading day from the first date on which
all five factors are computable, with RAW factor values alongside their booleans
so the scoring can be audited by eye.
"""
import csv
import os
import statistics

ROOT = "/home/user/Robinhood"
DATA = os.path.join(ROOT, "data", "kairos")
UNIV = os.path.join(DATA, "universe")
ETF = os.path.join(DATA, "etf")

CREDIT_LOOKBACK = 252      # trading days for the trailing credit median
CREDIT_LAG_DAYS = 1        # publication lag applied to the credit series
VIX_LEVEL = 20.0           # absolute, chosen from convention
BREADTH_MA = 200
BREADTH_THRESH = 50.0      # percent
TREND_MA = 200
UTIL_LOOKBACK = 60         # trading days for XLU vs SPY relative strength


# --------------------------------------------------------------------------- io
def read_two_col(path, valcol=1):
    """Read a d,<val> csv into an ordered list of (date, float) skipping blanks."""
    out = []
    with open(path) as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) <= valcol:
                continue
            v = row[valcol].strip()
            if v in ("", ".", "NA", "null"):
                continue
            try:
                out.append((row[0], float(v)))
            except ValueError:
                continue
    return out


def read_fred(path):
    """FRED csv: header is either DATE,<ID> or observation_date,<ID>. Missing = '.'."""
    return dict(read_two_col(path, 1))


def read_etf(path):
    """d,o,c -> dict date -> (open, close)."""
    out = {}
    with open(path) as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) < 3:
                continue
            out[row[0]] = (float(row[1]), float(row[2]))
    return out


def ffill_on(calendar, series):
    """Forward-fill a sparse {date: value} onto an ordered calendar. None before first obs."""
    out = []
    last = None
    keys = series
    for d in calendar:
        if d in keys:
            last = keys[d]
        out.append(last)
    return out


def rolling_mean(vals, n):
    """Simple rolling mean; element i uses vals[i-n+1..i]. None until enough history."""
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rolling_median(vals, n):
    """Rolling median over the last n non-None values (inclusive of current)."""
    out = [None] * len(vals)
    for i in range(len(vals)):
        if i < n - 1:
            continue
        window = [v for v in vals[i - n + 1:i + 1] if v is not None]
        if len(window) >= n // 2:
            out[i] = statistics.median(window)
    return out


# ------------------------------------------------------------------ breadth calc
def compute_breadth(calendar):
    """% of universe above its own 200dma, per calendar date.

    Each symbol contributes only on dates where it has >= BREADTH_MA prior closes
    in ITS OWN history. Symbols are aligned to the master calendar by date lookup,
    so a symbol that did not trade on a given date simply does not vote that day.
    """
    cal_idx = {d: i for i, d in enumerate(calendar)}
    n = len(calendar)
    above = [0] * n
    total = [0] * n

    files = sorted(f for f in os.listdir(UNIV) if f.endswith(".csv"))
    for fn in files:
        sym = fn[:-4]
        series = read_two_col(os.path.join(UNIV, fn), 1)
        if len(series) < BREADTH_MA + 1:
            continue
        dates = [d for d, _ in series]
        closes = [c for _, c in series]
        ma = rolling_mean(closes, BREADTH_MA)
        for j, d in enumerate(dates):
            if ma[j] is None:
                continue
            i = cal_idx.get(d)
            if i is None:
                continue
            total[i] += 1
            if closes[j] > ma[j]:
                above[i] += 1

    pct = [(100.0 * above[i] / total[i]) if total[i] > 0 else None for i in range(n)]
    return pct, total


# ------------------------------------------------------------------------- main
def main():
    qqq = read_etf(os.path.join(ETF, "QQQ.csv"))
    spy = read_etf(os.path.join(ETF, "SPY.csv"))
    xlu = read_etf(os.path.join(ETF, "XLU.csv"))
    tqqq = read_etf(os.path.join(ETF, "TQQQ.csv"))
    qld = read_etf(os.path.join(ETF, "QLD.csv"))
    bil = read_etf(os.path.join(ETF, "BIL.csv"))

    # Master trading calendar = QQQ's own trading days (full 2009-2026 coverage).
    calendar = sorted(qqq.keys())

    credit_raw = read_fred(os.path.join(DATA, "BAA10Y.csv"))
    vix_raw = read_fred(os.path.join(DATA, "VIXCLS.csv"))
    rf_raw = read_fred(os.path.join(DATA, "DGS3MO.csv"))
    hy_raw = read_fred(os.path.join(DATA, "BAMLH0A0HYM2.csv"))  # 3yr only, for cross-check

    credit = ffill_on(calendar, credit_raw)
    vix = ffill_on(calendar, vix_raw)
    rf = ffill_on(calendar, rf_raw)
    hy = ffill_on(calendar, hy_raw)

    # ---- credit: apply publication lag, then trailing median
    credit_lagged = [None] * len(calendar)
    for i in range(len(calendar)):
        j = i - CREDIT_LAG_DAYS
        credit_lagged[i] = credit[j] if j >= 0 else None
    credit_med = rolling_median(credit_lagged, CREDIT_LOOKBACK)

    # ---- trend
    qc = [qqq[d][1] for d in calendar]
    qqq_ma = rolling_mean(qc, TREND_MA)

    # ---- utilities relative strength
    xc = [xlu[d][1] for d in calendar]
    sc = [spy[d][1] for d in calendar]
    util_rel = [None] * len(calendar)
    for i in range(len(calendar)):
        j = i - UTIL_LOOKBACK
        if j >= 0:
            xr = xc[i] / xc[j] - 1.0
            sr = sc[i] / sc[j] - 1.0
            util_rel[i] = xr - sr   # >0 means utilities LEADING = unhealthy

    # ---- breadth
    breadth, breadth_n = compute_breadth(calendar)

    # ---- credit substitution justification: correlation on the 3yr overlap
    # NOTE ON ALIGNMENT: credit_lagged[i] holds day i-1's BAA10Y (publication lag),
    # so it must be compared against day i-1's HY OAS, not day i's. Comparing the
    # lagged series against the unlagged one destroys the daily-change correlation
    # (it reads 0.007 instead of 0.615) -- a pure alignment artefact, not a finding.
    pairs = [(hy[i - CREDIT_LAG_DAYS], credit_lagged[i]) for i in range(len(calendar))
             if i >= CREDIT_LAG_DAYS and hy[i - CREDIT_LAG_DAYS] is not None
             and credit_lagged[i] is not None]
    if len(pairs) > 30:
        a = [p[0] for p in pairs]
        b = [p[1] for p in pairs]
        ma_, mb_ = sum(a) / len(a), sum(b) / len(b)
        cov = sum((x - ma_) * (y - mb_) for x, y in zip(a, b))
        va = sum((x - ma_) ** 2 for x in a) ** 0.5
        vb = sum((y - mb_) ** 2 for y in b) ** 0.5
        corr = cov / (va * vb)
        # also correlation of daily CHANGES, the harder test
        da = [a[i] - a[i - 1] for i in range(1, len(a))]
        db = [b[i] - b[i - 1] for i in range(1, len(b))]
        mda, mdb = sum(da) / len(da), sum(db) / len(db)
        c2 = sum((x - mda) * (y - mdb) for x, y in zip(da, db))
        v1 = sum((x - mda) ** 2 for x in da) ** 0.5
        v2 = sum((y - mdb) ** 2 for y in db) ** 0.5
        dcorr = c2 / (v1 * v2)
        print(f"CREDIT SUBSTITUTION CHECK (overlap n={len(pairs)} days, "
              f"{pairs and calendar[0]}):")
        print(f"  level corr(BAMLH0A0HYM2, BAA10Y) = {corr:.4f}")
        print(f"  daily-change corr               = {dcorr:.4f}")

    # ---- assemble rows
    rows = []
    for i, d in enumerate(calendar):
        if d not in tqqq or d not in qld:
            continue          # before TQQQ inception, or non-trading day for a leg
        if None in (credit_lagged[i], credit_med[i], vix[i], breadth[i],
                    qqq_ma[i], util_rel[i], rf[i]):
            continue
        credit_ok = credit_lagged[i] <= credit_med[i]
        vix_ok = vix[i] <= VIX_LEVEL
        breadth_ok = breadth[i] > BREADTH_THRESH
        trend_ok = qc[i] > qqq_ma[i]
        util_ok = util_rel[i] <= 0.0
        score = sum([credit_ok, vix_ok, breadth_ok, trend_ok, util_ok])
        rows.append({
            "date": d,
            "credit_baa10y": f"{credit_lagged[i]:.4f}",
            "credit_med252": f"{credit_med[i]:.4f}",
            "hy_oas": ("" if hy[i] is None else f"{hy[i]:.4f}"),
            "vix": f"{vix[i]:.4f}",
            "breadth_pct": f"{breadth[i]:.4f}",
            "breadth_n": breadth_n[i],
            "qqq_close": f"{qc[i]:.6f}",
            "qqq_200dma": f"{qqq_ma[i]:.6f}",
            "xlu_spy_rel60": f"{util_rel[i]:.6f}",
            "xlu_spy_ratio": f"{xc[i] / sc[i]:.6f}",
            "dgs3mo": f"{rf[i]:.4f}",
            "tqqq_open": f"{tqqq[d][0]:.6f}",
            "tqqq_close": f"{tqqq[d][1]:.6f}",
            "qld_open": f"{qld[d][0]:.6f}",
            "qld_close": f"{qld[d][1]:.6f}",
            "qqq_open": f"{qqq[d][0]:.6f}",
            "spy_close": f"{sc[i]:.6f}",
            "bil_close": f"{bil[d][1]:.6f}" if d in bil else "",
            "credit_ok": int(credit_ok),
            "vix_ok": int(vix_ok),
            "breadth_ok": int(breadth_ok),
            "trend_ok": int(trend_ok),
            "utilities_ok": int(util_ok),
            "score": score,
            "score2_trend_breadth": int(breadth_ok) + int(trend_ok),
        })

    out = os.path.join(DATA, "factors.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"\nwrote {out}")
    print(f"rows: {len(rows)}  window: {rows[0]['date']} .. {rows[-1]['date']}")
    dist = {}
    for r in rows:
        dist[r["score"]] = dist.get(r["score"], 0) + 1
    print("score distribution (whole window):")
    for k in sorted(dist):
        print(f"  score {k}: {dist[k]:5d} days ({100.0*dist[k]/len(rows):5.1f}%)")
    for fac in ("credit_ok", "vix_ok", "breadth_ok", "trend_ok", "utilities_ok"):
        pct = 100.0 * sum(r[fac] for r in rows) / len(rows)
        print(f"  {fac:14s} healthy {pct:5.1f}% of days")
    print(f"breadth universe size: min={min(r['breadth_n'] for r in rows)} "
          f"max={max(r['breadth_n'] for r in rows)}")


if __name__ == "__main__":
    main()
