#!/usr/bin/env python3
"""ABUTRON read-only broker-candle cost/risk research, never broker execution."""
import argparse,bisect,datetime,json,math,multiprocessing,os,sqlite3,statistics,sys,hashlib
from pathlib import Path
sys.path[:0]=['/opt/apex/runtime','/opt/apex-client-mt5/quant-first']
import apex_fast_scanner as fast
import abutron_quant_first_v1 as quant
TF={'M5':300,'M15':900,'H1':3600,'H4':14400}
HORIZON=12
SYMBOLS=sorted(quant.DERIV_SCOPE)
STRATEGIES=('apex','strict','m15_h1_pullback','quant')
DB=None

def candle_bars(symbol):
    data={};ends={}
    with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True) as c:
        c.execute('PRAGMA query_only=ON')
        for tf,period in TF.items():
            items=c.execute('select start_time_utc,open,high,low,close from candles where symbol=? and timeframe=? order by start_time_utc',(symbol,tf)).fetchall()
            if len(items)<500: raise ValueError('INSUFFICIENT_NATIVE_HISTORY')
            data[tf]=[dict(time=t,open=o,high=h,low=l,close=cl) for t,o,h,l,cl in items]
            last=0
            for r in data[tf]:
                t=r['time']
                if type(t)!=int or t<=last or t%period or not all(math.isfinite(r[k]) and r[k]>0 for k in ('open','high','low','close')) or r['low']>min(r['open'],r['close']) or r['high']<max(r['open'],r['close']):
                    raise ValueError('INVALID_BROKER_OHLC_OR_TIME')
                last=t
            ends[tf]=[r['time']+period for r in data[tf]]
    return data,ends

def point_in_time(data,ends,anchor):
    ans={}
    for tf in TF:
        n=bisect.bisect_right(ends[tf],anchor)
        if n<160:return None
        ans[tf]=data[tf][n-160:n]
        if ans[tf][-1]['time']+TF[tf]>anchor:raise ValueError('LOOKAHEAD')
    return ans

def strict_quality(frames,state,side):
    if side not in ('BUY','SELL'):return False
    bar=frames['M5'][-1]
    a=state['atr14'];lo=bar['low'];hi=bar['high'];o=bar['open'];cl=bar['close']
    if a<=0 or hi<=lo or abs(cl-state['ema9'])>0.45*a or abs(cl-o)<0.45*a:return False
    loc=(cl-lo)/(hi-lo);rsi=state['rsi14']
    if side=='BUY':return cl>o and loc>=0.70 and 55<=rsi<=65
    return cl<o and loc<=0.30 and 35<=rsi<=45

def stop_first(m5,i,side,atr,horizon=HORIZON):
    """Next-open entry, 1.2 ATR stop, 1.8 ATR target, SL first if both touched."""
    if side not in ('BUY','SELL') or not math.isfinite(atr) or atr<=0 or i<0 or i+horizon>=len(m5):return None
    for j in range(i+1,i+horizon+1):
        if m5[j]['time']!=m5[i]['time']+300*(j-i):return None
    entry=m5[i+1]['open'];sgn=1 if side=='BUY' else -1
    stop=entry-sgn*1.2*atr;target=entry+sgn*1.8*atr
    if min(stop,target)<=0:return None
    exit_price=m5[i+horizon]['close'];reason='TIME'
    for j in range(i+1,i+horizon+1):
        b=m5[j];o=b['open'];hi=b['high'];lo=b['low']
        if side=='BUY':
            if o<=stop:exit_price=min(o,stop);reason='STOP_GAP';break
            if o>=target:exit_price=target;reason='TP';break
            if lo<=stop:exit_price=stop;reason='STOP';break
            if hi>=target:exit_price=target;reason='TP';break
        else:
            if o>=stop:exit_price=max(o,stop);reason='STOP_GAP';break
            if o<=target:exit_price=target;reason='TP';break
            if hi>=stop:exit_price=stop;reason='STOP';break
            if lo<=target:exit_price=target;reason='TP';break
    return {'gross_bps':sgn*10000*math.log(exit_price/entry),'exit_reason':reason}

def summary(trades):
    vals=[r['gross_bps'] for r in trades];n=len(vals)
    result={'n':n,'wins_gross':sum(v>0 for v in vals),'gross_mean_bps':round(statistics.mean(vals),3) if n else None,'stops':sum(r['exit_reason'].startswith('STOP') for r in trades),'hypothetical_cost_scenarios':{}}
    for fee in (5,10,20):
        net=[v-fee for v in vals];key=str(fee)
        if n:
            avg=statistics.mean(net);stderr=statistics.stdev(net)/math.sqrt(n) if n>1 else None
            equity=peak=dd=0
            for v in net:
                equity+=v;peak=max(peak,equity);dd=max(dd,peak-equity)
            result['hypothetical_cost_scenarios'][key]={'mean_net_bps':round(avg,3),'lower_95_normal_approx_bps':round(avg-1.96*stderr,3) if stderr is not None else None,'maximum_sequential_drawdown_bps':round(dd,3)}
        else:result['hypothetical_cost_scenarios'][key]={'mean_net_bps':None,'lower_95_normal_approx_bps':None,'maximum_sequential_drawdown_bps':None}
    return result

def one_symbol(args):
    global DB
    sym,path,step=args;DB=Path(path)
    fast.FRAMES=tuple(TF) # Changes worker process only, never importer's scanner.
    data,ends=candle_bars(sym);m5=data['M5'];first=160;last=len(m5)-HORIZON-1
    splits=(first,first+int((last-first)*.6),first+int((last-first)*.8),last)
    names=('development','validation','previously_seen_holdout')
    trades={k:{s:[] for s in STRATEGIES} for k in names};next_allowed={k:{s:-1 for s in STRATEGIES} for k in names}
    checked=gaps=0
    for i in range(first,last,step):
        anchor=m5[i]['time']+300;frames=point_in_time(data,ends,anchor)
        if frames is None or frames['M5'][-1]['time']!=m5[i]['time']:continue
        if m5[i+1]['time']!=anchor:gaps+=1;continue
        checked+=1
        base=fast.evaluate(sym,frames)['proposal']
        q=quant.assess(sym,frames,'Deriv',now=anchor+5)['research_bias']
        i5=fast.frame_state(frames['M5']);i15=fast.frame_state(frames['M15']);i1=fast.frame_state(frames['H1'])
        m5side={'UP':'BUY','DOWN':'SELL'}.get(i5['trend'],'HOLD')
        mild=(m5side!='HOLD' and i15['trend']==i1['trend']==('UP' if m5side=='BUY' else 'DOWN') and strict_quality(frames,i5,m5side))
        choices={'apex':base,'strict':base if strict_quality(frames,i5,base) else 'HOLD','m15_h1_pullback':m5side if mild else 'HOLD','quant':q}
        seg=next((name for name,a,b in zip(names,splits,splits[1:]) if a<=i<b),None)
        if seg is None:continue
        for model,side in choices.items():
            if side not in ('BUY','SELL') or i<next_allowed[seg][model]:continue
            outcome=stop_first(m5,i,side,i5['atr14'])
            if outcome is None:gaps+=1;continue
            trades[seg][model].append(outcome);next_allowed[seg][model]=i+HORIZON
    print('SYMBOL_FINISHED',sym,'scanned',checked,'path_gaps',gaps,flush=True)
    return sym,{'m5_history':len(m5),'decisions_scanned':checked,'gaps_rejected':gaps,'segments':{part:{model:summary(v) for model,v in rec.items()} for part,rec in trades.items()}}

def run(db,out,source_sha,step=6,workers=2):
    db=Path(db);out=Path(out)
    if db.is_symlink() or not db.is_file() or out.exists():raise ValueError('UNSAFE_DB_OR_OUTPUT')
    with db.open('rb') as h:digest=hashlib.file_digest(h,'sha256').hexdigest()
    if source_sha and digest!=source_sha:raise ValueError('BROKER_DATA_HASH_MISMATCH')
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as conn:
        if conn.execute('pragma quick_check').fetchone()[0]!='ok' or conn.execute('select count(*) from candles').fetchone()[0]<300000:raise ValueError('BROKER_DATA_INVALID')
    with multiprocessing.Pool(workers) as pool:results=dict(pool.map(one_symbol,[(s,str(db),step) for s in SYMBOLS]))
    payload={'schema':'abutron.quant.risk_aware.replay.v2','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':'READONLY_RESEARCH_ONLY','source_sha256':digest,'data':'AUTHENTICATED_DERIV_DEMO_COMPLETED_OHLC','entry':'NEXT_M5_OPEN_NOT_BROKER_FILL','stop':'1.2_ATR_FIRST_IF_BOTH_TOUCH','take_profit':'1.8_ATR','maximum_duration_m5_bars':HORIZON,'previously_seen_holdout':True,'commission_spread_slippage_are_assumed_not_verified':True,'cost_scenarios_bps':[5,10,20],'risk_governance':'HOLD_ALL_PROMOTIONS_UNTIL_FORWARD_REAL_COST_PROOF','orders_submitted':0,'execution_authorized':False,'positions_changed':False,'symbols':results}
    fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(payload,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    return payload

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--db',required=True);p.add_argument('--out',required=True);p.add_argument('--expected-sha256')
    p.add_argument('--step',type=int,choices=(3,6,12),default=6)
    p.add_argument('--workers',type=int,choices=(1,2),default=2)
    a=p.parse_args()
    z=run(a.db,a.out,a.expected_sha256,a.step,a.workers)
    print('REPORT_SAVED',a.out)
    for sym,d in z['symbols'].items():
        for name,detail in d['segments']['previously_seen_holdout'].items():
            v=detail['hypothetical_cost_scenarios']['20']
            print('HOLDOUT',sym,name,'n',detail['n'],'net20bps_mean',v['mean_net_bps'],'lower95',v['lower_95_normal_approx_bps'])
