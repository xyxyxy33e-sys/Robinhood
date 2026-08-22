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
    # Cases are loaded from data/bars/manifest.csv (file,prior_close,is_call,direction),
    # which is generated from the live leg_log so the backtest corpus tracks what the
    # strategy actually evaluated. Legacy hand-listed cases are appended if still present.
    MAN=os.path.join(D,'manifest.csv')
    cases=[]
    if os.path.exists(MAN):
        import csv as _csv
        for row in _csv.DictReader(open(MAN)):
            cases.append((row['file'],float(row['prior_close']),row['is_call']=='1',row['direction']))
    legacy=[('2026-07-23_TSLA.csv',374.01,False,'WIN +$920 put'),
            ('2026-07-23_GOOGL.csv',342.09,False,'WIN +$405 put'),
            ('2026-07-31_AAPL.csv',333.43,False,'LOSS -$1568 put'),
            ('2026-08-04_PLTR.csv',125.65,True ,'WIN +$725'),
            ('2026-08-06_U.csv',35.47,True ,'LOSS -$1536'),
            ('2026-08-12_NBIS.csv',193.23,True ,'uptrend +27.4%'),
            ('2026-08-13_BIRK.csv',36.74,True ,'no-trade'),
            ('2026-08-14_NU.csv',13.93,True ,'no-trade')]
    have={c[0] for c in cases}
    cases += [c for c in legacy if c[0] not in have]
    rows=[]
    for f,pc,up,lab in cases:
        p=os.path.join(D,f)
        if not os.path.exists(p): continue
        b=load(p)
        for i,x in enumerate(b):
            if x['t']<'1345' or x['t']>'1700': continue
            d=analyze(b,i,pc,up)
            raw=(b[min(i+12,len(b)-1)]['c']/x['c']-1)*100
            d['fwd60']= raw if up else -raw   # direction-adjusted: gain for the trade
            d['lab']=lab; d['up']=up
            rows.append((f[:-4],x['t'],d))
    # --- modelled P&L: the sweep below it measures MFE/MAE, which is NOT P&L.
    # Only the FIRST qualifying signal per name-day becomes a trade, and a signal
    # with good MFE still loses if it trips the -25% stop first. This applies the
    # real exit cascade to an option position. Assumptions: LEV x delta leverage,
    # theta at 14 DTE, fixed round-trip spread friction. Ignores IV moves.
    if '--pnl' in sys.argv:
        LEV=float(os.environ.get('LEV','7.9')); THETA=-3.3; FRIC=-3.0
        STOP=float(os.environ.get('STOP','-25')); ARM=float(os.environ.get('ARM','12'))
        TRAIL=float(os.environ.get('TRAIL','20')); FLOOR=float(os.environ.get('FLOOR','10'))
        def sim(b,i,up):
            e=b[i]['c']; hwm=0.0; armed=False; n=0
            for y in b[i+1:]:
                n+=1; adj=THETA*(n*5/390.0)+FRIC
                pnl=(((y['c']-e)/e*100) if up else ((e-y['c'])/e*100))*LEV
                hi =(((y['h']-e)/e*100) if up else ((e-y['l'])/e*100))*LEV
                lo =(((y['l']-e)/e*100) if up else ((e-y['h'])/e*100))*LEV
                hwm=max(hwm,hi)
                if lo<=STOP: return STOP+adj
                if hi>=50:  return 50+adj
                if hwm>=ARM: armed=True
                if armed and pnl<=max(FLOOR,hwm-TRAIL): return max(FLOOR,hwm-TRAIL)+adj
                if not armed and hwm>=8 and pnl<=-3: return -3+adj
            return (((b[-1]['c']-e)/e*100) if up else ((e-b[-1]['c'])/e*100))*LEV+adj
        print(f"modelled P&L, one trade per name-day, {LEV}x leverage")
        print(f"{'thresh':>7}{'trades':>8}{'avg':>9}{'total':>9}{'wins':>7}")
        for th in (1.0,1.2,1.25,1.3,1.5,1.75,2.0):
            globals()['VOL_RATIO']=th; tr=[]
            for f,pc,up,lab in cases:
                fp=os.path.join(D,f)
                if not os.path.exists(fp): continue
                b=load(fp)
                for i,x in enumerate(b):
                    if x['t']<'1345' or x['t']>'1700': continue
                    if analyze(b,i,pc,up)['NEW'] and i<len(b)-1: tr.append(sim(b,i,up)); break
            if tr: print(f"{th:>7.2f}{len(tr):>8}{sum(tr)/len(tr):>+8.1f}%{sum(tr):>+8.0f}%"
                         f"{sum(1 for t in tr if t>0):>4}/{len(tr)}")
        raise SystemExit

    # --- volume-threshold sensitivity -------------------------------------
    if '--sweep' in sys.argv:
        print(f"{'thresh':>7}{'fires':>7}{'avgMFE':>9}{'avgMAE':>9}{'winners':>9}{'losers':>8}")
        wins={'2026-07-23_TSLA','2026-07-23_GOOGL','2026-08-04_PLTR','2026-08-12_NBIS'}
        for th in (1.0,1.1,1.2,1.25,1.3,1.4,1.5,1.75,2.0):
            globals()['VOL_RATIO']=th; fired=[]; w=set(); l=set()
            for f,pc,up,lab in cases:
                fp=os.path.join(D,f)
                if not os.path.exists(fp): continue
                b=load(fp)
                for i,x in enumerate(b):
                    if x['t']<'1345' or x['t']>'1700': continue
                    if not analyze(b,i,pc,up)['NEW']: continue
                    e=x['c']; fut=b[i+1:]
                    if not fut: continue
                    fired.append((max((y['h']-e)/e*100 if up else (e-y['l'])/e*100 for y in fut),
                                  min((y['l']-e)/e*100 if up else (e-y['h'])/e*100 for y in fut)))
                    (w if f[:-4] in wins else l).add(f)
            if fired:
                print(f"{th:>7.2f}{len(fired):>7}{sum(r[0] for r in fired)/len(fired):>+8.2f}%"
                      f"{sum(r[1] for r in fired)/len(fired):>+8.2f}%{len(w):>8}/4{len(l):>7}/5")
        raise SystemExit
    for tag in ('OLD','NEW'):
        s=[r for r in rows if r[2][tag]]
        if s: print(f"{tag:4} fires={len(s):3} avg_fwd60={sum(r[2]['fwd60'] for r in s)/len(s):+.2f}% "
                    f"wins={sum(1 for r in s if r[2]['fwd60']>0)}/{len(s)}")
    print(f"decision points: {len(rows)}")
    print("disagreements:")
    for n,t,d in rows:
        if d['OLD']!=d['NEW']: print(f"  {n} {t} OLD={d['OLD']} NEW={d['NEW']} fwd60={d['fwd60']:+.2f}%")
