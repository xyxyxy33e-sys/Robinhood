import sys, os, glob, csv, statistics as st, math
sys.path.insert(0,'tools')
from reversal_screen import load, fired, D

# Build per-symbol series with trailing vol and dollar volume.
S={}
for p in sorted(glob.glob(os.path.join(D,'*.csv'))):
    sym=os.path.basename(p)[:-4]; bars=load(p)
    rets=[float('nan')]+[(bars[i]['c']/bars[i-1]['c']-1)*100 for i in range(1,len(bars))]
    S[sym]=(bars,rets,{b['d']:i for i,b in enumerate(bars)})

dates=sorted({d for _,_,idx in S.values() for d in idx})

def vol20(sym,i):
    _,rets,_=S[sym]
    w=[r for r in rets[max(1,i-20):i] if r==r]
    return st.stdev(w) if len(w)>2 else None

# For each trade date, collect qualifying names + features + the tradeable
# open->close return on that date.
days=[]
for k,d in enumerate(dates):
    if k==0: continue
    legs=[]
    for sym,(bars,rets,idx) in S.items():
        if d not in idx: continue
        i=idx[d]
        if i<1 or not fired(bars,i-1): continue
        sig=bars[i-1]
        drop=abs((sig['c']/bars[i-2]['c']-1)*100) if i>=2 else None
        v=vol20(sym,i-1)
        if drop is None or v is None or v==0: continue
        legs.append(dict(sym=sym, drop=drop, vol=v,
                         dv=sig['c']*sig['v'],
                         ret=(bars[i]['c']/bars[i]['o']-1)*100))
    if legs: days.append((d,legs))

print(f"{len(days)} trading days with at least one signal, "
      f"{sum(len(l) for _,l in days)} name-legs\n")

def port(wf,label):
    xs=[]
    for d,legs in days:
        w=[wf(l) for l in legs]; tot=sum(w)
        if tot<=0: continue
        xs.append(sum(wi/tot*l['ret'] for wi,l in zip(w,legs)))
    m=st.mean(xs); sd=st.stdev(xs); t=m/(sd/len(xs)**.5)
    sharpe=m/sd*math.sqrt(252)
    print(f"{label:34s} mean={m:+.3f}%  sd={sd:5.2f}%  t={t:+5.2f}  "
          f"ann.Sharpe={sharpe:5.2f}")
    return xs

print("=== portfolio weighting schemes (daily basket, open->close) ===")
port(lambda l: 1.0,                    "equal weight")
port(lambda l: l['drop'],              "proportional to drop size")
port(lambda l: math.sqrt(l['drop']),   "proportional to sqrt(drop)")
port(lambda l: 1.0/l['vol'],           "inverse trailing volatility")
port(lambda l: l['dv'],                "proportional to dollar volume")
port(lambda l: 1.0/l['dv'],            "inverse dollar volume (small tilt)")
port(lambda l: l['drop']/l['vol'],     "drop / volatility (z-score-ish)")

print("\n=== is the per-name bounce actually related to these? ===")
allf=[l for _,legs in days for l in legs]
def bucket(key,label,edges):
    print(f"  by {label}:")
    vs=sorted(l[key] for l in allf)
    cuts=[vs[int(len(vs)*q)] for q in edges]
    prev=-1e18
    for c,q in list(zip(cuts,edges))[1:]+[(1e18,1.0)]:
        g=[l['ret'] for l in allf if prev<l[key]<=c]
        if len(g)>30:
            print(f"    <= {c:12.2f}  n={len(g):5}  mean={st.mean(g):+.3f}%  "
                  f"t={st.mean(g)/(st.stdev(g)/len(g)**.5):+5.2f}")
        prev=c
bucket('drop','drop size',[0,.25,.5,.75])
bucket('vol','trailing volatility',[0,.25,.5,.75])
bucket('dv','dollar volume (size proxy)',[0,.25,.5,.75])
