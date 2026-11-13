"""OFFLINE research only: immutable broker-imported M5 and M1; no order API."""
import sqlite3,collections,datetime,statistics,math
DB='/var/lib/apex/precision-history/closed-candles.sqlite3'
c=sqlite3.connect('file:'+DB+'?mode=ro',uri=True)
symbols=[f'Volatility {n} Index.0' for n in (10,25,50,75,100)]
def ema(xs,n):
    a=2/(n+1);v=xs[0];out=[]
    for x in xs:
        v+=a*(x-v);out.append(v)
    return out
def avg(xs,n):
    q=collections.deque();out=[];total=0.
    for x in xs:
        q.append(x);total+=x
        if len(q)>n:total-=q.popleft()
        out.append(total/len(q))
    return out
data={}
for sym in symbols:
    tmp={}
    for tf in ('M1','M5','M15','H1'):
        tmp[tf]=list(c.execute('select start_time_utc,open,high,low,close from candles where symbol=? and timeframe=? order by start_time_utc',(sym,tf)))
    t=tmp['M5'];n=len(t)
    closes=[x[4] for x in t];highs=[x[2] for x in t];lows=[x[3] for x in t]
    e20=ema(closes,20);e55=ema(closes,55);ma40=avg(closes,40)
    tr=[highs[0]-lows[0]]+[max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1])) for i in range(1,n)]
    atr=avg(tr,14)
    stamps={tf:{x[0]:x for x in tmp[tf]} for tf in ('M1','M15','H1')}
    data[sym]=(t,stamps,closes,highs,lows,e20,e55,ma40,atr)
    print('LOADED',sym,'M5',n,'M1',len(tmp['M1']),flush=True)
def direction(stamps,decision_close,tf,step):
    # Use 3 consecutive completed TF candles before M5 signal's bar close.
    last=(decision_close//step)*step-step
    a=stamps[tf].get(last-2*step);b=stamps[tf].get(last)
    if a is None or b is None:return 0
    return 1 if b[4]>a[1] else -1 if b[4]<a[1] else 0
def candidates(sym,variant):
    t,st,c,h,l,e20,e55,m40,atr=data[sym]
    result=[]
    for i in range(90,len(t)-22):
        if t[i+1][0]-t[i][0]!=300:continue
        trend=1 if e20[i]>e55[i] else -1
        side=0
        if variant=='trend_pullback':
            if trend==1 and l[i]<e20[i] and c[i]>e20[i] and c[i]>t[i][1]:side=1
            if trend==-1 and h[i]>e20[i] and c[i]<e20[i] and c[i]<t[i][1]:side=-1
        elif variant=='breakout20':
            if trend==1 and c[i]>max(h[i-20:i])+0.15*atr[i]:side=1
            if trend==-1 and c[i]<min(l[i-20:i])-0.15*atr[i]:side=-1
        elif variant=='breakout55':
            if trend==1 and c[i]>max(h[i-55:i])+0.20*atr[i]:side=1
            if trend==-1 and c[i]<min(l[i-55:i])-0.20*atr[i]:side=-1
        elif variant=='meanrev_confirm':
            if c[i]<m40[i]-1.6*atr[i] and c[i]>t[i][1] and c[i]>c[i-1]:side=1
            if c[i]>m40[i]+1.6*atr[i] and c[i]<t[i][1] and c[i]<c[i-1]:side=-1
        elif variant=='meanrev_deep':
            if c[i]<m40[i]-2.2*atr[i] and c[i]>t[i][1]:side=1
            if c[i]>m40[i]+2.2*atr[i] and c[i]<t[i][1]:side=-1
        elif variant=='ema_cross':
            if e20[i]>e55[i] and e20[i-1]<=e55[i-1]:side=1
            if e20[i]<e55[i] and e20[i-1]>=e55[i-1]:side=-1
        elif variant=='strong_momentum':
            if trend==1 and c[i]>h[i-1] and c[i]>t[i][1] and c[i-1]>t[i-1][1] and c[i]-e20[i]<1.4*atr[i]:side=1
            if trend==-1 and c[i]<l[i-1] and c[i]<t[i][1] and c[i-1]<t[i-1][1] and e20[i]-c[i]<1.4*atr[i]:side=-1
        elif variant=='range_fade':
            if abs(e20[i]-e55[i])<0.5*atr[i]:
                if c[i]<m40[i]-1.4*atr[i] and c[i]>t[i][1]:side=1
                if c[i]>m40[i]+1.4*atr[i] and c[i]<t[i][1]:side=-1
        if not side:continue
        mtf15=direction(st,t[i][0]+300,'M15',900)
        mtfH1=direction(st,t[i][0]+300,'H1',3600)
        result.append((i,side,mtf15,mtfH1))
    return result
def evaluate(sym,items,filtermode,rr,maximum_minutes,cost_bps=5):
    t,st,c,h,l,e20,e55,m40,atr=data[sym]
    last_exit=-1;returns=[]
    for i,side,m15,h1 in items:
        if i<=last_exit:continue
        if filtermode=='both' and not (m15==h1==side):continue
        if filtermode=='at_least_one' and side not in (m15,h1):continue
        if filtermode=='no_opposition' and m15==h1==-side:continue
        entry_idx=i+1
        if t[entry_idx][0]-t[i][0]!=300:continue
        entry=t[entry_idx][1]
        stop_dist=1.5*atr[i]
        if stop_dist<=0:continue
        stop=entry-side*stop_dist;target=entry+side*rr*stop_dist
        result=None;ex_idx=None
        for minute in range(maximum_minutes):
            ts=t[entry_idx][0]+minute*60
            candle=st['M1'].get(ts)
            if candle is None:break
            hitstop=(candle[3]<=stop) if side==1 else (candle[2]>=stop)
            hittarget=(candle[2]>=target) if side==1 else (candle[3]<=target)
            if hitstop:
                exitprice=stop;reason='stop'
            elif hittarget:
                exitprice=target;reason='target'
            elif minute==maximum_minutes-1:
                exitprice=candle[4];reason='time'
            else:continue
            result=side*(exitprice-entry)/entry*10000-cost_bps
            ex_idx=entry_idx+minute//5
            break
        if result is None:continue
        last_exit=ex_idx
        day=datetime.datetime.fromtimestamp(t[i][0],datetime.timezone.utc).strftime('%Y-%m-%d')
        returns.append((day,result,reason))
    return returns
periods={'train':('2026-11-03','2026-11-04','2026-11-05','2026-11-06'),'validation':('2026-11-07','2026-11-08'),'holdout':('2026-11-09','2026-11-10')}
variants=('trend_pullback','breakout20','breakout55','meanrev_confirm','meanrev_deep','ema_cross','strong_momentum','range_fade')
filters=('none','both','at_least_one','no_opposition')
records={}
for variant in variants:
    cache={sym:candidates(sym,variant) for sym in symbols}
    for filt in filters:
        for rr in (1.5,2.0):
            for duration in (30,60,90):
                key=(variant,filt,rr,duration)
                results=[]
                for sym in symbols:
                    for day,ret,reason in evaluate(sym,cache[sym],filt,rr,duration):
                        results.append((day,ret,reason,sym))
                records[key]=results
    print('SCANNED',variant,flush=True)
def stats(vals,costdelta=0):
    a=[v[1]-costdelta for v in vals]
    return (len(a),round(statistics.mean(a),2) if a else None,round(sum(a),2) if a else None,round(sum(x>0 for x in a)/len(a)*100,1) if a else None)
eligible=[]
for key,rows in records.items():
    groups={k:[r for r in rows if r[0] in days] for k,days in periods.items()}
    a,b,h=(stats(groups[x]) for x in ('train','validation','holdout'))
    if all(x[0]>=12 and x[1]>0 for x in (a,b,h)):
        eligible.append((key,a,b,h))
print('EVALUATED',len(records),'ELIGIBLE_POSITIVE_ALL_PERIODS',len(eligible),flush=True)
for x in sorted(eligible,key=lambda z:z[3][1],reverse=True)[:20]:print('ELIGIBLE',x,flush=True)
ranking=[]
for k,rows in records.items():
    a,b,h=(stats([v for v in rows if v[0] in periods[x]]) for x in ('train','validation','holdout'))
    if b[0]>=12 and h[0]>=12:
        ranking.append((b[1],k,a,b,h))
for x in sorted(ranking,reverse=True)[:15]:
    print('TOP_BY_VALIDATION',x,flush=True)
print('EXTRA_COST_STRESS_TEST',flush=True)
for _,key,a,b,h in sorted(ranking,reverse=True)[:5]:
    rows=records[key];print('STRESS',key,[(x,stats([v for v in rows if v[0] in days],5)) for x,days in periods.items()],flush=True)
