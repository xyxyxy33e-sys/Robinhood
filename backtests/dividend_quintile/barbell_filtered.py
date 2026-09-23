import numpy as np
import pandas as pd
from backtest import load_data, month_end_dates, ttm_dividends, simulate_equal_weight, perf_stats

BACKTEST_END = "2026-09-23"
WINDOWS = {"5y": "2021-09-23", "10y": "2016-09-23", "20y": "2005-09-23"}
HALF = 25

def build_filtered_barbell(close, div, all_month_ends,
                            exclude_div_cutters=False,
                            exclude_crashers=False, crash_thresh=-0.25,
                            exclude_momentum_spike=False, spike_pct=0.90):
    ttm = ttm_dividends(div, all_month_ends)
    ttm_prior = ttm.shift(12)  # ~12 months earlier in the month-end series
    yld = (ttm / close.reindex(all_month_ends)).replace([np.inf, -np.inf], np.nan)

    px_me = close.reindex(all_month_ends)
    mom6 = px_me.pct_change(6)  # trailing 6-month return at each month-end

    holdings = {}
    for dt in all_month_ends:
        row = yld.loc[dt].dropna()
        px_ok = px_me.loc[dt, row.index].notna()
        row = row[px_ok]

        # --- high-yield universe with quality filters ---
        hy_universe = row.copy()
        if exclude_div_cutters and dt in ttm_prior.index:
            prior = ttm_prior.loc[dt]
            cur = ttm.loc[dt]
            cut = (cur < prior) & prior.notna() & (prior > 0)
            cutters = cut[cut].index
            hy_universe = hy_universe.drop(index=[t for t in cutters if t in hy_universe.index])
        if exclude_crashers and dt in mom6.index:
            m = mom6.loc[dt]
            crashed = m[m < crash_thresh].index
            hy_universe = hy_universe.drop(index=[t for t in crashed if t in hy_universe.index])
        hy_universe = hy_universe.sort_values(ascending=False)
        top = list(hy_universe.index[:HALF])

        # --- low-yield (growth) universe with momentum-spike filter ---
        lo_universe = row.copy()
        if exclude_momentum_spike and dt in mom6.index:
            m = mom6.loc[dt].reindex(lo_universe.index)
            cutoff = m.quantile(spike_pct)
            spikers = m[m > cutoff].index
            lo_universe = lo_universe.drop(index=[t for t in spikers if t in lo_universe.index])
        # deterministic tie-break within the (large) zero-yield cluster: use
        # trailing-12mo momentum descending, so among tied zero-yielders we
        # keep the stronger performers rather than an arbitrary sort order.
        if dt in mom6.index:
            mom12 = px_me.pct_change(12).loc[dt].reindex(lo_universe.index)
        else:
            mom12 = pd.Series(0.0, index=lo_universe.index)
        tie_break = pd.DataFrame({"yld": lo_universe, "mom12": mom12})
        tie_break = tie_break.sort_values(["yld", "mom12"], ascending=[True, False])
        bottom = list(tie_break.index[:HALF])

        if len(top) < HALF or len(bottom) < HALF:
            continue
        holdings[dt] = top + bottom
    return holdings


def main():
    close, adj, div, spy_adj = load_data()
    all_dates = close.index
    all_month_ends = month_end_dates(all_dates, all_dates.min(), BACKTEST_END)

    variants = {
        "Baseline 50 (25+25), no filters": build_filtered_barbell(close, div, all_month_ends),
        "+ exclude dividend cutters (HY leg)": build_filtered_barbell(
            close, div, all_month_ends, exclude_div_cutters=True),
        "+ exclude 6mo crashers <-25% (HY leg)": build_filtered_barbell(
            close, div, all_month_ends, exclude_crashers=True),
        "+ exclude div cutters + crashers (HY leg)": build_filtered_barbell(
            close, div, all_month_ends, exclude_div_cutters=True, exclude_crashers=True),
        "+ exclude top-decile 6mo spikers (growth leg)": build_filtered_barbell(
            close, div, all_month_ends, exclude_momentum_spike=True),
        "Full quality filter (all three)": build_filtered_barbell(
            close, div, all_month_ends, exclude_div_cutters=True,
            exclude_crashers=True, exclude_momentum_spike=True),
    }

    for wlabel, start in WINDOWS.items():
        bt_month_ends = month_end_dates(all_dates, start, BACKTEST_END)
        spy_me = spy_adj.reindex(bt_month_ends)
        spy_ret = spy_me.pct_change().dropna()
        print(f"\n########## {wlabel} ##########")
        for name, holdings in variants.items():
            rets = simulate_equal_weight(adj, holdings, bt_month_ends)
            if len(rets) < 6:
                print(f"{name}: insufficient data")
                continue
            perf_stats(rets, f"[{wlabel}] {name}")
        perf_stats(spy_ret, f"[{wlabel}] SPY")

if __name__ == "__main__":
    main()
