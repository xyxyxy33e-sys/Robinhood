"""Sector cap on the barbell growth leg (max k names per GICS sector), current GICS sectors from Wikipedia."""
import io, requests
import numpy as np, pandas as pd
from engine import Engine, stats

def sectors():
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    df = pd.read_html(io.StringIO(r.text))[0]
    return dict(zip(df["Symbol"].str.replace(".", "-", regex=False), df["GICS Sector"]))

if __name__ == "__main__":
    E = Engine(); sec = sectors()
    hyr, grr = E.hy_ranked(True), E.growth_ranked(True, 252)
    def capper(k):
        def f(ranked, d, n):
            cnt, out = {}, []
            for t in ranked:
                s = sec.get(t, "?")
                if cnt.get(s, 0) < k:
                    out.append(t); cnt[s] = cnt.get(s, 0) + 1
                if len(out) == n: break
            return out
        return f
    cal = lambda r, y: ((1 + r[r.index.year == y]).prod() - 1) * 100 if (r.index.year == y).sum() > 6 else np.nan
    rows, hold = [], {}
    for k in (None, 8, 6, 5, 4, 3):
        h = E.barbell(10, 20, hyr, grr, cap_fn=None if k is None else capper(k), start='2006-10-01'); hold[k] = h
        r = E.port_returns(h); r = r[r.index >= "2006-10-01"]
        c, v, sh, dd = stats(r)
        r19 = r[r.index >= "2019-01-01"]; s19 = stats(r19)
        nsec = np.mean([len({sec.get(t, "?") for t in v_[10:]}) for v_ in h.values()])
        rows.append(("no cap" if k is None else f"max {k}/sector", c * 100, v * 100, sh, dd * 100, cal(r, 2008), cal(r, 2022), s19[2], nsec))
    df = pd.DataFrame(rows, columns=["growth-leg cap", "CAGR", "vol", "Sharpe", "MaxDD", "2008", "2022", "Sharpe 2019+", "avg sectors in growth leg"])
    df.to_csv("sector_cap_results.csv", index=False)
    pd.options.display.float_format = "{:.2f}".format
    print(df.to_string(index=False))
    d = E.mes[-2]
    for k in (None, 4):
        names = hold[k].get(d, [])[10:]
        comp = pd.Series([sec.get(t, "?") for t in names]).value_counts().to_dict()
        print(f"\ngrowth leg at {d.date()} ({'no cap' if k is None else f'cap {k}'}): {comp}")
