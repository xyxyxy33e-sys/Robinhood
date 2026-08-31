import sys, os, glob, statistics as st, math
sys.path.insert(0,'tools')
from reversal_screen import load, fired, D

S={}
for p in sorted(glob.glob(os.path.join(D,'*.csv'))):
    sym=os.path.basename(p)[:-4]; bars=load(p)
    S[sym]=(bars,{b['d']:i for i,b in enumerate(bars)})
dates=sorted({d for _,idx in S.values() for d in idx})

rows=[]
for d in dates:
    sig_oc, all_oc, sig_cc, all_cc = [],[],[],[]
    for sym,(bars,idx) in S.items():
        if d not in idx: continue
        i=idx[d]
        if i<2 or i>=len(bars): continue
        oc=(bars[i]['c']/bars[i]['o']-1)*100
        cc=(bars[i]['c']/bars[i-1]['c']-1)*100
        all_oc.append(oc); all_cc.append(cc)
        if fired(bars,i-1):
            sig_oc.append(oc); sig_cc.append(cc)
    if sig_oc and len(all_oc)>=20:
        rows.append(dict(d=d,n=len(sig_oc),
                         b_oc=st.mean(sig_oc), u_oc=st.mean(all_oc),
                         b_cc=st.mean(sig_cc), u_cc=st.mean(all_cc)))

def rep(label,xs):
    m=st.mean(xs); sd=st.stdev(xs); t=m/(sd/len(xs)**.5)
    print(f"{label:46s} n={len(xs):4} mean={m:+.3f}% sd={sd:5.2f} t={t:+5.2f}")

print("=== DAY-CLUSTERED: one observation per trading day ===")
print("(each day's equal-weight basket, minus the same day's equal-weight universe)\n")
rep("basket open->close, raw",           [r['b_oc'] for r in rows])
rep("universe open->close, same days",   [r['u_oc'] for r in rows])
rep("EXCESS open->close",                [r['b_oc']-r['u_oc'] for r in rows])
print()
rep("EXCESS close->close",               [r['b_cc']-r['u_cc'] for r in rows])

print("\n=== does basket size matter? (excess, open->close) ===")
for lo,hi,lab in ((1,1,'1 name  (idiosyncratic drop)'),(2,3,'2-3 names'),
                  (4,7,'4-7 names'),(8,99,'8+ names (broad selloff)')):
    g=[r['b_oc']-r['u_oc'] for r in rows if lo<=r['n']<=hi]
    if len(g)>10: rep("  "+lab,g)

print("\n=== how much did pooling legs inflate the earlier t-stat? ===")
legs=sum(r['n'] for r in rows)
print(f"name-legs pooled: {legs}   independent trading days: {len(rows)}")
print(f"average names per signal day: {legs/len(rows):.2f}")
print(f"naive-vs-clustered sqrt(n) ratio: {math.sqrt(legs/len(rows)):.2f}x")
