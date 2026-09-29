"""
Walk-forward validation. Design choices are ranked on a TRAIN window and then
judged on a TEST window the ranking never saw.
  Barbell grid : hy_n{5,10,15,20} x gr_n{10,20,30} x screens{off,on} x abs_mom{off,on} x lookback{126,252}
  Buyback grid : N{10,20,30,50} x signal{ttm,blend,weighted,recent1} x mom_filter{off,on} x size>=10B{off,on}
"""
import itertools
import numpy as np, pandas as pd
from engine import Engine, stats
import buyback_signal as BS

BB_TRAIN, BB_TEST = ("2010-05-01", "2018-12-31"), ("2019-01-01", "2026-08-31")
BAR_TRAIN, BAR_TEST = ("2006-10-01", "2018-12-31"), ("2019-01-01", "2026-08-31")


def evaluate(E, grid, train, test):
    rows = []
    for key, h in grid:
        r = E.port_returns(h)
        tr, te = stats(r[(r.index >= train[0]) & (r.index <= train[1])]), stats(r[(r.index >= test[0]) & (r.index <= test[1])])
        rows.append((*key, tr[0], tr[2], tr[3], te[0], te[2], te[3]))
    return rows


def report(name, rows, keycols, default_key, spy_tr, spy_te):
    df = pd.DataFrame(rows, columns=keycols + ["tr_cagr", "tr_sh", "tr_dd", "te_cagr", "te_sh", "te_dd"]).dropna(subset=["tr_sh", "te_sh"])
    df["tr_rank"] = df.tr_sh.rank(ascending=False); df["te_rank"] = df.te_sh.rank(ascending=False)
    print(f"\n########## {name}: {len(df)} configs ##########")
    print(f"SPY Sharpe train {spy_tr:.2f} / test {spy_te:.2f}")
    print(f"Rank correlation train->test Sharpe: {df.tr_sh.rank().corr(df.te_sh.rank()):.2f}")
    print(f"Mean Sharpe train {df.tr_sh.mean():.2f} -> test {df.te_sh.mean():.2f}; median test {df.te_sh.median():.2f}; "
          f"configs beating SPY in test: {(df.te_sh > spy_te).mean()*100:.0f}%")
    b = df.sort_values("tr_sh", ascending=False).iloc[0]
    print(f"Best-in-train: {tuple(b[keycols])} train Sh {b.tr_sh:.2f} -> test Sh {b.te_sh:.2f} (test rank {int(b.te_rank)}/{len(df)})")
    m = df[[tuple(r) == default_key for r in df[keycols].values]]
    if len(m):
        d = m.iloc[0]
        print(f"Default {default_key}: train Sh {d.tr_sh:.2f} (rank {int(d.tr_rank)}) -> test Sh {d.te_sh:.2f} (rank {int(d.te_rank)}); test CAGR {d.te_cagr*100:.1f}% DD {d.te_dd*100:.1f}%")
    print("Top 5 by train Sharpe:")
    print(df.sort_values("tr_sh", ascending=False).head(5)[keycols + ["tr_sh", "te_sh", "te_cagr", "te_dd", "te_rank"]].round(2).to_string(index=False))
    print("Best 3 by test Sharpe (hindsight):")
    print(df.sort_values("te_sh", ascending=False).head(3)[keycols + ["tr_sh", "te_sh", "tr_rank"]].round(2).to_string(index=False))
    return df


if __name__ == "__main__":
    E = Engine()
    spy = E.spy_ret.dropna()
    sp = lambda a, b: stats(spy[(spy.index >= a) & (spy.index <= b)])[2]

    # ---- barbell
    hyr = {s: E.hy_ranked(s) for s in (False, True)}
    grr = {(a, l): E.growth_ranked(a, l) for a in (False, True) for l in (126, 252)}
    grid = []
    for hn, gn, sc, ab, lb in itertools.product((5, 10, 15, 20), (10, 20, 30), (False, True), (False, True), (126, 252)):
        grid.append(((hn, gn, sc, ab, lb), E.barbell(hn, gn, hyr[sc], grr[(ab, lb)], start='2006-10-01')))
    rows = evaluate(E, grid, BAR_TRAIN, BAR_TEST)
    d1 = report("BARBELL", rows, ["hy_n", "gr_n", "screens", "abs_mom", "lookback"], (10, 20, True, True, 252), sp(*BAR_TRAIN), sp(*BAR_TEST))
    d1.to_csv("wf_barbell.csv", index=False)

    # ---- buyback
    q0, q1, q2, q3, cap = BS.panels(E.close, E.mes)
    sc = BS.scores(q0, q1, q2, q3, cap)
    mom_ok = (E.mom[252] > 0).reindex(columns=cap.columns)
    big = cap >= 10e9
    grid = []
    for n, sig, mf, sz in itertools.product((10, 20, 30, 50), ("ttm", "blend", "weighted", "recent1"), (False, True), (False, True)):
        s = sc[sig]
        if mf: s = s.where(mom_ok.fillna(False))
        if sz: s = s.where(big)
        h = {}
        for d in E.mes:
            v = s.loc[d].dropna()
            if len(v) >= max(n, 20):
                h[d] = list(v.sort_values(ascending=False).head(n).index)
        grid.append(((n, sig, mf, sz), h))
    rows = evaluate(E, grid, BB_TRAIN, BB_TEST)
    d2 = report("BUYBACK", rows, ["N", "signal", "mom_filter", "size10B"], (30, "blend", True, False), sp(*BB_TRAIN), sp(*BB_TEST))
    d2.to_csv("wf_buyback.csv", index=False)
