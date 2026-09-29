"""
Net-of-cost and net-of-tax simulation with drifting weights and average-cost lots.
 - monthly rebalance to equal weight; every share traded costs `bps` per side
 - taxes (optional): realized gains taxed at 35% short-term (<12m held) / 20% long-term,
   netted within each calendar year (no loss carry-forward), paid at the first rebalance of the next year.
 - dividends are inside adjusted-close returns and are NOT separately taxed (flatters high-yield names).
"""
import numpy as np, pandas as pd
from collections import Counter
from engine import Engine, stats
import buyback_signal as BS


def net_sim(E, holdings, bps=0.0, tax=False, st=0.35, lt=0.20):
    adjm = E.adjm
    dates = sorted(d for d in holdings if holdings[d])
    shares, cost, since = {}, {}, {}
    V_pre, traded, out_idx = [], [], []
    ledger = {"st": 0.0, "lt": 0.0}
    tax_due = 0.0
    year = None
    V = 1.0
    prev_p = None
    for d in dates:
        p = adjm.loc[d]
        if shares:
            V = sum(sh * p.get(t, np.nan) for t, sh in shares.items() if np.isfinite(p.get(t, np.nan))) + \
                sum(0 for _ in [0])  # names lacking a price are carried at last value below
        # carry unpriced names at prior value
        if prev_p is not None:
            for t, sh in shares.items():
                if not np.isfinite(p.get(t, np.nan)) and np.isfinite(prev_p.get(t, np.nan)):
                    V += sh * prev_p[t]
        if tax and year is not None and d.year != year and tax_due > 0:
            V -= tax_due
            f = 1 - tax_due / (V + tax_due)
            shares = {t: s * f for t, s in shares.items()}
            tax_due = 0.0
        year = d.year
        V_pre.append(V); out_idx.append(d)
        slots = [t for t in holdings[d] if np.isfinite(p.get(t, np.nan))]
        if not slots:
            prev_p = p
            continue
        cnt = Counter(slots)
        names = list(cnt)
        target_of = {t: V * cnt[t] / len(slots) for t in names}
        new_sh, tr = {}, 0.0
        for t in set(shares) | set(names):
            px = p.get(t, np.nan)
            if not np.isfinite(px):
                new_sh[t] = shares.get(t, 0.0); continue
            cur = shares.get(t, 0.0)
            tgt = target_of[t] / px if t in cnt else 0.0
            dsh = tgt - cur
            tr += abs(dsh) * px
            if dsh < 0 and tax:
                gain = (px - cost[t]) * (-dsh)
                long_ = (d - since[t]).days >= 365
                ledger["lt" if long_ else "st"] += gain
            if dsh > 0:
                old = cur
                cost[t] = (cost.get(t, px) * old + px * dsh) / (old + dsh) if old > 0 else px
                if old <= 0:
                    since[t] = d
            new_sh[t] = tgt
        c = bps / 1e4 * tr
        f = 1 - c / V if V > 0 else 1
        shares = {t: s * f for t, s in new_sh.items() if s > 1e-12}
        traded.append(tr / V)
        if tax:
            nxt = d.year != (dates[dates.index(d) + 1].year if dates.index(d) + 1 < len(dates) else d.year)
            if nxt or d == dates[-1]:
                net = ledger["st"] + ledger["lt"]
                if net > 0:
                    w_st = max(ledger["st"], 0) / max(max(ledger["st"], 0) + max(ledger["lt"], 0), 1e-12)
                    tax_due = net * (w_st * st + (1 - w_st) * lt)
                ledger = {"st": 0.0, "lt": 0.0}
        prev_p = p
    s = pd.Series(V_pre, index=pd.DatetimeIndex(out_idx))
    r = s.pct_change().dropna()
    return r, float(np.mean(traded)) if traded else np.nan


if __name__ == "__main__":
    E = Engine()
    q0, q1, q2, q3, cap = BS.panels(E.close, E.mes)
    sc = BS.scores(q0, q1, q2, q3, cap)
    mom_ok = (E.mom[252] > 0).reindex(columns=cap.columns).fillna(False)
    hyr, grr = E.hy_ranked(True), E.growth_ranked(True, 252)
    strat = {"Barbell v2": E.barbell(10, 20, hyr, grr, start='2006-10-01')}
    for nm, s in (("Buyback blend top30", sc["blend"]), ("Buyback blend+mom top30", sc["blend"].where(mom_ok))):
        h = {}
        for d in E.mes:
            v = s.loc[d].dropna()
            if len(v) >= 30: h[d] = list(v.sort_values(ascending=False).head(30).index)
        strat[nm] = h
    START = "2010-06-01"
    cases = [("gross (no cost)", 0, False), ("10 bps/side", 10, False), ("25 bps/side", 25, False), ("50 bps/side", 50, False), ("25 bps + tax", 25, True)]
    rows = []
    for name, h in strat.items():
        h = {d: v for d, v in h.items() if d >= pd.Timestamp(START) - pd.Timedelta(days=31)}
        for cn, bps, tx in cases:
            r, turn = net_sim(E, h, bps, tx)
            r = r[r.index >= START]
            c, v, sh, dd = stats(r)
            rows.append((name, cn, c * 100, v * 100, sh, dd * 100, turn * 100))
    spy = E.spy_ret.dropna(); spy = spy[spy.index >= START]
    c, v, sh, dd = stats(spy)
    rows.append(("SPY (buy & hold)", "-", c * 100, v * 100, sh, dd * 100, 0.0))
    df = pd.DataFrame(rows, columns=["strategy", "case", "CAGR", "vol", "Sharpe", "MaxDD", "avg monthly one-way turnover %"])
    df.to_csv("cost_tax_results.csv", index=False)
    pd.options.display.float_format = "{:.2f}".format
    print(df.to_string(index=False))
