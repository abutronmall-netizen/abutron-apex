#!/usr/bin/python3
"""FP Markets DEMO native-bridge readiness report. NO ORDER OR CONFIG WRITES.

Requires broker-native, account-bound proofs. Produces a fail-closed report only.
The Deriv order router and EA do not import this module.
"""
from __future__ import annotations
import datetime as dt, json, math, re, sqlite3, time
from pathlib import Path

DB=Path('/var/lib/apex-signup/accounts.sqlite3')
FP_FEED=Path('/var/lib/abutron-fpmarkets-feed')
FP_SCAN=Path('/var/lib/abutron-fp-scanner/latest.json')
FP_PARTIAL_SCAN=Path('/var/lib/abutron-fp-scanner/partial-latest.json')
FP_AI=Path('/var/lib/abutron-fp-scanner/ai/latest.json')
FP_HISTORY=Path('/var/lib/apex/operator-live/fp-native-history.json')
PRIVATE=Path('/var/lib/private')
HEX32=re.compile(r'^[0-9a-f]{32}$')
RISK_SL_USD=50.0
RISK_TP_USD=100.0
PORTFOLIO_CAP=0.20

def read(path, max_size=5_000_000):
 if path.is_symlink() or not path.is_file() or path.stat().st_size>max_size:
  raise ValueError('untrusted source')
 return json.loads(path.read_text())

def fresh(iso,now,age):
 try:
  parsed=dt.datetime.fromisoformat(iso.replace('Z','+00:00'))
  return parsed.tzinfo is not None and -15 <= now-parsed.timestamp() <= age
 except (TypeError,ValueError,AttributeError,OverflowError):
  return False

def evidence_decision(controls,feed,scanner,ai,history,bridge,now):
 """Pure decision over authenticated evidence, never returns an order request."""
 blockers=[]
 def block(cond,reason):
  if not cond:blockers.append(reason)
 block(controls.get('broker')=='FP Markets' and controls.get('environment')=='DEMO'
       and controls.get('server')=='FPMarketsSC-Demo' and controls.get('connected') is True,
       'FP_DEMO_ACCOUNT_NOT_ATTESTED')
 block(controls.get('desired') is True and controls.get('effective') is True,
       'FP_ACCOUNT_AUTOTRADING_OFF')
 block(feed.get('broker')=='FP Markets' and feed.get('native_feeds_complete')==1
       and feed.get('execution_enabled') is False and feed.get('orders_submitted')==0
       and fresh(feed.get('checked_at_utc'),now,150),
       'FP_NATIVE_MARKET_FEED_UNAVAILABLE')
 block(scanner.get('schema')=='abutron.fpmarkets.apex.scanner.readonly.v1'
       and scanner.get('symbols')==13 and scanner.get('orders_enabled') is False
       and fresh(scanner.get('checked_at_utc'),now,160),
       'FP_CLOSED_CANDLE_SCANNER_UNVERIFIED')
 proposals=[r for r in scanner.get('instruments',[]) if isinstance(r,dict)
            and r.get('proposal') in ('BUY','SELL')]
 positives=[r for r in proposals if r.get('smc',{}).get('status')=='PASS'
            and r.get('ict',{}).get('status')=='PASS']
 block(bool(positives),'NO_FRESH_SMC_AND_ICT_CONFIRMED_FP_SIGNAL')
 block(ai.get('schema')=='abutron.fpmarkets.apex.ai_smc_ict.readonly.v1'
       and ai.get('status')=='FP_AI_RESEARCH_ONLY'
       and ai.get('orders_enabled') is False
       and fresh(ai.get('reviewed_at_utc'),now,440),
       'FP_QWEN_REVIEW_UNAVAILABLE')
 # AI must match the exact broker candle and proposal, not merely agree in text.
 reviews={x['symbol']:x for x in ai.get('reviews',[])
          if isinstance(x,dict) and isinstance(x.get('symbol'),str)}
 all_three=[]
 for r in positives:
  q=reviews.get(r.get('symbol'),{})
  if q.get('m5_closed_bar')==r.get('m5_closed_bar') and q.get('scanner_proposal')==r.get('proposal') \
     and q.get('llm_direction')==r.get('proposal') \
     and q.get('evidence_status')=='MODEL_REVIEW_COMPLETED' \
     and fresh(q.get('reviewed_at_utc'),now,440):
   all_three.append(r)
 block(bool(all_three),'NO_QWEN_SMC_ICT_THREE_WAY_MATCH')
 # A data feed is not exposure reconciliation. Require MT5-native proof.
 block(history.get('available') is True and history.get('history_verified_from_mt5') is True
       and history.get('broker')=='FP Markets' and history.get('environment')=='DEMO'
       and fresh(history.get('generated_at_utc'),now,140),
       'FP_BROKER_NATIVE_POSITIONS_ORDERS_DEALS_PROOF_MISSING')
 if history.get('available') and history.get('history_verified_from_mt5'):
  positions=history.get('positions',[]);pending=history.get('pending_orders',[])
  block(isinstance(positions,list) and isinstance(pending,list),
        'FP_BROKER_EXPOSURE_FORMAT_INVALID')
  if isinstance(pending,list):block(len(pending)==0,'FP_PENDING_BROKER_ORDERS')
  if isinstance(positions,list):
   block(len(positions)<=13 and all(type(p)==dict and p.get('stop_loss')
      and p.get('take_profit') for p in positions), 'FP_POSITION_PROTECTION_UNVERIFIED')
  equity=history.get('equity_usd')
  block(type(equity) in (int,float) and math.isfinite(equity)
       and equity>0 and RISK_SL_USD+2<=equity*PORTFOLIO_CAP,
       'FP_20_PERCENT_EQUITY_CEILING_NOT_VERIFIED')
 else:
  blockers.append('FP_20_PERCENT_EQUITY_CEILING_NOT_VERIFIED')
 block(bridge.get('broker')=='FP Markets' and bridge.get('mode')=='DEMO'
       and bridge.get('account_bound') is True and bridge.get('pending_orders')==0
       and bridge.get('native_demo_orders_enabled') is True
       and bridge.get('protocol_version')==3 and bridge.get('usd_policy')==(50,100)
       and bridge.get('compiled_sha256_verified') is True
       and bridge.get('broker_ordercheck_verified') is True,
       'FP_NATIVE_ORDER_EA_AND_BROKER_ORDERCHECK_UNVERIFIED')
 # These remain hard blockers until separate broker-bound implementation and
 # single-writer transaction journal are integrated and tested.
 blockers.append('FP_BROKER_NATIVE_ORDER_ROUTER_NOT_CONNECTED')
 blockers.append('FP_BROKER_RECONCILIATION_LEDGER_NOT_CONNECTED')
 return {'schema':'abutron.fpmarkets.execution.preflight.v1',
         'status':'BLOCKED' if blockers else 'READY',
         'broker':'FP Markets','environment':'DEMO','orders_enabled':False,
         'trade_attempts':0,'stop_loss_gross_usd':RISK_SL_USD,
         'take_profit_gross_usd':RISK_TP_USD,'portfolio_ceiling_pct':20,
         'scanner_candidates':len(proposals),'smc_ict_positive':len(positives),
         'ai_smc_ict_positive':len(all_three),'blockers':blockers}

def inspect(now=None):
 now=time.time() if now is None else now
 try:
  with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=7) as c:
   c.execute('PRAGMA query_only=ON')
   records=c.execute('''SELECT x.id,x.broker,x.environment,x.broker_server,x.status,
       coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
       FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t ON x.id=t.connection_id
       WHERE x.broker='FP Markets' AND x.environment='DEMO' AND x.status='CONNECTED' ''').fetchall()
  if len(records)!=1:raise ValueError('FP_CONNECTED_DEMO_ACCOUNT_NOT_UNIQUE')
  cid,broker,env,server,status,desired,effective=records[0]
  if not HEX32.fullmatch(cid):raise ValueError('FP_INVALID_ACCOUNT_FINGERPRINT')
  controls={'broker':broker,'environment':env,'server':server,'connected':status=='CONNECTED',
            'desired':bool(desired),'effective':bool(effective)}
  # No MT5 commands are created; identity and source location are fixed.
  w=read(PRIVATE/('abutron-client-mt5-'+cid)/'worker-health.json',30000)
  if w.get('id')!=cid or w.get('status')!='CONNECTED' or w.get('broker')!='FP Markets':
   raise ValueError('FP_WORKER_IDENTITY_UNVERIFIED')
  f=read(FP_FEED/'summary.json')
  partial=False
  try:
   native=read(FP_FEED/'market'/(cid+'.json'))
  except (OSError,ValueError,UnicodeError):
   native=read(FP_FEED/'partial'/(cid+'.json'))
   partial=True
  source='FP Markets DEMO MT5 native' if partial else 'FP Markets DEMO MT5'
  if (native.get('source')!=source or native.get('connection_id')!=cid or
      native.get('broker_server')!='FPMarketsSC-Demo' or
      native.get('account_mode')!='DEMO' or
      native.get('execution_enabled') is not False or
      native.get('orders_submitted')!=0 or
      not fresh(native.get('checked_at_utc'),now,150)):
   raise ValueError('FP_CONTRACT_SOURCE_UNTRUSTED')
  market_map=native.get('mapping',{})
  if (not isinstance(market_map,dict) or len(market_map)!=13 or
      any(not isinstance(v,dict) or v.get('status')!='MAPPED'
          for v in market_map.values())):
   raise ValueError('FP_CONTRACT_SYMBOLS_UNVERIFIED')
  disabled=[k for k,v in market_map.items() if v.get('trade_mode')!=4]
  if partial:
   if native.get('schema')!='abutron.fpmarkets.native.partial.readonly.v1' or native.get('status')!='PARTIAL_NOT_CERTIFIED':
    raise ValueError('FP_PARTIAL_FEED_SCHEMA_INVALID')
   quotes=native.get('quotes',{});bars=native.get('bars',{})
   if not isinstance(quotes,dict) or not isinstance(bars,dict) or set(quotes)!=set(bars) or not set(quotes)<=set(market_map):
    raise ValueError('FP_PARTIAL_QUOTES_BARS_INCONSISTENT')
   verified=sorted(quotes)
   unavailable=sorted(set(market_map)-set(quotes))
   if not verified or not unavailable:
    raise ValueError('FP_PARTIAL_COVERAGE_STATUS_INVALID')
   s=read(FP_PARTIAL_SCAN)
   if (s.get('schema')!='abutron.fpmarkets.apex.scanner.partial.readonly.v1' or
       s.get('status')!='FP_SCANNER_PARTIAL_READONLY' or
       s.get('symbols_verified')!=len(verified) or
       sorted(s.get('symbols_unavailable',[]))!=unavailable or
       s.get('orders_enabled') is not False or
       s.get('execution_authorized') is not False or
       s.get('native_market_at_utc')!=native.get('checked_at_utc')):
    raise ValueError('FP_PARTIAL_SCANNER_SOURCE_MISMATCH')
  else:
   verified=sorted(market_map)
   unavailable=[]
   s=read(FP_SCAN)
  a=read(FP_AI)
  try:h=read(FP_HISTORY)
  except (OSError,ValueError,UnicodeError):h={}
  bridge={}
  report=evidence_decision(controls,f,s,a,h,bridge,now)
  report['symbols_trade_mode_full']=13-len(disabled)
  report['symbols_trade_mode_disabled_at_snapshot']=sorted(disabled)
  report['native_feed_quality']='PARTIAL' if partial else 'COMPLETE'
  report['symbols_with_verified_candles']=len(verified)
  report['unavailable_symbols']=unavailable
  report['broker_native_history_verified']=bool(h.get('history_verified_from_mt5'))
  report['broker_pending_orders']=h.get('pending_orders_count')
  report['broker_open_positions']=h.get('open_positions_count')
  report['checked_at_utc']=dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat()
  return report
 except (OSError,ValueError,TypeError,KeyError,sqlite3.Error) as e:
  return {'schema':'abutron.fpmarkets.execution.preflight.v1',
   'status':'BLOCKED','orders_enabled':False,'trade_attempts':0,
   'blockers':['FP_PREFLIGHT_SOURCE_UNVERIFIED_'+type(e).__name__]}

if __name__=='__main__':
 print(json.dumps(inspect(),indent=2,sort_keys=True))
