#!/usr/bin/env python3
"""Backtest behind the v3 decision (run 2026-10-05 on data/daily/closes.csv, 2025-10-01..2026-10-02).

Close-to-close, fills at the close, costs per side on traded notional (5 bp base, 15 bp stress).
Caveat: the 29-name universe was chosen in 2026 with knowledge of which names did well, so every
absolute number here is biased upward. Compare strategies against 'EW buy&hold' of the same
universe, which carries the same bias, not against zero or SPY.
"""
import csv, math, statistics as st
import os
rows=list(csv.reader(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'data','daily','closes.csv'))))
hdr=rows[0][1:]; D=[r[0] for r in rows[1:]]; P=[[float(x) for x in r[1:]] for r in rows[1:]]
S=[s for s in hdr if s!='SPY']; ix={s:i for i,s in enumerate(hdr)}
T=len(D); START=126
def ret(t,s,k): return P[t][ix[s]]/P[t-k][ix[s]]-1
def ma(t,s,k): return sum(P[t-j][ix[s]] for j in range(k))/k

def run(select, cost=0.0005, start=START, end=None, every=1):
    end=end or T-1; w={}; nav=1.0; curve=[1.0]; turn=[]; costs=0
    for t in range(start,end):
        if (t-start)%every==0:
            tgt=select(t,w)
            tw={s:1/len(tgt) for s in tgt} if tgt else {}
            # drift-adjusted current weights already in w
            to=sum(abs(tw.get(s,0)-w.get(s,0)) for s in set(tw)|set(w))
            c=to*cost; nav*=1-c; costs+=c; turn.append(to); w=tw
        r=sum(wt*(P[t+1][ix[s]]/P[t][ix[s]]-1) for s,wt in w.items())
        nav*=1+r; curve.append(nav)
        if w:  # drift weights
            g={s:wt*P[t+1][ix[s]]/P[t][ix[s]] for s,wt in w.items()}; tot=sum(g.values())+(1-sum(w.values()))
            w={s:v/tot for s,v in g.items()}
    dr=[curve[i+1]/curve[i]-1 for i in range(len(curve)-1)]
    vol=st.pstdev(dr)*math.sqrt(252); mu=st.mean(dr)*252
    pk=0;mdd=0
    for v in curve: pk=max(pk,v); mdd=min(mdd,v/pk-1)
    return dict(tot=(nav-1)*100,vol=vol*100,sharpe=mu/vol if vol else 0,mdd=mdd*100,turn=st.mean(turn)*100 if turn else 0,cost=costs*100)

def topn(score,n,buf=None,filt=None):
    def f(t,w):
        c=[s for s in S if (filt is None or filt(t,s))]
        r=sorted(c,key=lambda s:-score(t,s))
        if buf is None: return r[:n]
        keep=[s for s in w if s in r[:buf]]
        out=keep[:n]
        for s in r:
            if len(out)>=n: break
            if s not in out: out.append(s)
        return out
    return f

strats={
 'EW buy&hold (29)':      (lambda t,w: (w and list(w)) or S, 10**9),
 'SPY':                   (lambda t,w:['SPY'],10**9),
 'Mom20 top5 daily':      (topn(lambda t,s:ret(t,s,20),5),1),
 'Mom20 top5 +buffer10':  (topn(lambda t,s:ret(t,s,20),5,10),1),
 'Mom60 top5 daily':      (topn(lambda t,s:ret(t,s,60),5),1),
 'Mom60 top5 +buffer10':  (topn(lambda t,s:ret(t,s,60),5,10),1),
 'Mom126 top8 daily+buf': (topn(lambda t,s:ret(t,s,126),8,12),1),
 'Mom126 top8 monthly':   (topn(lambda t,s:ret(t,s,126),8),21),
 'Reversal5 bottom5':     (topn(lambda t,s:-ret(t,s,5),5),1),
 'Pullback-in-uptrend':   (topn(lambda t,s:-ret(t,s,3),5,filt=lambda t,s:P[t][ix[s]]>ma(t,s,50)),1),
}
mid=START+(T-1-START)//2
print(f"Test window {D[START]} -> {D[-1]} ({T-1-START} days); halves split at {D[mid]}")
print(f"{'strategy':24}{'TOT%':>8}{'VOL%':>7}{'SHRP':>6}{'MDD%':>7}{'TURN%/d':>8}{'COST%':>7} |{'H1%':>7}{'H2%':>7} |{'TOT@15bp':>9}")
for name,(fn,ev) in strats.items():
    a=run(fn,every=ev); h1=run(fn,end=mid,every=ev); h2=run(fn,start=mid,every=ev); s15=run(fn,cost=0.0015,every=ev)
    print(f"{name:24}{a['tot']:+8.1f}{a['vol']:7.1f}{a['sharpe']:6.2f}{a['mdd']:+7.1f}{a['turn']:8.1f}{a['cost']:7.2f} |{h1['tot']:+7.1f}{h2['tot']:+7.1f} |{s15['tot']:+9.1f}")

print("\n=== Robustness: full year from day 11, by quarter, vs EW buy&hold of same universe ===")
Q=[11,74,137,200,T-1]
print("quarters:"," | ".join(f"{D[Q[i]]}..{D[Q[i+1]]}" for i in range(4)))
ew=lambda t,w:(w and list(w)) or S
def line(name,fn,cost=0.0005):
    full=run(fn,cost=cost,start=11); qs=[run(fn,cost=cost,start=Q[i],end=Q[i+1])['tot'] for i in range(4)]
    print(f"{name:26}{full['tot']:+8.1f}{full['sharpe']:6.2f}{full['mdd']:+7.1f}{full['cost']:7.2f} |"+"".join(f"{q:+7.1f}" for q in qs))
print(f"{'':26}{'TOT%':>8}{'SHRP':>6}{'MDD%':>7}{'COST%':>7} |{'Q1':>7}{'Q2':>7}{'Q3':>7}{'Q4':>7}")
line('EW buy&hold',ew); line('SPY',lambda t,w:['SPY'])
for k in (3,5,10):
    for n in (3,5,8):
        line(f'Reversal {k}d bottom{n}',topn(lambda t,s,k=k:-ret(t,s,k),n))
line('Mom5 top5 (opposite)',topn(lambda t,s:ret(t,s,5),5))

print("\n=== Lookback sweep (full year, 5bp), total % ===")
print(f"{'k':>4}{'bot5':>9}{'bot8':>9}{'bot8 uptrend':>14}{'bot8 @15bp':>12}")
for k in range(2,11):
    a=run(topn(lambda t,s,k=k:-ret(t,s,k),5),start=11)['tot']
    b=run(topn(lambda t,s,k=k:-ret(t,s,k),8),start=11)['tot']
    c=run(topn(lambda t,s,k=k:-ret(t,s,k),8,filt=lambda t,s:P[t][ix[s]]>ma(t,s,50)),start=51)['tot']
    d=run(topn(lambda t,s,k=k:-ret(t,s,k),8),start=11,cost=0.0015)['tot']
    print(f"{k:>4}{a:+9.1f}{b:+9.1f}{c:+14.1f}{d:+12.1f}")

print("\n=== Ensemble candidate: score = -mean(ret over 4,5,6,7,8 days) ===")
ens=lambda t,s:-sum(ret(t,s,k) for k in (4,5,6,7,8))/5
print(f"{'':26}{'TOT%':>8}{'SHRP':>6}{'MDD%':>7}{'COST%':>7} |{'Q1':>7}{'Q2':>7}{'Q3':>7}{'Q4':>7}")
line('EW buy&hold',ew)
line('Ensemble bot8',topn(ens,8))
line('Ensemble bot8 +buf12',topn(ens,8,12))
line('Ensemble bot8 @15bp',topn(ens,8),cost=0.0015)
line('Ensemble bot8 +buf12 @15bp',topn(ens,8,12),cost=0.0015)
a=run(topn(ens,8,12),start=11); print(f"\nbuf12 avg daily turnover {a['turn']:.1f}%  vol {a['vol']:.1f}%")

def series(fn,cost=0.0005,start=START,end=None,every=1):
    end=end or T-1; w={}; out=[]
    for t in range(start,end):
        c=0
        if (t-start)%every==0:
            tgt=fn(t,w); tw={s:1/len(tgt) for s in tgt}
            c=sum(abs(tw.get(s,0)-w.get(s,0)) for s in set(tw)|set(w))*cost; w=tw
        r=sum(wt*(P[t+1][ix[s]]/P[t][ix[s]]-1) for s,wt in w.items())
        out.append((1-c)*(1+r)-1)
        g={s:wt*P[t+1][ix[s]]/P[t][ix[s]] for s,wt in w.items()}; tot=sum(g.values())
        w={s:v/tot for s,v in g.items()}
    return out
def stats(dr):
    nav=1;pk=1;mdd=0
    for r in dr: nav*=1+r; pk=max(pk,nav); mdd=min(mdd,nav/pk-1)
    vol=st.pstdev(dr)*math.sqrt(252); return (nav-1)*100, st.mean(dr)*252/vol, mdd*100, vol*100
m=series(topn(lambda t,s:ret(t,s,126),8),every=21)
r=series(topn(ens,8,12))
e=series(lambda t,w:(w and list(w)) or S, every=10**9)
n=len(m); mu=lambda x:sum(x)/len(x)
cor=sum((a-mu(m))*(b-mu(r)) for a,b in zip(m,r))/math.sqrt(sum((a-mu(m))**2 for a in m)*sum((b-mu(r))**2 for b in r))
print(f"\n=== Apr-Oct window, correlation momentum vs reversal daily returns: {cor:.2f} ===")
print(f"{'':30}{'TOT%':>8}{'SHRP':>6}{'MDD%':>7}{'VOL%':>7}")
for name,dr in [('EW buy&hold',e),('Momentum monthly (v2)',m),('Reversal daily ens+buf',r)]+[(f'Blend {int(a*100)}/{int(100-a*100)} mom/rev',[a*x+(1-a)*y for x,y in zip(m,r)]) for a in (0.3,0.5,0.7)]:
    print(f"{name:30}"+"".join(f"{v:+8.1f}" if i==0 else (f"{v:6.2f}" if i==1 else f"{v:+7.1f}" if i==2 else f"{v:7.1f}") for i,v in enumerate(stats(dr))))
