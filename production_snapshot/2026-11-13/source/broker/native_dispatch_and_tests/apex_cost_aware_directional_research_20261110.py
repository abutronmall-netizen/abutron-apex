"""Read-only causal ridge regression on existing M5 OHLC; no live orders, no new service."""
import sqlite3,numpy as np,datetime,collections,math
db=sqlite3.connect('file:/var/lib/apex/precision-history/closed-candles.sqlite3?mode=ro',uri=True)
symnames=[f'Volatility {s} Index.0' for s in (10,25,50,75,100)]
universe=[]
def moving(x,n):
    return np.convolve(x,np.ones(n)/n,mode='valid')
def ewma(x,n):
    a=2/(n+1);r=np.zeros_like(x);r[0]=x[0]
    for j in range(1,len(x)):r[j]=a*x[j]+(1-a)*r[j-1]
    return r
for sidx,s in enumerate(symnames):
    a=np.array(list(db.execute('select start_time_utc,open,high,low,close from candles where symbol=? and timeframe=? order by start_time_utc',(s,'M5'))),dtype=float)
    t=a[:,0].astype(np.int64);o,h,l,c=(a[:,i] for i in range(1,5))
    tr=np.maximum(h-l,np.maximum(np.abs(h-np.roll(c,1)),np.abs(l-np.roll(c,1))));tr[0]=h[0]-l[0]
    atr=np.zeros(len(t))
    for i in range(len(t)):
        atr[i]=np.mean(tr[max(0,i-13):i+1])
    e20=ewma(c,20);e55=ewma(c,55)
    for i in range(110,len(t)-18):
        if t[i+7]-t[i]!=2100:continue
        scale=max(atr[i],1.e-10)
        feat=[1.]
        for lag in (1,3,6,12,24,48):
            feat.append(float(np.clip((c[i]-c[i-lag])/scale,-12,12)))
        feat.extend([float(np.clip((e20[i]-e55[i])/scale,-8,8)),
                     float(np.clip((c[i]-e20[i])/scale,-8,8)),
                     float(np.clip((c[i]-np.mean(c[i-39:i+1]))/scale,-8,8)),
                     float(np.clip((c[i]-o[i])/scale,-8,8)),
                     float(np.clip((h[i]-max(o[i],c[i]))/scale,0,8)),
                     float(np.clip((min(o[i],c[i])-l[i])/scale,0,8)),
                     float((c[i]-np.min(l[i-19:i+1]))/max(np.max(h[i-19:i+1])-np.min(l[i-19:i+1]),1e-10)),
                     float(np.clip(atr[i]/max(np.mean(atr[max(0,i-39):i+1]),1e-8),0,5)),
                     float(np.clip(np.std(np.diff(c[i-12:i+1]))/max(np.std(np.diff(c[i-48:i+1])),1e-8),0,5))])
        y=float((c[i+6]-o[i+1])/o[i+1]*1e4)
        day=datetime.datetime.fromtimestamp(int(t[i]),datetime.timezone.utc).strftime('%Y-%m-%d')
        universe.append((sidx,int(t[i]),day,np.array(feat,dtype=float),y))
    print('BUILT',s,'events',sum(z[0]==sidx for z in universe),flush=True)
F=np.stack([a[3] for a in universe]);Y=np.array([a[4] for a in universe]);sids=np.array([a[0] for a in universe]);days=np.array([a[2] for a in universe]);ts=np.array([a[1] for a in universe])
# Train observed outcomes only until 6 November, select model and entry threshold on 7-8 November, final independent holdout 9-10.
train=np.isin(days,['2026-11-03','2026-11-04','2026-11-05','2026-11-06'])
val=np.isin(days,['2026-11-07','2026-11-08'])
hold=np.isin(days,['2026-11-09','2026-11-10'])
mu=np.mean(F[train,1:],axis=0);std=np.std(F[train,1:],axis=0);std[std<1e-6]=1
X=np.concatenate([np.ones((len(F),1)),np.clip((F[:,1:]-mu)/std,-6,6)],axis=1)
def fit(alpha,per_symbol=False):
    # L2, intercept unpenalized; per-symbol independent models use same features.
    if per_symbol:
        pred=np.zeros(len(Y))
        for sym in range(5):
            idx=train&(sids==sym)
            Z=X[idx]; y=Y[idx];reg=np.eye(X.shape[1])*alpha;reg[0,0]=0
            coef=np.linalg.solve(Z.T@Z+reg,Z.T@y)
            q=sids==sym
            pred[q]=X[q]@coef
        return pred
    Z=X[train];y=Y[train];reg=np.eye(X.shape[1])*alpha;reg[0,0]=0
    coef=np.linalg.solve(Z.T@Z+reg,Z.T@y)
    return X@coef
def assess(pred,mask,cut,mode='both',cost=5):
    # At most one position per symbol every 30 minutes; use next-bar entry,
    # observed 30-minute later close, cost only modeled as sensitivity.
    idx=np.where(mask)[0]
    idx=sorted(idx,key=lambda i:ts[i])
    next_open={}
    ret=[]
    for i in idx:
        s=int(sids[i]);v=pred[i]
        if ts[i]<next_open.get(s,0):continue
        sign=1 if v>cut else -1 if v<-cut else 0
        if mode=='buy' and sign<0:sign=0
        if mode=='sell' and sign>0:sign=0
        if not sign:continue
        ret.append((s,sign*Y[i]-cost,ts[i],float(v)))
        next_open[s]=ts[i]+1800
    return ret
candidates=[]
for alpha in (1.,10.,100.,1000.,10000.):
 for per in (False,True):
  pred=fit(alpha,per)
  for cutoff in (0,5,10,15,20,30,40):
   for mode in ('both','buy','sell'):
    a=assess(pred,val,cutoff,mode)
    if len(a)<40:continue
    avg=sum(z[1] for z in a)/len(a)
    candidates.append((avg,len(a),alpha,per,cutoff,mode,pred))
print('N_CANDIDATES',len(candidates),flush=True)
for avg,n,alpha,per,cut,mode,pred in sorted(candidates,key=lambda x:x[0],reverse=True)[:15]:
 def metrics(mask):
  q=assess(pred,mask,cut,mode)
  return dict(n=len(q),mean_net5_bps=round(sum(z[1] for z in q)/len(q),2) if q else None,net5_bps=round(sum(z[1] for z in q),1),wins=sum(z[1]>0 for z in q))
 print('VALIDATION_SELECTED',dict(alpha=alpha,per_symbol=per,threshold_bps=cut,mode=mode,train=metrics(train),validation=metrics(val),holdout=metrics(hold)),flush=True)
