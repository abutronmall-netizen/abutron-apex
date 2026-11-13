#!/usr/bin/env python3
"""ABUTRON broker-cost entry research V1. READ ONLY. No MT5 order capability.
Uses historically completed Deriv DEMO OHLC, observed round-trip commissions,
snapshot spread and OrderCalcProfit conversion. Slippage is scenario-stressed;
actual historical spread/slippage and broker fills are NOT verified.
"""
from __future__ import annotations
import bisect,collections,datetime as dt,hashlib,json,math,os,sqlite3,statistics,sys,time
from pathlib import Path

DB=Path('/var/backups/abutron-signal-repair-20261106T2155Z/broker_long_candles.sqlite3')
COST=Path('/var/backups/abutron-cost-research-20261106T2235Z/BROKER_COST_REFERENCE_EQUITY_V2.json')
OUTPUT=Path('/var/backups/abutron-cost-research-20261106T2235Z/ENTRY_MODEL_WALKFORWARD_V1.json')
STRATEGIES=('trend_pullback','failed_breakout','ema_reversion','range_sweep','trend_breakout','streak_fade')
HOLD=12
PERCENTILES=(.60,.80,1.)
MIN_EVALUATION=30

def data(symbol,source=DB):
    rows={}
    with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as c:
        c.execute('pragma query_only=on')
        for tf in ('M5','H1'):
            period=300 if tf=='M5' else 3600
            a=c.execute('select start_time_utc,open,high,low,close from candles where symbol=? and timeframe=? order by start_time_utc',(symbol,tf)).fetchall()
            if len(a)<1000:raise ValueError('INSUFFICIENT_REAL_BROKER_BARS')
            last=0
            for row in a:
                t,o,h,l,cl=row
                if t<=last or t%period or not all(math.isfinite(z) and z>0 for z in (o,h,l,cl)) or l>min(o,cl) or h<max(o,cl):
                    raise ValueError('BROKER_BARS_INVALID_OR_NONMONOTONIC')
                last=t
            rows[tf]=a
    return rows

def h1_regime(bars):
    t=[];trend=[]
    e8=e21=bars[0][4]
    for j,(stamp,o,hi,lo,close) in enumerate(bars):
        e8+=(close-e8)*2/9
        e21+=(close-e21)*2/22
        t.append(stamp+3600)
        trend.append(1 if j>=30 and e8>e21 else -1 if j>=30 and e8<e21 else 0)
    return t,trend

def features(bars):
    """One-pass M5 completed-candle EMA / Wilder ATR + RSI, no future data."""
    c0=bars[0][4];e9=e21=e55=c0
    atr=0.;g=0.;l=0.
    out=[]
    for i,(t,o,hi,lo,c) in enumerate(bars):
        prev=bars[i-1][4] if i else c
        tr=max(hi-lo,abs(hi-prev),abs(lo-prev))
        gain=max(0,c-prev);loss=max(0,prev-c)
        e9+=(c-e9)*.2
        e21+=(c-e21)*2/22
        e55+=(c-e55)*2/56
        if i<14:
            atr+=tr/14;g+=gain/14;l+=loss/14
        else:
            atr=(atr*13+tr)/14;g=(g*13+gain)/14;l=(l*13+loss)/14
        rsi=100 if l==0 and g>0 else 50 if l==0 else 100-100/(1+g/l)
        out.append((e9,e21,e55,atr,rsi))
    return out

def decide(i,bars,vals,h1):
    """Six fixed, preregistered candidate ideas; no optimization on holdout."""
    t,o,hi,lo,c=bars[i]
    e9,e21,e55,atr,rsi=vals[i]
    prev=bars[i-1];cprev=prev[4]
    if atr<=0 or i<60:return {}
    range20=bars[i-20:i]
    top=max(x[2] for x in range20);bottom=min(x[3] for x in range20)
    length=hi-lo;body=abs(c-o)
    upper=hi-max(o,c);lower=min(o,c)-lo
    side={}
    # A: trend-following entry after price crosses EMA9 within a controlled pullback.
    if e21>e55 and h1==1 and cprev<e9 and c>e9 and c>o and body>.20*atr and 50<=rsi<=63 and c-e9<.55*atr:
        side['trend_pullback']='BUY'
    elif e21<e55 and h1==-1 and cprev>e9 and c<e9 and c<o and body>.20*atr and 37<=rsi<=50 and e9-c<.55*atr:
        side['trend_pullback']='SELL'
    # B: wick sweep of previous twenty candles followed by close inside prior range.
    if lo<bottom and c>bottom and c>o and lower>.5*atr and rsi<42 and h1>=0:
        side['failed_breakout']='BUY'
    elif hi>top and c<top and c<o and upper>.5*atr and rsi>58 and h1<=0:
        side['failed_breakout']='SELL'
    # C: pronounced EMA21 extension with reversal candle confirmation.
    if c<e21-1.3*atr and c>o and rsi<=34 and h1>=0:
        side['ema_reversion']='BUY'
    elif c>e21+1.3*atr and c<o and rsi>=66 and h1<=0:
        side['ema_reversion']='SELL'
    # D: prior-20-bar rejection, no strict H1 trend veto.
    if lo<bottom and length>0 and (c-lo)/length>=.75 and c>o and rsi<47:
        side['range_sweep']='BUY'
    elif hi>top and length>0 and (c-lo)/length<=.25 and c<o and rsi>53:
        side['range_sweep']='SELL'
    # E: 20-bar directional break with EMA regime.
    if c>top and e9>e21>e55 and h1==1 and c>o and .40*atr<=body<=1.50*atr and 55<=rsi<=72:
        side['trend_breakout']='BUY'
    elif c<bottom and e9<e21<e55 and h1==-1 and c<o and .40*atr<=body<=1.50*atr and 28<=rsi<=45:
        side['trend_breakout']='SELL'
    # F: four-candle momentum exhaustion followed by a confirming opposite candle.
    past=bars[i-4:i];previous_down=all(x[4]<x[1] for x in past)
    previous_up=all(x[4]>x[1] for x in past)
    run=cprev-past[0][1]
    if previous_down and run<=-1.5*atr and c>o and body>=.3*atr and rsi<45:
        side['streak_fade']='BUY'
    elif previous_up and run>=1.5*atr and c<o and body>=.3*atr and rsi>55:
        side['streak_fade']='SELL'
    return side

def price_outcome(bars,i,side,atr,stopfloor,hold=HOLD):
    """Broker-minimum stop, next bar entry, conservative SL-first candle evaluation."""
    if side not in ('BUY','SELL') or not math.isfinite(atr) or atr<=0 or i+hold>=len(bars):return None
    for j in range(i+1,i+hold+1):
        if bars[j][0]!=bars[i][0]+(j-i)*300:return None
    entry=bars[i+1][1]
    minstop=max(stopfloor,0)
    stopdist=max(1.2*atr,minstop*1.02)
    targetdist=max(1.8*atr,minstop*1.02)
    # Exclude setups where the broker's hard stop floor overwhelms the ATR risk envelope.
    if stopdist>3.5*atr:return None
    sign=1 if side=='BUY' else -1
    stop=entry-sign*stopdist;target=entry+sign*targetdist
    if stop<=0 or target<=0:return None
    exit_price=bars[i+hold][4];reason='TIME'
    for j in range(i+1,i+hold+1):
        t,o,hi,lo,c=bars[j]
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
    return {'gross_bps':sign*10000*(exit_price-entry)/entry,
            'risk_price':stopdist,'reason':reason,'entry':entry,'exit':exit_price}

def score(trades,comm_per_lot,contract):
    n=len(trades)
    result={'trades':n,'wins_gross':sum(x['gross_bps']>0 for x in trades),
            'stops':sum(x['reason'].startswith('STOP') for x in trades),
            'cost_scenarios':{}}
    for slippage in (5.,10.,20.):
        net=[x['gross_bps']-(comm_per_lot/(x['entry']*contract)*10000)-slippage for x in trades]
        mean=statistics.mean(net) if n else None
        se=statistics.stdev(net)/math.sqrt(n) if n>1 else None
        eq=peak=dd=0.
        for v in net:
            eq+=v;peak=max(peak,eq);dd=max(dd,peak-eq)
        result['cost_scenarios'][str(int(slippage))]={
            'mean_net_bps':round(mean,4) if mean is not None else None,
            'normal_95_lower_bps':round(mean-1.96*se,4) if se is not None else None,
            'gross_independent_trade_assumption':False,
            'sequential_drawdown_bps':round(dd,4),
            'percent_net_wins':round(sum(z>0 for z in net)/n*100,2) if n else None}
    return result

def analyze(symbol,costs,source=DB):
    raw=data(symbol,source);m5=raw['M5'];h1_t,h1_dir=h1_regime(raw['H1']);state=features(m5)
    start=170;end=len(m5)-HOLD-1
    split=[start,start+int((end-start)*.60),start+int((end-start)*.80),end]
    segnames=('development','validation','previously_inspected_holdout')
    buckets={p:{name:[] for name in STRATEGIES} for p in segnames}
    cooldown={p:{name:-1 for name in STRATEGIES} for p in segnames}
    filters=collections.Counter()
    last_h1=0;h1_idx=-1
    for i in range(start,end):
        anchor=m5[i][0]+300
        while h1_idx+1<len(h1_t) and h1_t[h1_idx+1]<=anchor:h1_idx+=1
        if h1_idx<30:continue
        part=next((p for p,a,b in zip(segnames,split,split[1:]) if a<=i<b),None)
        if part is None or i+HOLD>=split[segnames.index(part)+1]:continue
        # Never consume an unclosed H1 bar.
        assert h1_t[h1_idx]<=anchor
        suggestions=decide(i,m5,state,h1_dir[h1_idx])
        for model,side in suggestions.items():
            if i<cooldown[part][model]:continue
            outcome=price_outcome(m5,i,side,state[i][3],costs['minimum_broker_stop_price_distance'])
            if outcome is None:filters['BROKER_STOP_FLOOR_OR_GAP_EXCLUSION']+=1;continue
            equity=costs['research_reference_equity_usd'];minvol=costs['minimum_volume'];unit=costs['ordercalcprofit_usd_per_price_point_per_lot']
            minrisk=outcome['risk_price']*minvol*unit
            if minrisk>equity*.001:
                filters['MIN_LOT_EXCEEDS_POINT_ONE_PERCENT_EQUITY']+=1;continue
            buckets[part][model].append(outcome)
            cooldown[part][model]=i+HOLD
    result={p:{s:score(v,costs['commission_usd_roundtrip_per_lot_median'],costs['ordercalcprofit_usd_per_price_point_per_lot']) for s,v in sub.items()} for p,sub in buckets.items()}
    return {'symbol':symbol,'M5_history_count':len(m5),'H1_history_count':len(raw['H1']),
            'filter_rejections':dict(filters),'entry_models':result}

def main():
    assert DB.is_file() and COST.is_file() and not DB.is_symlink() and not OUTPUT.exists()
    with DB.open('rb') as f:datasetsha=hashlib.file_digest(f,'sha256').hexdigest()
    with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True) as c:
        assert c.execute('pragma quick_check').fetchone()[0]=='ok'
        assert c.execute('select count(*) from candles').fetchone()[0]==446000
    costs=json.loads(COST.read_text())
    assert costs['schema']=='abutron.deriv.authenticated.broker.cost.contract.v2'
    results={}
    for symbol,item in sorted(costs['instruments'].items()):
        x=analyze(symbol,{**item,'research_reference_equity_usd':costs['research_reference_equity_usd']})
        results[symbol]=x
        print('COMPLETED_SYMBOL',symbol,'DEVELOPMENT_N',[x['entry_models']['development'][n]['trades'] for n in STRATEGIES],
              'VALIDATION_N',[x['entry_models']['validation'][n]['trades'] for n in STRATEGIES],flush=True)
    eligible=[]
    for symbol,x in results.items():
        for name in STRATEGIES:
            dev=x['entry_models']['development'][name]
            val=x['entry_models']['validation'][name]
            qd=dev['cost_scenarios']['10'];qv=val['cost_scenarios']['10']
            # A positive result is NOT sufficient: forward evidence + true slippage proof required.
            if dev['trades']>=40 and val['trades']>=30 and qd['normal_95_lower_bps'] is not None and qv['normal_95_lower_bps'] is not None and qd['normal_95_lower_bps']>0 and qv['normal_95_lower_bps']>0:
                eligible.append({'symbol':symbol,'model':name,'validation_n':val['trades'],
                                 'validation_lower_bps':qv['normal_95_lower_bps']})
    payload={'schema':'abutron.quant.broker_cost_aware.models.v1',
      'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
      'mode':'READONLY_PRECOMMITTED_STRATEGY_COMPARISON',
      'm5_input_sha256':datasetsha,
      'cost_proof_sha256':hashlib.sha256(COST.read_bytes()).hexdigest(),
      'method':'CHRONOLOGICAL_60_20_20, original holdout inspected previously, never truly untouched',
      'cost':{'broker_commissions':'AUTHENTICATED_DEAL_MEDIANS',
        'displayed_spread':'ONE_CURRENT_SNAPSHOT_ZERO_NOT_HISTORICAL',
        'slippage_stress_bps':[5,10,20],
        'broker_stop_min':'CURRENT_NATIVE_MQL5_SYMBOL_TRADE_STOPS_LEVEL',
        'actual_execution_slippage_unverified':True,
        'estimated_equity_for_min_volume_viability':costs['research_reference_equity_usd']},
      'position_and_orders_modified':False,'order_authority':False,
      'candidates_pass_positive_development_and_validation':eligible,
      'profitability_proven':False,'forward_outcomes_verified':False,
      'broker_acked_protected_trade_from_this_model':False,
      'instruments':results}
    fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(payload,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    print('COMPLETED_REPORT',OUTPUT)
    print('POSITIVE_AFTER_COST_DEVELOPMENT_AND_VALIDATION',eligible)
    for sym,x in results.items():
        for name in STRATEGIES:
            v=x['entry_models']['validation'][name]
            if v['trades']>=30:
                net=v['cost_scenarios']['10']
                print('VALIDATION',sym,name,'N',v['trades'],'MEAN',net['mean_net_bps'],'LOWER95',net['normal_95_lower_bps'])
if __name__=='__main__':main()
