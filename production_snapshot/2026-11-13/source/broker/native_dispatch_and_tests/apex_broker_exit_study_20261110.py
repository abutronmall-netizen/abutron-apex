"""Retrospective time-exit study on actual broker closed positions; never sends orders."""
import sqlite3,csv,glob,os,collections,datetime,statistics,bisect,math
brok=max(glob.glob('/var/lib/private/abutron-native-readonly-mt5-6207/terminal/MQL5/Files/ABUTRON_NATIVE_ALLTIME_V1_*.tsv'),key=os.path.getmtime)
by=collections.defaultdict(list)
for x in csv.DictReader(open(brok).read().splitlines()[9:],delimiter='\t'):
    try:
        x['ts']=int(x['time_utc'])
        x['net']=sum(float(x[k]) for k in ('profit','commission','fee','swap'))
        x['gross']=float(x['profit'])
    except (ValueError,TypeError):continue
    if x['position_id'] not in ('','0'):by[x['position_id']].append(x)
db=sqlite3.connect('file:/var/lib/apex/precision-history/closed-candles.sqlite3?mode=ro',uri=True)
prices={}
for sym, in db.execute('select distinct symbol from candles where timeframe=?',('M1',)):
    a=list(db.execute('select start_time_utc,close from candles where symbol=? and timeframe=? order by start_time_utc',(sym,'M1')))
    prices[sym]=({t:p for t,p in a},[t for t,p in a])
periods={'train':('2026-11-03','2026-11-04','2026-11-05','2026-11-06'),'validation':('2026-11-07','2026-11-08'),'holdout':('2026-11-09','2026-11-10')}
records=[]
for pid,ds in by.items():
    ds.sort(key=lambda x:x['ts'])
    entry=next((d for d in ds if d['entry'] in ('0','2')),None)
    exits=[x for x in ds if x['entry'] in ('1','2','3')]
    if entry is None or not exits:continue
    exit=exits[-1]
    if exit['ts']<=entry['ts'] or entry['symbol'] not in prices:continue
    gross=sum(d['gross'] for d in ds)
    actual=sum(d['net'] for d in ds)
    direction=1 if entry['type']=='0' else -1
    delta=direction*(float(exit['price'])-float(entry['price']))
    if abs(delta)<1e-9 or gross/delta<=0:continue
    price_per_usd=gross/delta
    expected={}
    for h in (15,30,45,60,90,120):
        if entry['ts']+h*60>=exit['ts']:
            expected[h]=actual;continue
        t=(entry['ts']+h*60)//60*60
        mark=prices[entry['symbol']][0].get(t)
        if mark is None:continue
        # Same already-broker-charged costs, but additional close slippage not modeled.
        expected[h]=direction*(mark-float(entry['price']))*price_per_usd+sum(d['net']-d['gross'] for d in ds)
    day=datetime.datetime.fromtimestamp(entry['ts'],datetime.timezone.utc).strftime('%Y-%m-%d')
    records.append((pid,entry['symbol'],day,actual,expected,entry['ts'],exit['ts']))
print('REAL_CLOSED_POSITIONS',len(records),'ACTUAL_NET',round(sum(a[3] for a in records),2))
for name,days in periods.items():
    sub=[a for a in records if a[2] in days]
    print('PERIOD',name,'N',len(sub),'REAL_NET',round(sum(a[3] for a in sub),2))
    for h in (15,30,45,60,90,120):
        usable=[a for a in sub if h in a[4]]
        delta=[a[4][h]-a[3] for a in usable]
        if not delta:continue
        print('EXIT',h,'N',len(usable),'ACTUAL',round(sum(a[3] for a in usable),2),'HYPOTHETICAL',round(sum(a[4][h] for a in usable),2),'IMPROVEMENT',round(sum(delta),2),'BETTER',sum(x>0 for x in delta))
