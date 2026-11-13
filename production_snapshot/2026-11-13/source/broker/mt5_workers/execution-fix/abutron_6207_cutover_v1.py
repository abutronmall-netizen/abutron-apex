#!/usr/bin/env python3
"""6207-only Deriv DEMO cutover evidence and native EA activation ACK.

Separate from the legacy global dispatch gate. NO order requests, no broker
fills claimed, no changes to another account's desired/effective control.
Fails OFF unless an authenticated, one-shot 6207 operator approval is fresh.
"""
from __future__ import annotations
import argparse,datetime as dt,fcntl,json,os,sqlite3,stat,sys,tempfile,time
from pathlib import Path
sys.path[:0]=['/opt/apex-client-mt5','/opt/apex-client-portal','/opt/apex-signup',
             '/opt/apex-client-mt5/execution-fix','/opt/apex-client-mt5/quant-first']
import apex_native_order_runtime as native
import apex_signal_native_router_v1 as router
import handover_gate
import apex_crm_license_policy as license_policy
import apex_crm_subscriptions as subscriptions
import apex_pricing
from apex_portfolio_guard_v3 import capacity,UnsafeExposure
import abutron_prospective_execution_audit_v2 as audit
CID='d6fc2524ec373b8d1bc278a8be3ec635'
ROOT=Path('/var/lib/abutron-6207-pilot')
READINESS=ROOT/'6207-dedicated-cutover-v1.json'
APPROVAL=Path('/etc/abutron/6207-pilot-approval.json')
OPERATOR=Path('/etc/abutron/apex-demo-execution-approval.json')
MARKER=ROOT/'ONE_SHOT_CONSUMED'
FENCE=ROOT/'independent-source-fence-v1.json'
DIGITALOCEAN_PROOF=ROOT/'digitalocean-source-absent-v1.json'
OWNER_RETIREMENT=ROOT/'source-retirement-owner-confirmation-v1.json'
REPORT_SCHEMA='abutron.6207.dedicated_demo_cutover.v1'
ALLOW_OTHER_EFFECTIVE=False
class Blocked(RuntimeError):pass
def when(s):
 t=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
 if t.tzinfo is None:raise Blocked('NAIVE_TIME_DENIED')
 return t.timestamp()
def secured_json(path):
 if path.is_symlink() or not path.is_file():raise Blocked('APPROVAL_FILE_ABSENT')
 st=path.stat()
 if st.st_uid!=0 or stat.S_IMODE(st.st_mode)&0o077 or not 0<st.st_size<=4096:
  raise Blocked('APPROVAL_NOT_ROOT_PRIVATE')
 return json.loads(path.read_text())
def pilot_authorized(now):
 p=secured_json(APPROVAL)
 if (p.get('schema')!='abutron.6207.one_shot_pilot_approval.v1' or
     p.get('authorized') is not True or p.get('account_suffix')!='6207' or
     p.get('engineering_pilot_only') is not True or
     p.get('demo_only') is not True or p.get('max_orders')!=1 or
     p.get('risk_percent')!=0.10 or p.get('portfolio_ceiling_percent')!=20):
  raise Blocked('ONE_SHOT_PILOT_AUTHORIZATION_INVALID')
 if not when(p.get('not_before_utc'))<=now<when(p.get('expires_at_utc')):
  raise Blocked('PILOT_AUTHORIZATION_EXPIRED')
 if when(p['expires_at_utc'])-when(p['not_before_utc'])>600:
  raise Blocked('PILOT_APPROVAL_WINDOW_TOO_LONG')
 return True
def authorized_operator():
 d=secured_json(OPERATOR)
 if not handover_gate.approval_valid(d,OPERATOR.stat()):
  raise Blocked('ROOT_OPERATOR_SOURCE_FENCE_NOT_APPROVED')
 # This is only the operator's prior attestation, not remote fence proof.
 return True
def provider_deleted_source_proof(now):
 # Separate authenticated DigitalOcean API collector provides root-private,
 # strictly expiring evidence from the original provisioning team.
 if DIGITALOCEAN_PROOF.is_symlink() or not DIGITALOCEAN_PROOF.is_file():
  raise Blocked('DIGITALOCEAN_DELETION_EVIDENCE_MISSING')
 p=secured_json(DIGITALOCEAN_PROOF)
 required={'schema','provider','verified_at_utc','expires_at_utc','verification',
  'team_uuid','source_droplet_name','source_original_ipv4','source_present',
  'droplets_in_account','pages_scanned','inventory_sha256','account_uuid_sha256'}
 if set(p)!=required or p.get('schema')!='abutron.6207.digitalocean.source_absent.v1':
  raise Blocked('DIGITALOCEAN_DELETION_SCHEMA_UNTRUSTED')
 if (p.get('provider')!='DigitalOcean' or
     p.get('verification')!='AUTHENTICATED_DIGITALOCEAN_TEAM_API_FULL_DROPLET_INVENTORY' or
     p.get('team_uuid')!='89ae7096-be2b-4c30-a779-52f6116e7c4c' or
     p.get('source_droplet_name')!='abutron-ai' or
     p.get('source_original_ipv4')!='144.126.232.85' or
     p.get('source_present') is not False):
  raise Blocked('DIGITALOCEAN_TEAM_OR_SOURCE_MISMATCH')
 if not (-0.1<=now-when(p['verified_at_utc'])<=300 and
         now<when(p['expires_at_utc']) and
         0<when(p['expires_at_utc'])-when(p['verified_at_utc'])<=305):
  raise Blocked('DIGITALOCEAN_PROVIDER_EVIDENCE_EXPIRED')
 import re
 if not (type(p['droplets_in_account']) is int and p['droplets_in_account']>=0 and
         type(p['pages_scanned']) is int and p['pages_scanned']>=1 and
         all(isinstance(p[k],str) and re.fullmatch('[a-f0-9]{64}',p[k])
             for k in ('inventory_sha256','account_uuid_sha256'))):
  raise Blocked('DIGITALOCEAN_PROVIDER_EVIDENCE_INTEGRITY_INVALID')
 return True

def owner_deletion_attestation(now):
 # The owner explicitly confirms the old source server was deleted. This is
 # owner attestation, NOT independent provider proof. Applicable ONLY to a
 # time-limited, one-shot Deriv DEMO engineering pilot for account 6207.
 p=secured_json(OWNER_RETIREMENT)
 fields={'schema','recorded_at_utc','old_source_hostname','old_source_ipv4',
         'provider','confirmation_source','status','account_suffix',
         'environment','provider_api_verified','project_removal_seen',
         'one_order_only','risk_percent','owner_accepts_unverified_deletion'}
 if set(p)!=fields or p.get('schema')!='abutron.6207.owner_attested_source_retirement.v1':
  raise Blocked('OWNER_RETIREMENT_RECORD_SCHEMA_INVALID')
 if (p.get('old_source_hostname')!='abutron-ai' or
     p.get('old_source_ipv4')!='144.126.232.85' or
     p.get('provider')!='DigitalOcean' or
     p.get('confirmation_source')!='DIRECT_OWNER_CHAT_AND_PROJECT_ACTIVITY_SCREENSHOT' or
     p.get('status')!='OWNER_CONFIRMED_DELETED' or
     p.get('account_suffix')!='6207' or
     p.get('environment')!='DERIV_DEMO_ONLY' or
     p.get('provider_api_verified') is not False or
     p.get('project_removal_seen') is not True or
     p.get('one_order_only') is not True or
     p.get('risk_percent')!=0.10 or
     p.get('owner_accepts_unverified_deletion') is not True):
  raise Blocked('OWNER_DELETION_DEMO_SCOPE_NOT_APPROVED')
 if not -1<=now-when(p['recorded_at_utc'])<=1200:
  raise Blocked('OWNER_DELETION_ATTESTATION_EXPIRED')
 return True

def independent_source_fence(now):
 if DIGITALOCEAN_PROOF.exists():
  return provider_deleted_source_proof(now)
 if OWNER_RETIREMENT.exists():
  return owner_deletion_attestation(now)
 # Evidence requires an authenticated observation of the retired source,
 # not merely the local operator attestation or disconnected-device status.
 f=secured_json(FENCE)
 fields={'schema','checked_at_utc','source_device_id','source_hostname',
   'authenticated_readonly_method','source_order_timer_active_count',
   'source_order_service_active_count','source_order_process_count',
   'source_broker_execution_worker_count','source_proof_sha256'}
 if set(f)!=fields or f['schema']!='abutron.6207.independent_source_fence.v1':
  raise Blocked('INDEPENDENT_SOURCE_FENCE_SCHEMA_INVALID')
 if f['source_device_id']!='34dd03e2-4c17-4771-86e1-868c7e747500' or f['source_hostname']!='abutron-ai':
  raise Blocked('INDEPENDENT_SOURCE_IDENTITY_INVALID')
 if f['authenticated_readonly_method']!='REMOTE_DESKTOP_COMMANDER_SOURCE_DEVICE_EXECUTION':
  raise Blocked('REMOTE_SOURCE_NOT_AUTHENTICATED')
 if not -0.05<=now-when(f['checked_at_utc'])<=45:
  raise Blocked('INDEPENDENT_SOURCE_FENCE_NOT_FRESH')
 for key in ('source_order_timer_active_count','source_order_service_active_count',
             'source_order_process_count','source_broker_execution_worker_count'):
  if type(f[key]) is not int or f[key]!=0:
   raise Blocked('OLD_SOURCE_EXECUTOR_ACTIVE_OR_UNVERIFIED')
 import re
 if not isinstance(f['source_proof_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',f['source_proof_sha256']):
  raise Blocked('OLD_SOURCE_PROOF_DIGEST_MISSING')
 return True

def entitlements(conn,owner,row):
 cid,_,broker,env,server,state,worker,login,desired,effective,verified=row
 d=license_policy.account_decision(conn,owner,broker,'MT5',env,login,server,
       connection_state=state,broker_verified=verified is not None,
       worker_binding=worker,trading_active=True)
 if not d['new_entries_allowed']:raise Blocked('6207_LICENSE_OR_TRIAL_NOT_ENTITLED')
 if d['license_basis']=='paid':
  rec=conn.execute('SELECT plan,seats FROM apex_crm_licenses WHERE account_id=?',(owner,)).fetchone()
  sub=subscriptions.current(conn,owner)
  if (not rec or not sub or rec[1]!=apex_pricing.SEATS.get(rec[0]) or
      sub['plan']!=rec[0] or sub['status']!='active' or
      sub['currency']!='ZAR' or sub['billing_interval']!='monthly' or
      sub['amount_minor']!=apex_pricing.PRICES.get(rec[0]) or
      not sub['renewal_on'] or sub['renewal_on']<dt.date.today().isoformat()):
   raise Blocked('6207_SUBSCRIPTION_NOT_CURRENT')
 elif d['license_basis']!='trial':
  raise Blocked('6207_LICENSE_BASIS_INVALID')
def multi_trial_mode(now):
 if not handover_gate.active('abutron-6207-multi-trial-dispatch.timer'):
  return None
 if handover_gate.active('abutron-6207-one-shot-dispatch.timer'):
  raise Blocked('ONE_SHOT_AND_MULTI_WRITERS_CANNOT_BE_ENABLED_TOGETHER')
 import abutron_6207_multi_trial_v1 as trial
 trial.authorized(now)
 trial.owner_provenance()
 return trial

def source_verified(now):
 policy=router.read(router.POLICY)
 if (policy.get('environment')!='DERIV_DEMO' or policy.get('live_trading') is not False or
     policy.get('max_concurrent_positions')!=13 or policy.get('max_positions_per_symbol')!=1):
  raise Blocked('ROOT_DERIV_DEMO_POLICY_NOT_SAFE')
 if not native.optionc_on(CID):raise Blocked('ADAPTIVE_6207_POLICY_NOT_ACTIVE')
 multi=multi_trial_mode(now)
 if multi is None and (MARKER.is_file() or MARKER.is_symlink()):
  raise Blocked('ONE_SHOT_ALREADY_CONSUMED')
 if handover_gate.active('abutron-apex-native-orders.timer'):
  raise Blocked('GLOBAL_DISPATCHER_MUST_REMAIN_OFF')
 if multi is None and not handover_gate.active('abutron-6207-one-shot-dispatch.timer'):
  raise Blocked('DEDICATED_PILOT_DISPATCH_TIMER_NOT_ARMED')
 authorized_operator()
 if multi is None:
  independent_source_fence(now)
  pilot_authorized(now)
 with sqlite3.connect('file:'+router.DB+'?mode=ro',uri=True,timeout=6) as conn:
  conn.execute('PRAGMA query_only=ON')
  if conn.execute('PRAGMA quick_check').fetchone()[0]!='ok':
   raise Blocked('CUSTOMER_DB_NOT_INTEGRAL')
  row=conn.execute("""SELECT x.id,x.account_id,x.broker,x.environment,
   x.broker_server,x.status,x.worker_binding,x.account_reference,
   COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0),x.broker_verified_at
   FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
   WHERE x.id=?""",(CID,)).fetchone()
  if (not row or row[0]!=CID or not str(row[7]).endswith('6207') or
      row[2:6]!=('Deriv','DEMO','Deriv-Demo','CONNECTED') or
      row[6]!='abutron-client-mt5-'+CID or row[10] is None):
   raise Blocked('6207_BROKER_IDENTITY_OR_WORKER_INVALID')
  if row[8]!=1:raise Blocked('6207_CUSTOMER_SWITCH_OFF')
  if not ALLOW_OTHER_EFFECTIVE:
   other=conn.execute("""SELECT count(*) FROM apex_trade_controls t
    JOIN apex_mt5_connections x ON x.id=t.connection_id WHERE x.broker='Deriv'
    AND x.id != ? AND t.effective_enabled=1""",(CID,)).fetchone()[0]
   if other:raise Blocked('OTHER_DERIV_ACCOUNT_EFFECTIVE_ON')
  entitlements(conn,row[1],row)
 if not router.manager.attest(CID,'Deriv','Deriv-Demo'):
  raise Blocked('DERIV_6207_SESSION_NOT_ATTESTED')
 ea,err=native.ea_state_v2(CID,row[7],row[4])
 if (err or not ea or ea.get('protocol_version')!=3 or
     not ea.get('native_demo_orders_enabled') or
     not ea.get('terminal_trade_allowed') or not ea.get('account_trade_allowed') or
     ea.get('positions')!=0 or ea.get('pending_orders')!=0):
  raise Blocked('6207_NATIVE_V3_ACCOUNT_OR_TRADE_PERMISSION_INVALID')
 native.verify_6207_audit_readiness(ea['files'],ea['nonce'],row[7],row[4])
 good,reason,nonce=audit.ea_status(ea['files'],ea['files'].parent,row[7])
 if not good or nonce!=ea['nonce']:raise Blocked('6207_AUDIT_BINARY_OR_HEARTBEAT_INVALID_'+reason[:60])
 cap=ea['files']/('ABUTRON_OPTIONC_DERIV_CAPABILITY_V2_'+ea['nonce']+'.txt')
 if cap.is_symlink() or not cap.is_file() or not 0<=time.time()-cap.stat().st_mtime<=12:
  raise Blocked('ADAPTIVE_NATIVE_CAPABILITY_STALE')
 parts=cap.read_text(encoding='utf-8-sig').splitlines()
 if (len(parts)!=9 or parts[:5]!=['APEX_OPTIONC_ADAPTIVE_CAPABILITY_V2',
        ea['nonce'],row[7],'Deriv-Demo','DERIV'] or
     parts[6:]!=['1','0.10','20'] or abs(now-int(parts[5]))>18):
  raise Blocked('ADAPTIVE_NATIVE_CAPABILITY_MISMATCH')
 a=native.fresh_customer_broker_feed(CID,row[1])
 if a['positions'] or a.get('equity_usd',0)<=0:raise Blocked('6207_NOT_FLAT_OR_EQUITY_INVALID')
 if multi is not None:
  cfg=multi.authorized(now)
  multi.capacity(cfg,a)
 try:occupied=capacity(CID,a,ea,row[7],row[4],native.ledger.SYMBOLS,native.ledger.DB)
 except UnsafeExposure as exc:raise Blocked('NATIVE_PORTFOLIO_GUARD_'+str(exc)[:50])
 if occupied:raise Blocked('6207_NATIVE_EXPOSURE_NOT_FLAT')
 with sqlite3.connect('file:'+str(native.ledger.DB)+'?mode=ro',uri=True,timeout=6) as db:
  pending=db.execute("""SELECT COUNT(*) FROM attempts WHERE connection_id=? AND state IN
   ('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED','OPEN_PROTECTED','UNPROTECTED')""",(CID,)).fetchone()[0]
 if pending:raise Blocked('6207_LEDGER_UNRESOLVED')
 return {'owner':row[1], 'connection_id':CID,'nonce':ea['nonce'],
   'equity_usd':a['equity_usd'],'risk_budget_usd':round(a['equity_usd']*.001,4),
   'active_positions':0,'pending_orders':0,'native_audit_sha_verified':True}
def atomic(path,value):
 ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
 if path.is_symlink():raise Blocked('READINESS_PATH_SYMLINK')
 fd,tmp=tempfile.mkstemp(prefix='.cutover-',dir=ROOT)
 try:
  with os.fdopen(fd,'w') as f:
   json.dump(value,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o600);os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def inspect(now=None):
 now=time.time() if now is None else float(now)
 report={'schema':REPORT_SCHEMA,'checked_at_utc':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
 'account_suffix':'6207','connection_id':CID,'status':'BLOCKED',
 'new_orders_sent':0,'broker_fill_acknowledged':False,
 'source_single_writer_fence':('OWNER_CONFIRMED_DELETED_PROVIDER_UNVERIFIED_DEMO_ONLY' if OWNER_RETIREMENT.exists() and not DIGITALOCEAN_PROOF.exists() else 'PROVIDER_OR_AUTHENTICATED_SOURCE_PROOF_REQUIRED'),
 'reason':'UNVERIFIED','expiry_epoch':now+10}
 try:
  details=source_verified(now)
  report.update(status='READY_FOR_6207_NATIVE_ACTIVATION',reason='NONE',
                account_owner=details['owner'],mt5_session_nonce=details['nonce'],
                equity_usd=details['equity_usd'],risk_budget_usd=details['risk_budget_usd'])
 except (Blocked,ValueError,TypeError,KeyError,sqlite3.Error,OSError,RuntimeError) as e:
  report['reason']=str(e)[:120]
 atomic(READINESS,report)
 print('6207_SCOPED_CUTOVER',report['status'],report['reason'],'ORDERS',0)
 return report
def delegation_active(cid,owner,desired,now=None):
 if cid!=CID or desired!=1:return False
 now=time.time() if now is None else float(now)
 try:
  multi=multi_trial_mode(now)
  if multi is None and (MARKER.exists() or MARKER.is_symlink()):return False
  if (READINESS.is_symlink() or not READINESS.is_file() or READINESS.stat().st_uid!=0 or
      stat.S_IMODE(READINESS.stat().st_mode)&0o077):return False
  j=json.loads(READINESS.read_text())
  if (j.get('schema')!=REPORT_SCHEMA or j.get('status')!='READY_FOR_6207_NATIVE_ACTIVATION' or
      j.get('connection_id')!=CID or j.get('account_owner')!=owner or
      not -0.01<=now-when(j.get('checked_at_utc'))<=12 or now>=j.get('expiry_epoch',0)):
   return False
  if handover_gate.active('abutron-apex-native-orders.timer'):return False
  if multi is None and not handover_gate.active('abutron-6207-one-shot-dispatch.timer'):
   return False
  authorized_operator()
  if multi is None:
   independent_source_fence(now)
   pilot_authorized(now)
  else:
   # Re-check the equity drawdown, count and broker-flat requirements
   # against current authenticated data before each effective-ON ACK.
   multi.probe()
  return True
 except (Blocked,ValueError,TypeError,KeyError,OSError,sqlite3.Error):return False
def acknowledge():
 now=time.time();report=inspect(now)
 if report['status']=='READY_FOR_6207_NATIVE_ACTIVATION':
  # Fail OFF if fresh broker proof disappears between report and acknowledgement.
  try:
   source_verified(time.time())
  except (Blocked,ValueError,TypeError,KeyError,sqlite3.Error,OSError,RuntimeError) as exc:
   report['status']='BLOCKED'
   report['reason']='SECOND_NATIVE_PROOF_FAILED_'+str(exc)[:80]
   atomic(READINESS,report)
 allow=report['status']=='READY_FOR_6207_NATIVE_ACTIVATION'
 with sqlite3.connect(router.DB,timeout=12,isolation_level=None) as c:
  c.execute('PRAGMA busy_timeout=12000')
  c.execute('BEGIN IMMEDIATE')
  try:
   row=c.execute("""SELECT x.account_id,x.status,x.broker,x.environment,x.broker_server,
    COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0)
    FROM apex_mt5_connections x JOIN apex_trade_controls t ON t.connection_id=x.id WHERE x.id=?""",(CID,)).fetchone()
   if not row:raise Blocked('6207_ACCOUNT_DELETED_DURING_ACK')
   owner,status,broker,env,server,desired,effective=row
   enable=bool(allow and desired==1 and owner==report.get('account_owner') and
    (status,broker,env,server)==('CONNECTED','Deriv','DEMO','Deriv-Demo') and
    delegation_active(CID,owner,desired))
   if effective!=int(enable):
    stamp=int(time.time())
    changed=c.execute("""UPDATE apex_trade_controls SET effective_enabled=?,updated_at=?,last_error=?
      WHERE connection_id=? AND effective_enabled=? AND desired_enabled=?""",
      (int(enable),stamp,None if enable else 'SCOPED_6207_PILOT_'+report['reason'][:100],
       CID,effective,desired))
    if changed.rowcount!=1:raise Blocked('6207_ACK_CONCURRENT_CHANGE')
    c.execute("""INSERT INTO apex_trade_control_audit
     (account_id,connection_id,requested_enabled,outcome,occurred_at)
     VALUES(?,?,?,?,?)""",(owner,CID,desired,
      '6207_NATIVE_ADAPTIVE_DEMO_READY_ACK_NO_ORDER' if enable else
      '6207_SCOPED_EXECUTION_REVOKED_NO_ORDER',stamp))
   c.execute('COMMIT')
  except Exception:
   c.execute('ROLLBACK');raise
 print('6207_NATIVE_ACTIVATION_ACK','EFFECTIVE',int(enable),'ACCOUNT_ONLY',CID[:8],
       'BROKER_ORDER_ACKS_CLAIMED',0)
 return enable
def main():
 p=argparse.ArgumentParser()
 x=p.add_mutually_exclusive_group(required=True)
 x.add_argument('--inspect',action='store_true')
 x.add_argument('--ack',action='store_true')
 args=p.parse_args()
 if os.geteuid()!=0:raise SystemExit('ROOT_REQUIRED')
 if args.inspect:inspect()
 else:acknowledge()
if __name__=='__main__':main()
