#!/usr/bin/python3
"""Authenticated FP Markets partial research; never authorizes orders."""
import datetime as dt,hashlib,importlib.util,json,time
from pathlib import Path
CID='35b81a287b6a030f2f46ff426b135e6c'
SOURCE=Path('/var/lib/abutron-fpmarkets-feed/partial')/(CID+'.json')
SUMMARY=Path('/var/lib/abutron-fpmarkets-feed/summary.json')
BASE='/opt/apex-client-mt5/fpmarkets-scanner/fp_apex_readonly_scanner.py'
FRAMES=('M1','M5','M15','H1','H4','D1')
QUALITY_GATE=Path('/opt/apex-client-mt5/fpmarkets-research-partial/fp_entry_quality_gate_v1.py')
def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,str(path))
 x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x);return x
def build():
 f=load_module('fp_original_scanner',BASE)
 now=time.time();d=f.read(SOURCE);summary=f.read(SUMMARY,300000)
 syms=f.universe()
 f.verify(d.get('schema')=='abutron.fpmarkets.native.partial.readonly.v1' and
  d.get('status')=='PARTIAL_NOT_CERTIFIED' and
  d.get('source')=='FP Markets DEMO MT5 native' and
  d.get('account_mode')=='DEMO' and d.get('broker_server')=='FPMarketsSC-Demo' and
  d.get('connection_id')==CID and d.get('execution_enabled') is False and
  d.get('orders_submitted')==0,'FP_PARTIAL_NATIVE_IDENTITY_INVALID')
 f.verify(-30<=now-f.timestamp(d['checked_at_utc'])<=130,'FP_PARTIAL_SNAPSHOT_STALE')
 f.verify(d.get('timeframes')==list(FRAMES),'FP_FRAMES_UNVERIFIED')
 f.verify(summary.get('schema')=='abutron.fpmarkets.feed.readonly.v1' and
  summary.get('orders_submitted')==0 and summary.get('execution_enabled') is False and
  -30<=now-f.timestamp(summary['checked_at_utc'])<=130,'FP_COLLECTOR_STALE')
 connected=[x for x in summary.get('connections',[]) if x.get('connection_id')==CID]
 f.verify(len(connected)==1 and connected[0].get('status') in ('BROKER_NATIVE_DATA_PARTIAL','BROKER_NATIVE_DATA_COMPLETE') and
  connected[0].get('execution_enabled') is False and connected[0].get('orders_submitted')==0,
  'FP_PARTIAL_SESSION_MISMATCH')
 f.verify(f.account_check(d,now=now)==CID,'FP_ACCOUNT_HEARTBEAT_INVALID')
 mapping=d.get('mapping');quotes=d.get('quotes');bars=d.get('bars')
 f.verify(isinstance(mapping,dict) and set(mapping)==set(syms) and
  isinstance(quotes,dict) and isinstance(bars,dict) and set(quotes)==set(bars),
  'FP_PARTIAL_UNIVERSE_INVALID')
 fast=f.module('fp_original_fast_for_partial',str(f.FAS))
 smc=f.module('fp_original_smc_for_partial',str(f.SMC))
 quality=load_module('fp_native_entry_quality_v1',QUALITY_GATE)
 rows=[];verified=[];missing=[]
 for sym in syms:
  m=mapping[sym]
  f.verify(isinstance(m,dict) and m.get('status') in ('MAPPED','MISSING','AMBIGUOUS'),
   'FP_PARTIAL_SYMBOL_STATUS_INVALID')
  family=('Metal' if sym=='XAUUSD' else 'Crypto' if sym=='BTCUSD' else
   'Commodity' if sym=='USOIL' else 'Index' if sym in ('US100','US30','SP500','GER40') else 'Forex')
  if m['status']!='MAPPED' or sym not in bars:
   f.verify(sym not in bars and sym not in quotes and
    ((m['status']!='MAPPED' and not m.get('actual')) or
     (m['status']=='MAPPED' and m.get('actual') in syms[sym])),
    'FP_UNAVAILABLE_SYMBOL_HAS_UNVERIFIED_DATA')
   missing.append(sym)
   unavailable_status=('BARS_PENDING' if m['status']=='MAPPED' else m['status'])
   rows.append({'symbol':sym,'broker':'FP Markets','family':family,
    'available':False,'broker_status':unavailable_status,'proposal':'HOLD',
    'reason':'FP_BROKER_SYMBOL_'+unavailable_status+'_NO_VERIFIED_CANDLES',
    'm5_closed_bar':None,'indicators':{},'m5_direction':'HOLD',
    'higher_timeframe_direction':'UNAVAILABLE',
    'smc':{'status':'VETO','score':0,'reasons':['BROKER_SYMBOL_UNAVAILABLE']},
    'ict':{'status':'VETO'},'ai':{'status':'UNAVAILABLE','direction':None},
    'final_decision':'HOLD','candidate_for_ai':False,'requires_ai_and_smc_and_ict':True,
    'orders_enabled':False,'execution_authorized':False})
   continue
  f.verify(m.get('actual') in syms[sym] and sym in bars and sym in quotes,
   'FP_BROKER_ALIAS_NOT_ATTESTED')
  q=quotes[sym]
  f.verify(q.get('symbol')==m['actual'] and type(q.get('time')) is int and
    -30<=now-q['time']<=300 and q.get('broker_clock_offset_seconds')==7200 and
    all(fast.finite(q.get(k)) for k in ('bid','ask')) and
    0<q['bid']<=q['ask'],'FP_NATIVE_QUOTE_INVALID')
  frames=bars[sym]
  f.verify(isinstance(frames,dict) and set(frames)==set(FRAMES),'FP_NATIVE_FRAMESET_INVALID')
  # One session-closed broker symbol must not abort fresh signals in 12 others.
  # Never pass its stale candles to an order-producing signal.
  if any((not isinstance(frames.get(tf),list) or not frames[tf] or
          now-frames[tf][-1].get('time',0)>900)
         for tf in ('M1','M5')):
   missing.append(sym)
   rows.append({'symbol':sym,'broker':'FP Markets','family':family,
    'available':False,'broker_status':'STALE_NATIVE_SESSION',
    'proposal':'HOLD','reason':'FP_BROKER_CLOSED_BAR_STALE',
    'm5_closed_bar':None,'indicators':{},'m5_direction':'HOLD',
    'higher_timeframe_direction':'UNAVAILABLE',
    'smc':{'status':'REMOVED'},'ict':{'status':'REMOVED'},
    'ai':{'status':'NOT_REQUIRED','direction':None},'final_decision':'HOLD',
    'candidate_for_ai':False,'requires_ai_and_smc_and_ict':False,
    'orders_enabled':False,'execution_authorized':False})
   continue
  for tf in FRAMES:
   f.verify(isinstance(frames[tf],list) and len(frames[tf])>=60,'FP_NATIVE_BARS_MISSING')
   smc.validate_bars(frames[tf],tf,now=now,enforce_freshness=True)
  assessment=f.assess(sym,frames,fast,smc)
  raw_proposal=assessment.get('proposal')
  quality_status,measurements=quality.gate(assessment,frames,q)
  assessment['original_scanner_proposal']=raw_proposal
  assessment['entry_quality']={'status':quality_status,'metrics':measurements,
      'version':quality.VERSION,'order_authority':False}
  if raw_proposal in ('BUY','SELL') and quality_status!='PASS':
   assessment['proposal']='HOLD'
   assessment['reason']='ENTRY_QUALITY_'+quality_status
   assessment['candidate_for_ai']=False
  assessment.update({'available':True,'family':family,'broker_status':'MAPPED'})
  rows.append(assessment);verified.append(sym)
 f.verify(len(rows)==13 and len(verified)<=len(quotes)==len(bars) and
   len(verified)+len(missing)==13 and d.get('symbol_count')==len(bars) and
   len(verified)*6<=connected[0].get('timeframes_verified',0) and
   len(verified)<=connected[0].get('fresh_quotes',0),
   'FP_PARTIAL_COVERAGE_INCONSISTENT')
 return {'schema':'abutron.fpmarkets.apex.scanner.partial.readonly.v1',
  'status':'FP_SCANNER_PARTIAL_READONLY',
  'checked_at_utc':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
  'source':'FP Markets DEMO MT5 native completed candles',
  'account_fingerprint':hashlib.sha256(CID.encode()).hexdigest()[:24],
  'native_market_at_utc':d['checked_at_utc'],'broker':'FP Markets',
  'symbols':13,'symbols_verified':len(verified),'symbols_unavailable':missing,
  'timeframe_series':len(verified)*6,
  'scanner_proposals':sum(x['proposal']!='HOLD' for x in rows),
  'smc_ict_passed':0,
  'original_apex_candidates':sum(x['proposal'] in ('BUY','SELL') for x in rows),
  'policy':'PARTIAL_RESEARCH_NOT_CERTIFIED_NO_TRADES','orders_enabled':False,
  'execution_authorized':False,'account_controls_modified':False,
  'final_decisions':{'HOLD':13},'instruments':rows}
if __name__=='__main__':
 d=build()
 print(json.dumps({'status':d['status'],'verified':d['symbols_verified'],
   'unavailable':d['symbols_unavailable'],'proposals':d['scanner_proposals'],
   'orders_enabled':d['orders_enabled']}))

