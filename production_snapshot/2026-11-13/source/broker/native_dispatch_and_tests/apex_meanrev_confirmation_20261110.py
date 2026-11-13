"""Read-only APEX mean-reversion causal confirmation study."""
import sqlite3,datetime,collections,statistics,sys
sys.path.insert(0,'/opt/abutron-apex11-staging/native-v4-guarded-20261108')
from abutron_replacement.bridge import AbutronApex11SignalBridge
db=sqlite3.connect('file:/var/lib/apex/precision-history/closed-candles.sqlite3?mode=ro',uri=True)
periods={'train':('2026-11-03','2026-11-04','2026-11-05','2026-11-06'),'validation':('2026-11-07','2026-11-08'),'holdout':('2026-11-09','2026-11-10')}
rows=[]
for k in (10,25,50,75,100):
    sym=f'Volatility {k} Index.0'
    arr=list(db.execute('select start_time_utc,open,high,low,close from candles where symbol=? and timeframe=? order by start_time_utc',(sym,'M5')))
    b=AbutronApex11SignalBridge([dict(symbol=sym,broker='deriv',asset_class='deriv_synthetic',tick_size=.001,spread_bps=3,commission_bps=0,annual_vol=.75,max_weight=.2,timeframe_seconds=300)])
    for i,(t,o,h,l,c) in enumerate(arr):
        d=b.on_closed_candle(dict(symbol=sym,ts=t+300,open=o,high=h,low=l,close=c,volume=0,is_closed=True,provenance='authenticated_mt5'),observed_at=t+300)
        if i<100 or i+12>=len(arr) or t%1800!=0:continue
        reg=d.get('regime',{}).get('regime','unknown')
        for ag in d.get('signals',[]):
            if ag['agent']!='meanrev' or not ag['score']:continue
            sign=1 if ag['score']>0 else -1
            prev=arr[i-1];prev2=arr[i-2]
            candle=sign*(c-o)>0
            delta=sign*(c-prev[4])>0
            delta2=sign*(prev[4]-prev2[4])>0
            body=abs(c-o)>0.2*(h-l)
            rejection=(sign==1 and c-l>2*(h-c)) or (sign==-1 and h-c>2*(c-l))
            # Price at next M5 open, 30-min exit: six completed bars from signal.
            gross=sign*(arr[i+6][4]-arr[i+1][1])/arr[i+1][1]*1e4
            day=datetime.datetime.fromtimestamp(t,datetime.timezone.utc).strftime('%Y-%m-%d')
            rows.append(dict(sym=k,day=day,regime=reg,sign=sign,base=gross-5,conditions=dict(candle=candle,delta=delta,delta2=delta2,body=body,rejection=rejection)))
    print('DONE',k,'records',len(rows),flush=True)
variants={
    'original': lambda x:True,
    'reversal_candle':lambda x:x['conditions']['candle'],
    'close_reverses':lambda x:x['conditions']['delta'],
    'candle_and_close_reverses':lambda x:x['conditions']['candle'] and x['conditions']['delta'],
    'confirmed_two_closes':lambda x:x['conditions']['delta'] and x['conditions']['delta2'],
    'reversal_body':lambda x:x['conditions']['candle'] and x['conditions']['body'],
    'rejection_candle':lambda x:x['conditions']['candle'] and x['conditions']['rejection'],
    'rejection_and_delta':lambda x:x['conditions']['delta'] and x['conditions']['rejection']
}
for subset_name,predicate in [('all',lambda x:True),('range',lambda x:x['regime']=='range'),('trend',lambda x:x['regime'].startswith('trend')),('V50',lambda x:x['sym']==50),('V75',lambda x:x['sym']==75)]:
    for variant,filter_fn in variants.items():
        selected=[x for x in rows if predicate(x) and filter_fn(x)]
        group=[]
        for name,dates in periods.items():
            a=[x['base'] for x in selected if x['day'] in dates]
            group.append((name,len(a),round(statistics.mean(a),2) if a else None,round(sum(a),2) if a else None))
        print('COMPARISON',subset_name,variant,group,flush=True)
