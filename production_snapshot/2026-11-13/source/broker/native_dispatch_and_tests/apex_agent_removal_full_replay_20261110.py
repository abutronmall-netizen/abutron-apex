"""Read-only APEX 1.1 baseline-vs-existing-agent edit, M5/M15/H1 and M1 exit evidence."""
import sqlite3,sys,collections,datetime,statistics
sys.path.insert(0,'/opt/abutron-apex11-staging/native-v4-guarded-20261108')
from abutron_replacement.bridge import AbutronApex11SignalBridge
db=sqlite3.connect('file:/var/lib/apex/precision-history/closed-candles.sqlite3?mode=ro',uri=True)
PERIODS={'train':('2026-11-03','2026-11-04','2026-11-05','2026-11-06'),'validation':('2026-11-07','2026-11-08'),'holdout':('2026-11-09','2026-11-10')}
RESULT=[]
for k in (50,75):
 sym=f'Volatility {k} Index.0'
 a={}
 for tf in ('M1','M5','M15','H1'):
  a[tf]=list(db.execute('select start_time_utc,open,high,low,close from candles where symbol=? and timeframe=? order by start_time_utc',(sym,tf)))
 m1={int(r[0]):r for r in a['M1']}
 m5=a['M5'];atr=[]
 tr=[]
 for i,(t,o,h,l,c) in enumerate(m5):
  last=m5[max(0,i-1)][4]
  tr.append(max(h-l,abs(h-last),abs(l-last)))
  atr.append(sum(tr[max(0,i-13):i+1])/min(i+1,14))
 higher={}
 for tf,step in (('M15',900),('H1',3600)):
  higher[tf]=[dict(symbol=sym,ts=int(t+step),open=o,high=h,low=l,close=c,volume=0,is_closed=True,provenance='authenticated_mt5') for t,o,h,l,c in a[tf]]
 for variant in ('baseline','without_meanrev'):
  b=AbutronApex11SignalBridge([dict(symbol=sym,broker='deriv',asset_class='deriv_synthetic',tick_size=.001,spread_bps=3,commission_bps=0,annual_vol=.75,max_weight=.2,timeframe_seconds=300)])
  if variant=='without_meanrev':
   b.engine.signal_agents=[agent for agent in b.engine.signal_agents if agent.name!='meanrev']
  idx={'M15':0,'H1':0};last_exit=-1;trades=[]
  for i,(t,o,h,l,c) in enumerate(m5):
   close=int(t+300);contexts={}
   for tf,step in (('M15',900),('H1',3600)):
    hs=higher[tf]
    while idx[tf]<len(hs) and hs[idx[tf]]['ts']<=close:idx[tf]+=1
    contexts[tf]=hs[max(0,idx[tf]-3):idx[tf]]
   d=b.on_closed_candle(dict(symbol=sym,ts=close,open=o,high=h,low=l,close=c,volume=0,is_closed=True,provenance='authenticated_mt5'),observed_at=close,higher_timeframes=contexts)
   if i<110 or i>=len(m5)-7 or i<=last_exit:continue
   side=d['status']
   if side not in ('BUY','SELL'):continue
   sign=1 if side=='BUY' else -1
   if m5[i+1][0]!=t+300:continue
   entry=float(m5[i+1][1]);stopdist=1.5*atr[i]
   stop=entry-sign*stopdist;target=entry+sign*2*stopdist;outcome=None;exit_i=None
   for minute in range(30):
    candle=m1.get(int(t+300+minute*60))
    if candle is None:break
    hit_stop=(candle[3]<=stop if sign==1 else candle[2]>=stop)
    hit_take=(candle[2]>=target if sign==1 else candle[3]<=target)
    if hit_stop:ex=stop;reason='stop'
    elif hit_take:ex=target;reason='target'
    elif minute==29:ex=candle[4];reason='time'
    else:continue
    outcome=sign*(ex-entry)/entry*1e4-5
    exit_i=i+1+minute//5
    break
   if outcome is None:continue
   last_exit=exit_i
   day=datetime.datetime.fromtimestamp(t,datetime.timezone.utc).strftime('%Y-%m-%d')
   trades.append((day,outcome,reason))
  RESULT.extend((k,variant,*trade) for trade in trades)
  print('SCENARIO_COMPLETED',k,variant,len(trades),flush=True)
for k in (50,75):
 for variant in ('baseline','without_meanrev'):
  print('SUMMARY',k,variant)
  for name,days in PERIODS.items():
   q=[x[3] for x in RESULT if x[0]==k and x[1]==variant and x[2] in days]
   if not q:print(name,'NONE');continue
   print(name,'n',len(q),'avg_net_5bps',round(statistics.mean(q),2),'net_total_bps',round(sum(q),2),'wins',sum(x>0 for x in q),'net_10bps',round(statistics.mean(q)-5,2))
