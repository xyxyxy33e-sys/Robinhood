"""
Second EDGAR pull: operating cash flow, dividends paid, net income (duration
facts with filing dates) for payout-sustainability and profitability filters.
Output: edgar_facts2.json -> {ticker: {"ocf": [...], "divpaid": [...], "ni": [...]}}
"""
import json
import concurrent.futures as cf
from backtest import load_data
from fetch_edgar import get, UA

TAGS = {
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "divpaid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "ni": ["NetIncomeLoss", "ProfitLoss"],
}
KEEP = {"10-K", "10-Q", "10-K/A", "10-Q/A"}

def extract(j):
    gaap = j.get("facts", {}).get("us-gaap", {})
    out = {}
    for key, tags in TAGS.items():
        rows, seen = [], set()
        for tag in tags:
            for f in gaap.get(tag, {}).get("units", {}).get("USD", []):
                if f.get("form") not in KEEP or "start" not in f: continue
                k = (f["start"], f["end"])
                if k in seen: continue
                seen.add(k)
                rows.append({c: f[c] for c in ("start", "end", "val", "filed", "form")})
        out[key] = rows
    return out

if __name__ == "__main__":
    close, *_ = load_data()
    tmap = get("https://www.sec.gov/files/company_tickers.json")
    cik = {v["ticker"].upper(): int(v["cik_str"]) for v in tmap.values()}
    def work(t):
        c = cik.get(t.upper())
        j = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json") if c else None
        return t, (extract(j) if j else None)
    res = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for i, (t, d) in enumerate(ex.map(work, list(close.columns)), 1):
            if d: res[t] = d
            if i % 100 == 0: print(i, flush=True)
    json.dump(res, open("edgar_facts2.json", "w"))
    print("saved", len(res), "| with OCF:", sum(1 for d in res.values() if d["ocf"]), "| NI:", sum(1 for d in res.values() if d["ni"]), "| divpaid:", sum(1 for d in res.values() if d["divpaid"]))
