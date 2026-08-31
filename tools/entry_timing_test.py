import sys, os, glob, statistics as st
sys.path.insert(0,'tools')
from reversal_screen import load, fired, D

S={}
for p in sorted(glob.glob(os.path.join(D,'*.csv'))):
    S[os.path.basename(p)[:-4]]=load(p)
dates=sorted({b['d'] for bars in S.values() for b in bars})

# Three legs, each measured on the SAME bar pair:
#   overnight : signal-day close -> next open   (buy at the close, hold overnight)
#   session   : next open -> next close         (buy at the open)
#   c2c       : signal-day close -> next close  (buy at the close, hold through)
rows=[]
for d in dates:
    acc={k:{'s':[],'a':[]} for k in ('overnight','session','c2c')}
    for sym,bars in S.items():
        idx={b['d']:i for i,b in enumerate(bars)}
        if d not in idx: continue
        i=idx[d]
        if i<2: continue
        prev=bars[i-1]
        legs={'overnight':(bars[i]['o']/prev['c']-1)*100,
              'session'  :(bars[i]['c']/bars[i]['o']-1)*100,
              'c2c'      :(bars[i]['c']/prev['c']-1)*100}
        sig=fired(bars,i-1)
        for k,v in legs.items():
            acc[k]['a'].append(v)
            if sig: acc[k]['s'].append(v)
    if acc['session']['s'] and len(acc['session']['a'])>=20:
        rows.append({k:(st.mean(v['s']),st.mean(v['a'])) for k,v in acc.items()})

def rep(lab,xs):
    m=st.mean(xs); sd=st.stdev(xs); t=m/(sd/len(xs)**.5)
    print(f"  {lab:38s} {m:+7.3f}%  sd={sd:5.2f}  t={t:+5.2f}")

print(f"day-clustered, {len(rows)} signal days, benchmarked to the same day's universe\n")
for k,lab in (('overnight','buy at signal close -> next OPEN'),
              ('session','buy at next OPEN -> next close'),
              ('c2c','buy at signal close -> next CLOSE')):
    print(f"{lab}")
    rep("raw basket return",     [r[k][0] for r in rows])
    rep("same-day universe",     [r[k][1] for r in rows])
    rep("EXCESS", [r[k][0]-r[k][1] for r in rows])
    print()
