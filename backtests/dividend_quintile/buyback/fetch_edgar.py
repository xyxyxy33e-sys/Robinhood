"""
Download point-in-time buyback and share-count facts for S&P 500 names from
the SEC EDGAR XBRL companyfacts API (free, no key; requires a descriptive
User-Agent and <=10 requests/sec).

Output: edgar_facts.json -> {ticker: {"rep": [...], "shares": [...]}}
  rep    : {start, end, val, filed, form} cash paid for share repurchases (USD)
  shares : {end, val, filed, form}        shares outstanding as reported
Each fact carries its `filed` date, so a backtest can use only what was
public at each rebalance date.

Run from a folder containing the cached price parquet (see ../download_data.py)
and backtest.py, or edit TICKERS below.
"""
import json, os, sys, threading, time
from pathlib import Path
import concurrent.futures as cf
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import load_data
OUT = Path(os.environ.get('EDGAR_OUT') or Path(__file__).resolve().parent.parent / '.cache' / 'edgar_facts.json')

UA = {"User-Agent": "research backtest xyxyxy33e@gmail.com"}
REP_TAGS = ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"]
SHARE_TAGS = [("dei", "EntityCommonStockSharesOutstanding"),
              ("us-gaap", "CommonStockSharesOutstanding")]
KEEP_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}

_lock, _last = threading.Lock(), [0.0]
def throttle(min_gap=0.12):
    with _lock:
        wait = _last[0] + min_gap - time.time()
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()

def get(url, tries=4):
    for i in range(tries):
        throttle()
        try:
            r = requests.get(url, headers=UA, timeout=90)
            if r.status_code == 200: return r.json()
            if r.status_code in (404,): return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None

def extract(facts):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    rep, seen = [], set()
    for tag in REP_TAGS:                         # earlier tag wins on duplicate periods
        for f in gaap.get(tag, {}).get("units", {}).get("USD", []):
            if f.get("form") not in KEEP_FORMS or "start" not in f: continue
            key = (f["start"], f["end"])
            if key in seen: continue
            seen.add(key)
            rep.append({k: f[k] for k in ("start", "end", "val", "filed", "form")})
    shares = []
    for ns, tag in SHARE_TAGS:
        for f in facts.get("facts", {}).get(ns, {}).get(tag, {}).get("units", {}).get("shares", []):
            if f.get("form") in KEEP_FORMS:
                shares.append({k: f[k] for k in ("end", "val", "filed", "form")})
        if shares: break
    return {"rep": rep, "shares": shares}

def main():
    uni = OUT.parent / 'universe.json'
    if uni.exists():
        tickers = json.load(open(uni))          # current S&P 500 members
    else:
        close, *_ = load_data()
        tickers = list(close.columns)
    tmap = get("https://www.sec.gov/files/company_tickers.json")
    cik = {v["ticker"].upper(): int(v["cik_str"]) for v in tmap.values()}
    missing = [t for t in tickers if t.upper() not in cik]
    print("no CIK for:", missing)

    def work(t):
        c = cik.get(t.upper())
        if c is None: return t, None
        j = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json")
        return t, (extract(j) if j else None)

    out = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for i, (t, d) in enumerate(ex.map(work, tickers), 1):
            if d: out[t] = d
            if i % 50 == 0: print(f"{i}/{len(tickers)} done, {len(out)} with data", flush=True)
    OUT.parent.mkdir(exist_ok=True)
    json.dump(out, open(OUT, "w"))
    n_rep = sum(1 for d in out.values() if d["rep"])
    n_sh = sum(1 for d in out.values() if d["shares"])
    print(f"saved {len(out)} tickers; {n_rep} with repurchase facts; {n_sh} with share counts")

if __name__ == "__main__":
    main()
