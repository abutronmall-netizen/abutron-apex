#!/usr/bin/python3
"""FP Markets 1622 DEMO native execution authorization acknowledgment.
No broker order functions. Account-specific; must never authorize LIVE.
Customer DEMO ON request, active license seat, verified native risk controls,
and configured single-writer are ALL required. Never sets desired_enabled=1.
"""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
import time

sys.path[:0]=['/opt/apex-client-portal','/opt/apex-signup']
import apex_crm_license_policy as license_policy
CID='14eef404262094655b2040c8ced86a53'
FP0512_CID='35b81a287b6a030f2f46ff426b135e6c'
DB=Path('/var/lib/apex-signup/accounts.sqlite3')
WORKER=Path('/var/lib/private/abutron-client-mt5-'+CID)
FILES=WORKER/'terminal/MQL5/Files'
HISTORY=Path('/var/lib/apex/operator-live/fp-native-history-account-14eef404262094655b2040c8ced86a53.json')
RECON=Path('/var/lib/abutron-fp-execution/1622/reconciliation/latest.json')
FEED=Path('/var/lib/abutron-fpmarkets-feed/partial')/(CID+'.json')
SCANNER=Path('/var/lib/abutron-fp-scanner/partial-latest.json')
AI=Path('/var/lib/abutron-fp-scanner/ai/latest.json')
CONFIG=Path('/etc/abutron/fp-demov1-execution-1622.json')
ROUTER=Path('/opt/apex-client-mt5/fpmarkets-execution/fp_signal_order_router_apex11_1622.py')
APPROVED_ROUTER_SHAS=frozenset({'c169b94c50aeabb9ee3db0fd4648501a5fbadd0218bf930b9d9b4e468d431fcb','c903e638316c6cd7db90cde93aabd367e3112a6ed4dd583ce4041d453ff4249c','b50b47fd38c1ef91aac0924d190133b89310c271c6c650020bcc57a2ab0ebed2','32314609eda281b3cb3c784b7e3261668ed16a52fc0228d05ae39b89b343c1b0'})

BRIDGE_SHA='f0edbc4fbeb792d970b4e661d7c9d399419bcddbf49b36d36f520fc33a859ed4'
FP_ADAPTIVE_BRIDGE_SHA='76f3503c1661642438e690239d667758f0211fe4790623541345051f0a728a1c'
FP_ADAPTIVE_FLAG=Path('/etc/abutron/optionc-fp1622-demo-v2.json')
def adaptive_on():
 try:
  p=get_json(FP_ADAPTIVE_FLAG,4000)
  return (p.get('schema')=='abutron.optionc.activation.v2' and
   p.get('demo_only') is True and p.get('fpmarkets_enabled') is True and
   p.get('fp_enabled') is False and
   p.get('fpmarkets_connection_allowlist')==[CID] and
   p.get('risk_budget_pct_per_trade')==0.1 and
   p.get('portfolio_ceiling_pct')==20 and
   not FP_ADAPTIVE_FLAG.is_symlink())
 except (OSError,ValueError,TypeError):return False
OUT=Path('/var/lib/abutron-fp-execution/1622/activation')
HEX32=re.compile('^[0-9a-f]{32}$')

def get_json(p,limit=5000000):
 st=p.lstat()
 if not stat.S_ISREG(st.st_mode) or st.st_size<=1 or st.st_size>limit:
  raise ValueError('FP_SOURCE_FILE_TYPE_OR_SIZE_INVALID')
 return json.loads(p.read_text(encoding='utf-8'))

def fresh(t,now,max_age):
 date=dt.datetime.fromisoformat(str(t).replace('Z','+00:00'))
 if date.tzinfo is None:raise ValueError('FP_SOURCE_TIMESTAMP_WITHOUT_TZ')
 return -10<=now-date.timestamp()<=max_age

def account_row(db=None):
 if db is None:db=DB
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=8) as c:
  c.execute('PRAGMA query_only=ON')
  row=c.execute("""SELECT a.account_id,a.broker,a.environment,a.status,
     a.broker_server,a.account_reference,a.broker_verified_at,a.worker_binding,
     COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0),
     COALESCE(t.last_error,'')
     FROM apex_mt5_connections a LEFT JOIN apex_trade_controls t
     ON t.connection_id=a.id WHERE a.id=?""",(CID,)).fetchone()
 if not row:raise ValueError('FP_DEMO_ACCOUNT_NOT_FOUND')
 return {'owner':row[0],'broker':row[1],'environment':row[2],'status':row[3],
  'server':row[4],'login':str(row[5]),'verified':row[6] is not None,
  'worker_binding':row[7],'desired':row[8],'effective':row[9],'last_error':row[10]}

def check_readiness(record,now=None):
 now=time.time() if now is None else now
 errors=[]
 adaptive=adaptive_on()
 def require(ok,reason):
  if not ok:errors.append(reason)
 require(adaptive,'FP_LEGACY_FIXED_USD_EXECUTION_PERMANENTLY_DISABLED')
 require((record['broker'],record['environment'],record['status'],record['server'])==
         ('FP Markets','DEMO','CONNECTED','FPMarketsSC-Demo'),
         'FP_DEMO_NOT_CONNECTED')
 require(record['verified'] and bool(record['worker_binding']) and
         record['worker_binding']=='abutron-client-mt5-'+CID,
         'FP_BROKER_VERIFIED_WORKER_MISSING')
 require(record['desired'] in (0,1) and record['effective'] in (0,1),
         'FP_CONTROL_NOT_BINARY')
 with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=8) as db:
  db.execute('PRAGMA query_only=ON')
  lic=license_policy.connection_decision(db,record['owner'],CID)
 require(lic is not None and lic.get('license_allows_new_entries') is True,
         'FP_LICENSE_OR_BROKER_SEAT_MISSING')
 try:
  w=get_json(WORKER/'worker-health.json',30000)
  nonce=w.get('nonce')
  require(w.get('id')==CID and w.get('status')=='CONNECTED' and
          w.get('heartbeat_fresh') is True and
          w.get('broker')=='FP Markets' and w.get('mode')=='DEMO' and
          w.get('server')==record['server'] and
          isinstance(nonce,str) and HEX32.fullmatch(nonce) is not None and
          -10<=now-(WORKER/'worker-health.json').stat().st_mtime<=20,
          'FP_NATIVE_SESSION_NOT_VERIFIED')
  if not isinstance(nonce,str) or not HEX32.fullmatch(nonce):raise ValueError('FP_NONCE_BAD')
  p=FILES/('ABUTRON_SESSION_HEARTBEAT_V1_'+nonce+'.txt')
  require(p.is_file() and not p.is_symlink() and -10<=now-p.stat().st_mtime<=20,
          'FP_NATIVE_SESSION_HEARTBEAT_STALE')
  expected=['ABUTRON_MT5_NATIVE_HEARTBEAT_V1',nonce,w['proof_owner'],'FP_MARKETS',
            record['server'],'DEMO','CONNECTED','NO_ORDER_FUNCTIONS']
  require(p.read_text(encoding='utf-8-sig').splitlines()==expected,
          'FP_SESSION_HEARTBEAT_IDENTITY_MISMATCH')
  binary=WORKER/'terminal/MQL5/Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5'
  require(binary.is_file() and not binary.is_symlink() and
          hashlib.sha256(binary.read_bytes()).hexdigest()==(FP_ADAPTIVE_BRIDGE_SHA if adaptive else BRIDGE_SHA),
          'FP_APPROVED_BRIDGE_BINARY_NOT_INSTALLED')
  proofs=[]
  proof_types=[('ABUTRON_FP_BRIDGE_READY_V3_','FP_NATIVE_BRIDGE_READY_V3')]
  if not adaptive:proof_types.append(('ABUTRON_FP_BRIDGE_USD_50_100_','FP_NATIVE_BRIDGE_USD_50_100_V1'))
  for prefix,header in proof_types:
   p=FILES/(prefix+nonce+'.txt')
   require(p.is_file() and not p.is_symlink() and -10<=now-p.stat().st_mtime<=17,
           'FP_NATIVE_BRIDGE_PROOF_STALE')
   z=p.read_text(encoding='utf-8-sig').splitlines()
   require(len(z)==11 and z[:5]==[header,nonce,record['login'],record['server'],'FP_DEMO'],
           'FP_NATIVE_BRIDGE_ACCOUNT_OR_USD_POLICY_INVALID')
   if len(z)!=11:raise ValueError('FP_NATIVE_BRIDGE_PROOF_BAD_LENGTH')
   numbers=list(map(int,z[5:]))
   require(abs(now-numbers[0])<=26 and
           0<=numbers[1]<=300 and 0<=numbers[2]<=300 and
           all(v in (0,1) for v in numbers[3:]),
           'FP_NATIVE_BRIDGE_EXPOSURE_INVALID')
   proofs.append(numbers[1:])
  # Existing protected positions may remain open while the DEMO account
  # switch stays ON. New entries still require independent risk readiness
  # from the single-writer router; this acknowledgment places no orders.
  require((len(proofs)==1 if adaptive else proofs[0]==proofs[1]) and
          proofs[0][0]==0 and proofs[0][2:]==[1,1,1],
          'FP_NATIVE_BRIDGE_ORDERS_OFF_OR_EXPOSURE_UNSAFE')
  if adaptive:
   cap=FILES/('ABUTRON_OPTIONC_FP_CAPABILITY_V2_'+nonce+'.txt')
   require(cap.is_file() and not cap.is_symlink() and
           -10<=now-cap.stat().st_mtime<=17,
           'FP_ADAPTIVE_NATIVE_CAPABILITY_NOT_FRESH')
   capability=cap.read_text(encoding='utf-8-sig').splitlines()
   require(len(capability)==9 and capability[:5]==[
      'APEX_OPTIONC_ADAPTIVE_CAPABILITY_V2',nonce,record['login'],record['server'],'FP']
      and capability[6:]==['1','0.10','20'] and
      abs(now-int(capability[5]))<=26,
      'FP_ADAPTIVE_NATIVE_CAPABILITY_NOT_APPROVED')
  history=get_json(HISTORY)
  require(history.get('schema')=='abutron.fpmarkets.native.account_history.readonly.v1'
          and history.get('history_verified_from_mt5') is True
          and history.get('account_masked')=='••••'+record['login'][-4:]
          and history.get('account_currency')=='USD'
          and history.get('history_complete_within_selected_window') is True
          and fresh(history.get('generated_at_utc'),now,150)
          and fresh(history.get('broker_export_at_utc'),now,150),
          'FP_HISTORY_NOT_BROKER_VERIFIED_AND_FRESH')
  equity=history.get('equity_usd')
  open_count=history.get('open_positions_count')
  require(type(open_count) is int and 0<=open_count<=300 and
          history.get('pending_orders_count')==0 and
          proofs[0][1]==open_count,
          'FP_EXPOSURE_REQUIRES_HUMAN_RECONCILIATION')
  require(type(equity) in (int,float) and math.isfinite(equity) and (equity>0 if adaptive else equity>=260),
          'FP_50_USD_STOP_EXCEEDS_20_PERCENT_CEILING')
  recon=get_json(RECON,300000)
  require(recon.get('status')=='RECONCILED_READONLY'
    and recon.get('broker_history_verified') is True
    and recon.get('bridge_proof_matches_broker') is True
    and recon.get('bridge_input_enabled') is True
    and recon.get('broker_open_positions')==open_count
    and recon.get('broker_pending_orders')==0
    and recon.get('gross_sl_tp_usd')==(None if adaptive else [50,100])
    and recon.get('native_risk_model')==('OPTION_C_ADAPTIVE_V2' if adaptive else 'LEGACY_FIXED_USD')
    and (recon.get('portfolio_risk_for_new_entries_verified') is True if adaptive else True)
    and recon.get('portfolio_ceiling_pct')==20
    and recon.get('receipt_counts',{}).get('UNKNOWN')==0
    and recon.get('broker_verified_ack_count')==recon.get('receipt_counts',{}).get('ACK')
    and fresh(recon.get('generated_at_utc'),now,95),
    'FP_RISK_RECONCILIATION_NOT_READY')
  config=get_json(CONFIG,10000)
  require(config=={'schema':'abutron.fpmarkets.demo.single_writer.config.v1',
                   'account':'FP Markets DEMO','enable_request_creation':True},
          'FP_SINGLE_WRITER_DISARMED')
  require(hashlib.sha256(ROUTER.read_bytes()).hexdigest() in APPROVED_ROUTER_SHAS,
          'FP_SINGLE_WRITER_BINARY_SOURCE_MISMATCH')
  allowed=(Path('/etc/systemd/system/fp-demo-single-writer-preflight-1622.service.d')/
           'native-fp-demo-1622-writedir.conf')
  require(allowed.is_file() and str(FILES/'ABUTRON_FP') in allowed.read_text(),
          'FP_NATIVE_ORDER_WRITEPATH_NOT_VERIFIED')
  feed=get_json(FEED)
  require(feed.get('schema')=='abutron.fpmarkets.native.partial.readonly.v1'
          and feed.get('connection_id')==CID
          and feed.get('parallel_forex_status')=='SIX_FOREX_R_VERIFIED_V305'
          and feed.get('execution_enabled') is False
          and len(feed.get('quotes',{}))>=6
          and fresh(feed.get('checked_at_utc'),now,150),
          'FP_MARKET_FEED_NOT_VERIFIED')
  scanner=get_json(SCANNER)
  require(scanner.get('schema')=='abutron.fpmarkets.apex.scanner.partial.readonly.v1'
          and scanner.get('status')=='FP_SCANNER_PARTIAL_READONLY'
          and scanner.get('orders_enabled') is False
          and fresh(scanner.get('checked_at_utc'),now,150),
          'FP_ORIGINAL_APEX_SCANNER_NOT_READY')
  # No TradingAgents research review required for native DEMO activation.
 except (OSError,ValueError,TypeError,KeyError,UnicodeError,OverflowError) as err:
  errors.append('FP_NATIVE_SOURCE_'+type(err).__name__)
 return list(dict.fromkeys(errors))

TRANSIENT_FP_SNAPSHOT_RACES=frozenset((
 'FP_EXPOSURE_REQUIRES_HUMAN_RECONCILIATION',
 'FP_RISK_RECONCILIATION_NOT_READY',
))
def check_readiness_consistent(record,checker=check_readiness,delay=time.sleep):
 blocks=checker(record)
 for _ in range(5):
  if not blocks or any(reason not in TRANSIENT_FP_SNAPSHOT_RACES for reason in blocks):
   return blocks
  delay(1.0)
  blocks=checker(record)
 return blocks

def process():
 row=account_row()
 actual=row['effective']
 new=0
 reason=None
 if row['desired']==1:
  try:blocks=check_readiness_consistent(row)
  except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,OverflowError):
   blocks=['FP_READINESS_EVIDENCE_UNAVAILABLE']
  if not blocks:new=1
  else:reason=blocks[0]
 elif row['desired']==0:
  reason=None
 else:reason='FP_DESIRED_CONTROL_INVALID'
 # Effective ON is always independent of request, backend broker, license,
 # verified state, and account status. Use compare-and-update under lock.
 when=int(time.time())
 with sqlite3.connect(str(DB),timeout=9) as db:
  db.execute('PRAGMA busy_timeout=5000')
  db.execute('BEGIN IMMEDIATE')
  current=db.execute("""SELECT a.account_id,a.broker,a.environment,a.status,
        t.desired_enabled,t.effective_enabled,COALESCE(t.last_error,'')
        FROM apex_mt5_connections a JOIN apex_trade_controls t
        ON t.connection_id=a.id WHERE a.id=?""",(CID,)).fetchone()
  if not current:raise ValueError('FP_ACCOUNT_DISAPPEARED')
  if current[0]!=row['owner'] or current[1:3]!=('FP Markets','DEMO') or current[3]!='CONNECTED':
   new=0
   reason='FP_ACCOUNT_CHANGED_DURING_NATIVE_ACK'
  if current[4]!=row['desired']:
   new=0
   reason='FP_CLIENT_SWITCH_CHANGED_DURING_NATIVE_ACK'
  if current[4]!=1:new=0
  if new==0 and current[4]==0 and current[5]==0:
   db.execute('COMMIT')
   return {'status':'OFF','effective_enabled':False,'changed':False,'reason':None}
  if (current[5],current[6])!=(new,reason or ''):
   db.execute("""UPDATE apex_trade_controls SET effective_enabled=?,
     last_error=?,updated_at=? WHERE connection_id=?""",
     (new,reason,when,CID))
   db.execute("""INSERT INTO apex_trade_control_audit
     (account_id,connection_id,requested_enabled,outcome,occurred_at)
     VALUES(?,?,?,?,?)""",
     (current[0],CID,current[4],
      'FP_DEMO_NATIVE_EFFECTIVE_ON' if new else 'FP_DEMO_NATIVE_EFFECTIVE_BLOCKED_OR_OFF',when))
   changed=True
  else:changed=False
  db.execute('COMMIT')
 return {'status':'ON' if new else ('OFF' if current[4]==0 else 'BLOCKED'),
         'effective_enabled':bool(new),'changed':changed,'reason':reason}

def publish(result):
 OUT.mkdir(parents=True,mode=0o700,exist_ok=True)
 doc={'schema':'abutron.fpmarkets.demo.execution.activation_ack.v1',
      'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
      'broker':'FP Markets','environment':'DEMO',
      'account_masked':'••••1622','status':result['status'],
      'effective_enabled':result['effective_enabled'],
      'changed':result['changed'],'reason':result['reason'],
      'orders_submitted_by_ack':0}
 fd,tmp=tempfile.mkstemp(prefix='.fp-activation-',dir=OUT)
 try:
  with os.fdopen(fd,'w') as f:
   json.dump(doc,f,sort_keys=True,separators=(',',':'))
   f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o600)
  os.replace(tmp,OUT/'latest.json')
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

if __name__=='__main__':
 try:
  result=process()
  publish(result)
  print(json.dumps(result,sort_keys=True))
 except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,OverflowError):
  print(json.dumps({'status':'BLOCKED','changed':False,
    'effective_enabled':False,'orders_submitted_by_ack':0},sort_keys=True))
  raise
