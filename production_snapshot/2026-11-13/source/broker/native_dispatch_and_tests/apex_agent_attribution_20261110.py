"""Read-only causal attribution of existing APEX agents against native M5 candles."""
import sqlite3,collections,datetime,statistics,sys
sys.path.insert(0,'/opt/abutron-apex11-staging/native-v4-guarded-20261108')
from abutron_replacement.bridge import AbutronApex11SignalBridge
p='/var/lib/apex/precision-history/closed-candles.sqlite3'
db=sqlite3.connect('file:'+p+'?mode=ro',uri=True)
periods={'train':('2026-11-03','2026-11-04','2026-11-05','2026-11-06'),'validation':('2026-11-07','2026-11-08'),'holdout':('2026-11-09','2026-11-10')}
facts=[]
for k in (10,25,50,75,100):
    sym=f'Volatility {k} Index.0'
    candles=list(db.execute('select start_time_utc,open,high,low,close from candles where symbol=? and timeframe=? order by start_time_utc',(sym,'M5')))
    bridge=AbutronApex11SignalBridge([dict(symbol=sym,broker='deriv',asset_class='deriv_synthetic',tick_size=.001,spread_bps=3,commission_bps=0,annual_vol=.75,max_weight=.2,timeframe_seconds=300)])
    for i,(t,o,h,l,c) in enumerate(candles):
        d=bridge.on_closed_candle(dict(symbol=sym,ts=t+300,open=o,high=h,low=l,close=c,volume=0,is_closed=True,provenance='authenticated_mt5'),observed_at=t+300)
        if i<100 or i+12>=len(candles) or (t%1800)!=0:continue
        if candles[i+1][0] != t+300 or candles[i+6][0] != t+1800:continue
        reg=d.get('regime',{}).get('regime','unknown')
        date=datetime.datetime.fromtimestamp(t,datetime.timezone.utc).strftime('%Y-%m-%d')
        exit_30=candles[i+6][4]
        entry=candles[i+1][1]
        gross_change=(exit_30-entry)/entry*1e4
        for ag in d.get('signals',[]):
            score=float(ag['score'])
            if not score:continue
            facts.append(dict(sym=k,day=date,regime=reg,agent=ag['agent'],score=score,side=1 if score>0 else -1,net5_bps=(1 if score>0 else -1)*gross_change-5,inv_net5_bps=(-1 if score>0 else 1)*gross_change-5))
        side=d.get('status')
        if side in ('BUY','SELL'):
            facts.append(dict(sym=k,day=date,regime=reg,agent='portfolio',score=float(d['target_weight_research_only']),side=1 if side=='BUY' else -1,net5_bps=(1 if side=='BUY' else -1)*gross_change-5,inv_net5_bps=(-1 if side=='BUY' else 1)*gross_change-5))
    print('REPLAY_COMPLETE',sym,'N',len(candles),'facts',len(facts),flush=True)
def stats(q,key='net5_bps'):
    xs=[z[key] for z in q]
    return (len(xs),round(statistics.mean(xs),2) if xs else None,round(sum(v>0 for v in xs)/len(xs)*100,1) if xs else None)
print('AGENT_REGIME_PERFORMANCE_BY_PERIOD',flush=True)
for agent in sorted(set(x['agent'] for x in facts)):
    for reg in sorted(set(x['regime'] for x in facts)):
        a=[x for x in facts if x['agent']==agent and x['regime']==reg]
        if len(a)<30:continue
        print('AGENT_REGIME',agent,reg,'N',len(a),[(period,stats([x for x in a if x['day'] in days])) for period,days in periods.items()],flush=True)
print('SYMBOL_AGENT_PERFORMANCE_BY_PERIOD',flush=True)
for sym in (10,25,50,75,100):
    for agent in sorted(set(x['agent'] for x in facts)):
        a=[x for x in facts if x['sym']==sym and x['agent']==agent]
        if len(a)<15:continue
        print('SYM_AGENT',sym,agent,'N',len(a),[(period,stats([x for x in a if x['day'] in days])) for period,days in periods.items()],flush=True)
