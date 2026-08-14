import csv
BARS_MIN=3; VOL_RATIO=1.5; CLOCK_MIN=15; BASE_N=6; SKIP_OPEN=3

def load(p):
    return [{'t':r['t'],**{k:float(r[k]) for k in 'ohlcv'}} for r in csv.DictReader(open(p))]

def vwap(bars):
    num=sum((b['h']+b['l']+b['c'])/3*b['v'] for b in bars); den=sum(b['v'] for b in bars)
    return num/den if den else None

def leg_run(bars,i,up=True):
    s=i
    while s>0 and ((bars[s]['c']>bars[s-1]['c']) if up else (bars[s]['c']<bars[s-1]['c'])): s-=1
    return s

def med(v):
    v=sorted(v); n=len(v)
    return v[n//2] if n%2 else (v[n//2-1]+v[n//2])/2

def analyze(bars,i,prior_close,up=True):
    d={}; o=bars[0]['o']; px=bars[i]['c']; vw=vwap(bars[:i+1])
    d['px']=px; d['vwap']=vw
    d['day_chg']=(px/prior_close-1)*100*(1 if up else -1)
    d['tape_basic']= ((px>o and px>vw) if up else (px<o and px<vw)) and d['day_chg']>=2
    s=leg_run(bars,i,up); d['leg_min']=(i-s+1)*5
    # BASELINE: trailing median of the BASE_N bars preceding this bar, skipping the
    # opening SKIP_OPEN bars. Independent of where the leg is judged to start.
    lo=max(SKIP_OPEN, i-BASE_N); base=[b['v'] for b in bars[lo:i]]
    bl=med(base) if base else 0
    d['vol_ratio']= bars[i]['v']/bl if bl else 0
    leg_low=min(b['l'] for b in bars[s:i+1]) if up else max(b['h'] for b in bars[s:i+1])
    w=bars[max(0,i-BARS_MIN+1):i+1]
    new_ext = bars[i]['h']>=max(b['h'] for b in w) if up else bars[i]['l']<=min(b['l'] for b in w)
    hl = (min(b['l'] for b in bars[i-1:i+1]) > min(b['l'] for b in bars[i-3:i-1])) if (up and i>=3) \
         else ((max(b['h'] for b in bars[i-1:i+1]) < max(b['h'] for b in bars[i-3:i-1])) if i>=3 else False)
    directional = bars[i]['c']>bars[i]['o'] if up else bars[i]['c']<bars[i]['o']
    d['structure']= ((px>leg_low) if up else (px<leg_low)) and (new_ext or hl) and directional
    d['OLD']= d['tape_basic'] and d['vol_ratio']>=VOL_RATIO and d['leg_min']>=CLOCK_MIN
    d['NEW']= d['tape_basic'] and d['vol_ratio']>=VOL_RATIO and d['structure']
    return d

# ---------------------------------------------------------------------------
# Harness. Bars in ../data/bars/YYYY-MM-DD_SYM.csv (t,o,h,l,c,v; t = UTC HHMM,
# 5-minute, RTH). Fetch with get_equity_historicals(interval='5minute').
# Historical OI / spread / bid_size / ask_size do NOT exist in the API, so the
# liquidity gates are NOT backtestable here — only the leg rule is.
if __name__=='__main__':
    import os,sys
    D=os.path.join(os.path.dirname(__file__),'..','data','bars')
    cases=[('2026-08-12_NBIS.csv',193.23),('2026-08-13_BIRK.csv',36.74),
           ('2026-08-14_RDDT.csv',158.12),('2026-08-14_NU.csv',13.93)]
    rows=[]
    for f,pc in cases:
        p=os.path.join(D,f)
        if not os.path.exists(p): continue
        b=load(p)
        for i,x in enumerate(b):
            if x['t']<'1345' or x['t']>'1700': continue
            d=analyze(b,i,pc)
            d['fwd60']=(b[min(i+12,len(b)-1)]['c']/x['c']-1)*100
            rows.append((f[:-4],x['t'],d))
    for tag in ('OLD','NEW'):
        s=[r for r in rows if r[2][tag]]
        if s: print(f"{tag:4} fires={len(s):3} avg_fwd60={sum(r[2]['fwd60'] for r in s)/len(s):+.2f}% "
                    f"wins={sum(1 for r in s if r[2]['fwd60']>0)}/{len(s)}")
    print(f"decision points: {len(rows)}")
    print("disagreements:")
    for n,t,d in rows:
        if d['OLD']!=d['NEW']: print(f"  {n} {t} OLD={d['OLD']} NEW={d['NEW']} fwd60={d['fwd60']:+.2f}%")
