#!/usr/bin/python3
"""ABUTRON V75 research-only comparison: strict HTF vs pre-registered H1-pullback alternative.
Point-in-time closed candles; no MT5 orders, risk configuration, or trading switch changes.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import importlib.util,json,math,statistics,os,tempfile

REPLAY=Path('/opt/apex-client-mt5/quant-first/abutron_quant_replay_v1.py')
SCANNER=Path('/opt/apex/runtime/apex_fast_scanner.py')
SYMBOL='Volatility 75 Index.0'
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,str(path))
 if spec is None or spec.loader is None:raise ValueError('CODE_UNVERIFIED')
 mod=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(mod)
 return mod
replay=load('v75_asof_replay',REPLAY)
apex=load('v75_original_scanner',SCANNER)

def check_closed_bar_state(state,anchor=None):
    if set(state)!=set(replay.FRAMES):raise ValueError('MISSING_TIMEFRAME_SOURCE')
    for tf,seconds in replay.FRAMES.items():
        rows=state[tf]
        if len(rows)<65:raise ValueError('INSUFFICIENT_FRAME_COVERAGE')
        prev=0
        for bar in rows:
            t=bar.get('time')
            if type(t) is not int or t<=prev:
                raise ValueError('UNTRUSTED_BAR_TIMESTAMPS')
            if anchor is not None and t+seconds>anchor:
                raise ValueError('LOOKAHEAD_BAR_IN_CANDIDATE')
            prices=[bar.get(k) for k in ('open','high','low','close')]
            if not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in prices):
                raise ValueError('INVALID_BROKER_PRICE')
            o,h,l,c=prices
            if h<max(o,c) or l>min(o,c):
                raise ValueError('INVALID_CANDLE_RANGE')
            prev=t

def experimental(state,anchor=None):
    """Keep original qualifying signals; permit only M15+H4-aligned H1 pullbacks
    with *stricter* M5 body, close/EMA9 distance, RSI and volatility evidence.
    Never used as an actual order source.
    """
    check_closed_bar_state(state,anchor)
    baseline=apex.evaluate(SYMBOL,state)
    if baseline['proposal'] in ('BUY','SELL'):
        return baseline['proposal'],'ORIGINAL_STRICT_PASS'
    indicators=baseline['indicators']
    m5,m15,h1,h4=[indicators[k] for k in ('M5','M15','H1','H4')]
    side=baseline['m5_signal']
    if side not in ('BUY','SELL'):return 'HOLD','M5_MIXED'
    want='UP' if side=='BUY' else 'DOWN'
    if m15['trend']!=want or h4['trend']!=want:return 'HOLD','M15_H4_DISAGREE'
    if h1['trend']==want:return 'HOLD','BASELINE_ENTRY_QUALITY_REJECTED'
    if h1['trend'] not in ('UP','DOWN'):return 'HOLD','H1_MIXED'
    if m5['atr14']<=0 or m5['close']<=0:return 'HOLD','NO_VALID_ATR'
    if side=='BUY' and not 55<=m5['rsi14']<=66:return 'HOLD','PULLBACK_RSI_NOT_STRONG'
    if side=='SELL' and not 34<=m5['rsi14']<=45:return 'HOLD','PULLBACK_RSI_NOT_STRONG'
    latest=state['M5'][-1]
    atr=m5['atr14']
    body=abs(float(latest['close'])-float(latest['open']))/atr
    distance=abs(m5['close']-m5['ema9'])/atr
    if body<0.50:return 'HOLD','PULLBACK_WEAK_BODY'
    if distance>0.50:return 'HOLD','PULLBACK_OVEREXTENDED'
    if apex.m5_entry_quality(latest,m5,side)!='PASS':return 'HOLD','M5_CANDLE_CONFIRMATION_FAIL'
    return side,'H1_PULLBACK_RESEARCH_ONLY'

def run():
    proof=replay.verify_history_current()
    data=replay.load_market(replay.DB,SYMBOL)
    m5=data['M5']; n=len(m5)
    if n<900:raise ValueError('BROKER_HISTORY_TOO_SHORT')
    if any(b['time']-a['time']!=300 for a,b in zip(m5[:-1],m5[1:])):
        raise ValueError('BROKER_M5_HISTORY_HAS_GAPS')
    normal=[];trial=[];extra=[]
    reasons=Counter();v75_asof_checked=0;first=None
    for idx in range(80,n-replay.HOLD_BARS):
        state,anchor=replay.history_asof(data,idx)
        if min(len(state[tf]) for tf in replay.FRAMES)<65:continue
        if first is None:first=idx
        for tf,seconds in replay.FRAMES.items():
            if state[tf] and state[tf][-1]['time']+seconds>anchor:
                raise ValueError('LOOKAHEAD_DETECTED')
        standard=apex.evaluate(SYMBOL,state)
        changed,reason=experimental(state,anchor)
        if standard['proposal'] in ('BUY','SELL'):normal.append((idx,standard['proposal']))
        if changed in ('BUY','SELL'):trial.append((idx,changed))
        if reason=='H1_PULLBACK_RESEARCH_ONLY':
            extra.append((idx,changed))
        reasons[reason]+=1;v75_asof_checked+=1
    if first is None or v75_asof_checked<100:
        raise ValueError('INSUFFICIENT_SIX_FRAME_COVERAGE')
    end=n-replay.HOLD_BARS
    cut1=first+int((end-first)*.60);cut2=first+int((end-first)*.80)
    segments={'development':(first,cut1),'validation':(cut1,cut2),'untouched_holdout':(cut2,end)}
    results={}
    for name,candidate in [('existing_strict_apex',normal),('h1_pullback_research_candidate',trial),('new_h1_conflict_entries_only',extra)]:
        by_period={}
        for k,(lo,hi) in segments.items():
            trades=replay.select_trades(candidate,m5,lo,hi)
            info=replay.score(trades)
            # These frictions are scenario stress tests only, NOT sourced broker costs.
            vals=[r['gross_directional_move_bps'] for r in trades]
            info['hypothetical_bps_friction_5_mean']=round(statistics.mean(vals)-5,4) if vals else None
            info['hypothetical_bps_friction_10_mean']=round(statistics.mean(vals)-10,4) if vals else None
            info['instrument_net_expectancy_verified']=False
            by_period[k]=info
        results[name]={'raw_signal_candles':len(candidate),'segments':by_period}
    return {
      'schema':'abutron.apex.v75.h1_pullback_lab.readonly.v1',
      'verified_at_utc':datetime.now(timezone.utc).isoformat(),
      'mode':'SHADOW_RESEARCH_ONLY',
      'broker_source':'Deriv DEMO point-in-time precision-history candles',
      'source_integrity':proof,
      'symbol':SYMBOL,
      'm5_history_bars':n,
      'asof_scanned_bars':v75_asof_checked,
      'method':'Strict APEX versus a pre-specified H1-conflict research alternative; next M5 open to 3rd M5 close, nonoverlapping signals',
      'candidate_rule':'M5/M15/H4 direction aligned, H1 contrary, RSI BUY 55-66 or SELL 34-45, M5 body >=0.5 ATR, extension <=0.5 ATR, original candle quality pass',
      'costs':'UNVERIFIED; 5/10 bps figures are hypothetical stress only',
      'risk_policy_changed':False,'trading_switches_changed':False,
      'orders_enabled':False,'execution_authorized':False,
      'verified_net_profitable_edge':False,
      'eligible_for_execution':False,
      'needs_more_broker_forward_data':True,
      'observations_by_rule':dict(reasons),
      'strategies':results
    }
if __name__=='__main__':
 print(json.dumps(run(),sort_keys=True))
