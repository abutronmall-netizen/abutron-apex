#!/usr/bin/env python3
"""ABUTRONFX APEX per-client execution preflight, DEMO-only and NON-EXECUTING.

Safety boundaries:
* NEVER uses MT5 credentials or a trading API.
* NEVER enables a trading flag, creates a cutover token or sends a broker order.
* Strict account/connection signal binding, fresh real broker feed, zero exposure,
  account-level entitlement/risk authorizations and exact no-duplicate signal key.
* Each operation is a diagnostic. All blockers are durable until verified repaired.
"""
from __future__ import annotations
import os,json,math,sqlite3,time,hashlib,tempfile
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path('/var/lib/apex-client-feed')
DB='/var/lib/apex-signup/accounts.sqlite3'
ROOT_POLICY=Path('/etc/apex/trading-policy.json')
HANDOVER=ROOT/'handover-readiness.json'
USD_PROFILE=Path('/opt/apex/runtime/APEX_DERIV_USD_PROFILE_ACTIVE_v1.json')
REPORTS=ROOT/'execution-preflight'
SYMBOLS={
 'Volatility 10 Index.0','Volatility 25 Index.0','Volatility 50 Index.0',
 'Volatility 75 Index.0','Volatility 100 Index.0','Crash 150 Index.0',
 'Crash 300 Index.0','Crash 600 Index.0','Crash 1000 Index.0',
 'Boom 150 Index.0','Boom 300 Index.0','Boom 600 Index.0','Boom 1000 Index.0'
}
def utc():return datetime.now(timezone.utc).isoformat()
def load(p):
 try:return json.loads(p.read_text())
 except (ValueError,OSError,UnicodeError):return {}
def recency(v,now,maxage=150):
 try:
  t=datetime.fromisoformat(v.replace('Z','+00:00'))
  return bool(t.tzinfo) and -15 <= now-t.timestamp() <= maxage
 except (TypeError,AttributeError,ValueError,OverflowError):return False
def posint(v):
 return type(v) in (int,float) and math.isfinite(v) and 0<v<=100
def native_bridge_proof(cid,account_login,server):
 """Verifies loaded EA within this exact isolated, authenticated MT5 session.
 Does not verify OrderCheck/OrderSend; never submits or authorizes trades.
 """
 if not isinstance(account_login,str) or not account_login or server!='Deriv-Demo':
  return False
 base=Path('/var/lib/private/abutron-client-mt5-'+cid)
 try:
  health=load(base/'worker-health.json')
  nonce=health.get('nonce')
  if not isinstance(nonce,str) or len(nonce)!=32 or any(ch not in '0123456789abcdef' for ch in nonce):
   return False
  file=base/'terminal/MQL5/Files'/('ABUTRON_APEX_BRIDGE_READY_V1_'+nonce+'.txt')
  if not file.is_file() or not 0<=time.time()-file.stat().st_mtime<=20:
   return False
  rows=file.read_text(encoding='utf-8-sig').splitlines()
  return rows[:5]==['APEX_NATIVE_BRIDGE_READY_V1',nonce,account_login,server,'DERIV_DEMO']
 except (OSError,ValueError,UnicodeError,TypeError):return False
def validate(owner,cid,broker,mode,server,status,worker,binding,licence,feed,inbox,policy,handover,now=None,bridge_ready=False,usd_profile=None):
 now=time.time() if now is None else now
 reasons=[]
 def block(why):
  if why not in reasons:reasons.append(why)
 if broker!='Deriv' or mode!='DEMO' or server!='Deriv-Demo':
  block('NOT_APPROVED_DERIV_DEMO')
 if status!='CONNECTED' or worker!='abutron-client-mt5-'+cid:
  block('NO_ISOLATED_CONNECTED_TERMINAL')
 # Preflight requires authenticated customer intent but cannot activate trading.
 # Desired ON (request) and effective OFF (no broker permission yet) are distinct.
 if binding[0]!=1:block('CUSTOMER_DEMO_ACTIVATION_NOT_REQUESTED')
 if binding[1]!=0:block('UNEXPECTED_ACTIVE_EXECUTION_DURING_PREFLIGHT')
 if not isinstance(feed,dict) or feed.get('connection_id')!=cid or feed.get('account_id')!=owner:
  block('CROSS_ACCOUNT_NATIVE_FEED')
 if feed.get('status')!='BROKER_DATA_VERIFIED_SHADOW' or feed.get('broker_data_verified') is not True:
  block('BROKER_NATIVE_MARKET_DATA_UNVERIFIED')
 if not recency(feed.get('checked_at_utc'),now):
  block('BROKER_NATIVE_FEED_STALE')
 if feed.get('symbol_count')!=13 or feed.get('timeframes_per_symbol')!=6:
  block('MARKET_DATA_UNIVERSE_INCOMPLETE')
 account=feed.get('account') if isinstance(feed.get('account'),dict) else {}
 if account.get('open_positions')!=0 or account.get('positions')!=[]:
  block('BROKER_ACCOUNT_OPEN_POSITIONS_NOT_FLAT')
 if not isinstance(inbox,dict) or inbox.get('account_id')!=owner or inbox.get('connection_id')!=cid:
  block('CROSS_ACCOUNT_APEX_SIGNAL')
 if inbox.get('status')!='RESEARCH_PREVIEW' or not recency(inbox.get('updated_at_utc'),now):
  block('NO_RECENT_APEX_SIGNAL_INBOX')
 if licence is None or licence.get('status')!='active':
  block('CLIENT_TRADING_ENTITLEMENT_NOT_ACTIVE')
 if policy.get('schema')!='apex.trading.policy.v1' or policy.get('environment')!='DERIV_DEMO' or policy.get('live_trading') is not False:
  block('ROOT_DEMO_POLICY_INVALID')
 # Fixed gross USD per-position broker stops, not percentage/daily loss limits.
 # No daily-loss cap was requested; an unbounded policy is not a safety certification.
 if policy.get('max_concurrent_positions')!=13 or policy.get('max_positions_per_symbol')!=1:
  block('RISK_CONCURRENCY_POLICY_MISMATCH')
 profile=usd_profile if isinstance(usd_profile,dict) else {}
 rows=profile.get('rows',[])
 valid_rows=(isinstance(rows,list) and len(rows)==13 and all(
    isinstance(row,list) and len(row)==4 and row[0] in SYMBOLS and
    type(row[1]) in (int,float) and math.isfinite(row[1]) and row[1]>0 and
    row[2]==50.0 and row[3]==100.0 for row in rows))
 if profile.get('status')!='ACTIVE_DERIV_DEMO_USD_GROSS' or not valid_rows or len({r[0] for r in rows})!=13:
  block('FIXED_USD_PER_TRADE_PROFILE_UNVERIFIED')
 if handover.get('status')!='APPROVED_FOR_TRADING_CUTOVER':
  block('PRODUCTION_SINGLE_WRITER_CUTOVER_LOCKED')
 if not bridge_ready:block('NATIVE_MT5_BRIDGE_NOT_LOADED_OR_STALE')
 proposed=[];seen=set()
 for x in inbox.get('candidates',[]) if isinstance(inbox.get('candidates'),list) else []:
  symbol=x.get('symbol');side=x.get('side');bar=x.get('m5_bar_time')
  if symbol not in SYMBOLS or side not in ('BUY','SELL') or type(bar)!=int:continue
  if not 0<=now-(bar+300)<=240:continue
  key=hashlib.sha256((owner+'|'+cid+'|'+symbol+'|M5|'+str(bar)+'|'+side).encode()).hexdigest()
  if key in seen: block('DUPLICATE_APEX_SIGNAL_KEY'); continue
  seen.add(key)
  if x.get('signal_key')!=key: block('APEX_SIGNAL_IDENTITY_MISMATCH');continue
  if x.get('execution_authorized') is not False or x.get('trade_ready') is not False:
   block('UNAUTHORIZED_SIGNAL_SOURCE')
   continue
  proposed.append({'symbol':symbol,'side':side,'last_closed_m5':bar,
    'signal_key':key,'execution_authorized':False})
 if not proposed:block('NO_FRESH_QUALIFIED_APEX_SIGNAL')
 # There is deliberately no broker trading path, even if no blockers remain.
 block('NATIVE_MT5_BRIDGE_EXECUTION_NOT_BROKER_TESTED')
 return {'schema':'abutron.apex.execution.preflight.v1',
 'status':'BLOCKED_NON_EXECUTING',
 'blockers':reasons,
 'eligible_candidate_count':len(proposed),
 'research_candidate_preview':proposed,
 'orders_submitted':0,'order_send_called':False,'automatic_trading_enabled':False,
 'broker_position_reconciled':account.get('open_positions')==0 and account.get('positions')==[],
 'native_bridge_loaded':bridge_ready,'native_bridge_order_execution_verified':False}
def atomic(p,doc):
 p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.preflight-')
 try:
  with os.fdopen(fd,'w') as f:
   json.dump(doc,f,separators=(',',':'),allow_nan=False)
   f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o600);os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def collect():
 policy=load(ROOT_POLICY);handover=load(HANDOVER);usd_profile=load(USD_PROFILE)
 with sqlite3.connect('file:'+DB+'?mode=ro',uri=True) as c:
  rows=c.execute('''SELECT x.id,x.account_id,x.broker,x.environment,x.broker_server,x.status,
      x.worker_binding,COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0),
      l.plan,l.status,x.account_reference
      FROM apex_mt5_connections x
      LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
      LEFT JOIN apex_crm_licenses l ON l.account_id=x.account_id
      WHERE x.status IN ('CONNECTED','CONNECTING') ORDER BY x.id''').fetchall()
 reports=[]
 for cid,owner,broker,mode,server,status,worker,desired,effective,plan,licstatus,account_login in rows:
  if len(cid)!=32 or not all(ch in '0123456789abcdef' for ch in cid):continue
  feed=load(ROOT/(cid+'.json')); inbox=load(ROOT/'inboxes'/(cid+'.json'))
  lic={'plan':plan,'status':licstatus} if licstatus else None
  ready=native_bridge_proof(cid,account_login,server)
  doc=validate(owner,cid,broker,mode,server,status,worker,(desired,effective),lic,
      feed,inbox,policy,handover,bridge_ready=ready,usd_profile=usd_profile)
  doc.update({'checked_at_utc':utc(),'connection_id':cid,
      'account_id':owner,'broker':broker,'environment':mode})
  atomic(REPORTS/(cid+'.json'),doc)
  reports.append({'connection_id':cid,'status':doc['status'],
      'blocker_count':len(doc['blockers']),'research_candidates':doc['eligible_candidate_count'],
      'native_bridge_loaded':doc['native_bridge_loaded']})
 summary={'schema':'abutron.apex.execution.preflight.summary.v1',
  'checked_at_utc':utc(),'account_count':len(reports),
  'trading_enabled':False,'orders_submitted':0,'real_broker_execution_test_passed':False,
  'native_bridges_loaded':sum(bool(x['native_bridge_loaded']) for x in reports),
  'single_writer_handover':'LOCKED','connections':reports}
 atomic(REPORTS/'summary.json',summary)
 print('CUSTOMER_EXECUTION_PREFLIGHT_COMPLETE','ACCOUNTS',len(reports),
  'REAL_ORDERS_SUBMITTED',0,'EXECUTION_DISABLED',True)
if __name__=='__main__':collect()
