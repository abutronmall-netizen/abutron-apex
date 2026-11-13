#!/usr/bin/env python3
"""ABUTRON APEX: 6207 ONLY, prospective Deriv DEMO bounded trial.

Autonomous until 2026-11-07 14:00:00 UTC (16:00 SAST).
Never attempts LIVE or FP, changes global order routes, or retries an
uncertain broker submission. Protective exit and reconciliation continue.
"""
from __future__ import annotations
import datetime as dt,fcntl,hashlib,json,math,os,sqlite3,stat,sys,time
from pathlib import Path
sys.path[:0]=['/opt/apex-client-mt5','/opt/apex-client-portal','/opt/apex-signup',
 '/opt/apex-client-mt5/quant-first','/opt/apex-client-mt5/execution-fix']
import abutron_6207_one_shot_pilot_v1 as one
import apex_native_order_runtime as native
import apex_signal_native_router_v1 as router
import customer_order_ledger as ledger
CID='d6fc2524ec373b8d1bc278a8be3ec635'
ROOT=Path('/var/lib/abutron-6207-pilot')
APPROVAL=Path('/etc/abutron/6207-multi-trial-approval-v1.json')
OWNER=ROOT/'source-retirement-owner-confirmation-v1.json'
REPORT=ROOT/'multi-trial-latest-v1.json'
END=dt.datetime(2026,11,7,14,0,0,tzinfo=dt.timezone.utc).timestamp()
MAX_TRADES=4
MAX_POSITIONS=1
RISK_PCT=0.10
DRAWDOWN_PCT=0.40
ALLOWED={'Volatility 25 Index.0','Volatility 50 Index.0','Volatility 75 Index.0'}
DISPATCH_TIMER='abutron-6207-multi-trial-dispatch.timer'
SOURCE='OWNER_CONFIRMED_DELETED_NOT_DIGITALOCEAN_API_VERIFIED'
class Denied(RuntimeError):pass

def stamp(s):
 try:return one.stamp(s)
 except Exception as e:raise Denied('INVALID_TIME_FIELD') from e

def protected_json(path):
 if path.is_symlink() or not path.is_file():
  raise Denied('SCOPED_TRIAL_APPROVAL_MISSING')
 st=path.stat()
 if st.st_uid!=0 or stat.S_IMODE(st.st_mode)&0o077 or not 0<st.st_size<=8192:
  raise Denied('ROOT_PRIVATE_APPROVAL_REQUIRED')
 return json.loads(path.read_text())

def authorized(now=None):
 now=time.time() if now is None else float(now)
 if now>=END:raise Denied('16_00_SAST_HARD_CUTOFF')
 cfg=protected_json(APPROVAL)
 if set(cfg)!={'schema','account_suffix','broker','environment','allowed_symbols',
  'start_at_utc','expires_at_utc','authorized','max_orders','max_positions',
  'risk_percent_per_order','total_nominal_risk_percent','equity_drawdown_stop_percent',
  'initial_equity_usd','portfolio_ceiling_percent','previous_one_shot_consumed',
  'owner_source_deletion_provider_verified','trial_scope','no_retry_on_unknown'}:
  raise Denied('TRIAL_APPROVAL_SCHEMA_MISMATCH')
 if cfg['schema']!='abutron.6207.bounded_multi_demo_trial.v1' or cfg['trial_scope']!='DERIV_6207_ONLY_UNTIL_16_SAST':
  raise Denied('TRIAL_SCOPE_INVALID')
 if cfg['account_suffix']!='6207' or cfg['broker']!='Deriv' or cfg['environment']!='DEMO':
  raise Denied('TRIAL_NOT_DERIV_6207_DEMO')
 if type(cfg['authorized']) is not bool or cfg['authorized'] is not True:
  raise Denied('TRIAL_OPERATOR_NOT_AUTHORIZED')
 if (cfg['max_orders']!=MAX_TRADES or cfg['max_positions']!=MAX_POSITIONS or
   cfg['risk_percent_per_order']!=RISK_PCT or
   cfg['total_nominal_risk_percent']!=MAX_TRADES*RISK_PCT or
   cfg['equity_drawdown_stop_percent']!=DRAWDOWN_PCT or
   cfg['portfolio_ceiling_percent']!=20 or
   cfg['previous_one_shot_consumed'] is not True or
   cfg['owner_source_deletion_provider_verified'] is not False or
   cfg['no_retry_on_unknown'] is not True):
  raise Denied('TRIAL_RISK_POLICY_INVALID')
 if sorted(cfg['allowed_symbols'])!=sorted(ALLOWED):
  raise Denied('TRIAL_SYMBOL_UNIVERSE_INVALID')
 start=stamp(cfg['start_at_utc']);end=stamp(cfg['expires_at_utc'])
 if abs(end-END)>0.01 or not start<=now<end or not (0<end-start<=6*3600):
  raise Denied('TRIAL_NOT_IN_APPROVED_WINDOW')
 eq=cfg['initial_equity_usd']
 if type(eq) not in (int,float) or not math.isfinite(eq) or eq<=0:
  raise Denied('TRIAL_STARTING_EQUITY_INVALID')
 if not (ROOT/'ONE_SHOT_CONSUMED').is_file():
  raise Denied('PREVIOUS_ONE_SHOT_CONSUMPTION_NOT_PRESERVED')
 if (Path('/etc/abutron/6207-pilot-approval.json')).exists():
  raise Denied('PRIOR_ONE_SHOT_APPROVAL_MUST_REMAIN_REVOKED')
 return cfg

def owner_provenance():
 p=protected_json(OWNER)
 if not (p.get('schema')=='abutron.6207.owner_attested_source_retirement.v1' and
   p.get('status')=='OWNER_CONFIRMED_DELETED' and
   p.get('old_source_hostname')=='abutron-ai' and
   p.get('old_source_ipv4')=='144.126.232.85' and
   p.get('provider')=='DigitalOcean' and
   p.get('account_suffix')=='6207' and p.get('environment')=='DERIV_DEMO_ONLY' and
   p.get('provider_api_verified') is False):
  raise Denied('OWNER_SOURCE_PROVENANCE_MISMATCH')
 return SOURCE

def attempts(cfg):
 with sqlite3.connect('file:'+str(ledger.DB)+'?mode=ro',uri=True,timeout=8) as c:
  c.execute('PRAGMA query_only=ON')
  if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':
   raise Denied('LEDGER_INTEGRITY_INVALID')
  rows=c.execute("""SELECT symbol,side,state,created_at_utc,buffered_loss_usd
    FROM attempts WHERE connection_id=? AND created_at_utc>=?
    ORDER BY created_at_utc,signal_key""",(CID,cfg['start_at_utc'])).fetchall()
 for r in rows:
  if r[0] not in ALLOWED or r[1] not in ('BUY','SELL'):
   raise Denied('TRIAL_UNEXPECTED_BROKER_ORDER')
 return rows

def capacity(cfg,account):
 rows=attempts(cfg)
 count=len(rows)
 if count>=MAX_TRADES:raise Denied('TRIAL_MAXIMUM_FOUR_ORDERS_USED')
 if any(r[2] in ('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED','UNPROTECTED') for r in rows):
  raise Denied('UNCERTAIN_ORDER_MUST_RECONCILE_NO_RETRY')
 if any(r[2]=='OPEN_PROTECTED' for r in rows):
  raise Denied('ONE_OPEN_POSITION_MAX')
 if len(account.get('positions',[]))!=0 or account.get('open_positions')!=0 or account.get('all_positions_protected') is not True:
  raise Denied('BROKER_NOT_FLAT_OR_PROTECTED')
 equity=account.get('equity_usd')
 if type(equity) not in (float,int) or not math.isfinite(equity) or equity<=0:
  raise Denied('EQUITY_NOT_VERIFIED')
 if equity<cfg['initial_equity_usd']*(1-DRAWDOWN_PCT/100):
  raise Denied('TRIAL_DRAWDOWN_STOP_0_40_PERCENT')
 # Every native order carries independent 0.10%-equity native risk guards.
 # Four entries max is the cumulative nominal 0.40%-of-equity budget.
 reserved=sum(float(r[4] or 0) for r in rows)
 if reserved > max(equity,cfg['initial_equity_usd'])*DRAWDOWN_PCT/100+0.05:
  raise Denied('TRIAL_NOMINAL_ORDER_RISK_BUDGET_EXCEEDED')
 return count

def enable_state():
 import abutron_6207_cutover_v1 as gate
 return gate.handover_gate.active(DISPATCH_TIMER) and not gate.handover_gate.active('abutron-apex-native-orders.timer') and not gate.handover_gate.active('abutron-6207-one-shot-dispatch.timer')

def choose_due(now):
 pub=one.read(one.PUBLISHED,100000)
 if pub.get('schema')!=one.SCHEMA or pub.get('account_suffix')!='6207':
  raise Denied('RESEARCH_PUBLICATION_IDENTITY_INVALID')
 if not 0<=now-stamp(pub.get('created_at_utc'))<=80:
  raise Denied('RESEARCH_PUBLICATION_STALE')
 mh,ch=one.source_ok(now)
 obs=one.observed_candidate_rows(now,mh,ch)
 matched=[]
 for r in obs:
  symbol,model,bar,first,lag,entry,side,barhash,*_=r
  if symbol not in ALLOWED or not entry<=now<entry+one.MAX_ENTRY_LATENCY:
   continue
  p=[x for x in pub['candidates'] if
     (x.get('symbol'),x.get('model'),x.get('side'),x.get('source_signal_m5_start'),
      x.get('source_bar_sha256'),x.get('planned_entry_m5_start'),x.get('strategy_sha256'),
      x.get('cost_sha256'))==(symbol,model,side,bar,barhash,entry,mh,ch)]
  if len(p)!=1:continue
  if any(z[0]==symbol and z[5]==entry and z[6]!=side for z in obs):
   continue
  matched.append(p[0])
 if not matched:raise Denied('NO_FRESH_PRECOMMITTED_DUE_SIGNAL')
 return sorted(matched,key=lambda x:(x['planned_entry_m5_start'],x['symbol'],x['model']))

def dispatch():
 if os.geteuid()!=0:raise Denied('ROOT_REQUIRED')
 now=time.time();cfg=authorized(now);owner_provenance()
 if not enable_state():raise Denied('ISOLATED_EXECUTION_TIMER_NOT_ARMED')
 # Lock shared native order writer across legacy and multi-trial processes.
 lockpath=native.ROOT/'execution-writer.lock'
 fd=os.open(lockpath,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  cfg=authorized(time.time())
  row,ea,account=one.fresh_runtime_checks(time.time())
  capacity(cfg,account)
  due=choose_due(time.time())
  folder=ea['files']/'ABUTRON'
  if folder.is_symlink() or not folder.is_dir() or (folder/native.REQUEST_NAME).exists():
   raise Denied('EA_HAS_PENDING_NATIVE_REQUEST')
  for cand in due:
   key=ledger.expected_key(row[1],CID,cand['symbol'],cand['ledger_m5_bar_time'],cand['side'])
   if key!=cand.get('signal_key'):continue
   if (folder/native.RECEIPT_DIR/(key+'.txt')).exists():continue
   with sqlite3.connect('file:'+str(ledger.DB)+'?mode=ro',uri=True,timeout=8) as c:
    duplicate=c.execute('SELECT count(*) FROM attempts WHERE signal_key=?',(key,)).fetchone()[0]
   if duplicate:continue
   if time.time()>=END or time.time()>=cand['planned_entry_m5_start']+one.MAX_ENTRY_LATENCY:
    raise Denied('DUE_SIGNAL_EXPIRED_BEFORE_COMMIT')
   # Durable original identity + risk reservation, then UNKNOWN before I/O.
   proof={'broker':'Deriv','environment':'DEMO','server':'Deriv-Demo',
     'current_broker_identity_verified':True,'open_positions':0,'occupied_symbols':[],
     'protected_positions_reconciled':True,'pending_orders':0,
     'risk_governor_approved':True,'account_trade_authorized':True,
     'single_writer_approved':True}
   with ledger.new() as c:
    ledger.reserve(c,row[1],CID,cand['symbol'],cand['side'],
     cand['ledger_m5_bar_time'],key,proof)
    ledger.queue_native_adaptive_pending(c,key,account['equity_usd'])
   # The ledger now prevents retry even if publication fails.
   native.atomic_audit_client_context(folder,key,ea['nonce'],row[7],row[4],cand['symbol'],cand['side'])
   if time.time()>=END or time.time()>=cand['planned_entry_m5_start']+one.MAX_ENTRY_LATENCY:
    raise Denied('SIGNAL_EXPIRED_AFTER_DURABLE_UNKNOWN_NO_RETRY')
   request=['APEX_NATIVE_ADAPTIVE_ORDER_V3',ea['nonce'],key,row[7],row[4],
     cand['symbol'],cand['side'],'AUTO','0.10','STRUCTURE_M5',
     str(int(min(time.time()+12,END))),'SEND_DEMO_ONLY']
   native.atomic_native_request(folder/native.REQUEST_NAME,request)
   result={'schema':'abutron.6207.multi_demo_trial.v1','checked_at_utc':one.utc(),
      'account_suffix':'6207','status':'NATIVE_REQUEST_PUBLISHED_SUBMISSION_UNKNOWN',
      'attempt_key_prefix':key[:12],'instrument':cand['symbol'],'side':cand['side'],
      'model':cand['model'],'broker_ack':False,'safe_to_retry':False,
      'source_deletion_verification':SOURCE,'hard_cutoff_utc':'2026-11-07T14:00:00Z'}
   one.atomic_json(REPORT,result)
   print('6207_TRIAL_NATIVE_ORDER_PUBLISHED_UNKNOWN_NO_RETRY',cand['symbol'],cand['side'],
      key[:12],flush=True)
   return
  raise Denied('DUE_SIGNALS_ALL_DUPLICATE_OR_MISMATCHED')
 finally:os.close(fd)

def probe():
 cfg=authorized()
 owner_provenance()
 row=one.identity()
 acc=native.fresh_customer_broker_feed(CID,row[1])
 n=capacity(cfg,acc)
 return {'orders_attempted':n,'equity':acc['equity_usd'],'account_suffix':'6207',
  'next_order_risk_pct':0.10,'trading_end_utc':'2026-11-07T14:00:00Z'}

def main():
 import argparse
 p=argparse.ArgumentParser()
 action=p.add_mutually_exclusive_group(required=True)
 action.add_argument('--dispatch',action='store_true')
 action.add_argument('--inspect',action='store_true')
 arg=p.parse_args()
 if arg.inspect:
  try:print('6207_MULTI_TRIAL_READINESS',json.dumps(probe()),flush=True)
  except Exception as exc:print('6207_MULTI_TRIAL_BLOCKED',type(exc).__name__,str(exc)[:150],flush=True)
 elif arg.dispatch:
  try:dispatch()
  except BlockingIOError:
   # Another scoped writer owns the native single-writer lock. No retry or order.
   print('6207_MULTI_TRIAL_CONCURRENT_TICK_SKIPPED',flush=True)
  except Denied as exc:
   # A non-due M5 signal is normal, and an existing position disables new entries.
   # All other denials remain safe and observable without a broker request.
   print('6207_MULTI_TRIAL_WAIT_OR_DENY',str(exc)[:140],flush=True)
   if str(exc) not in ('NO_FRESH_PRECOMMITTED_DUE_SIGNAL','RESEARCH_PUBLICATION_STALE',
      'ONE_OPEN_POSITION_MAX','TRIAL_MAXIMUM_FOUR_ORDERS_USED','16_00_SAST_HARD_CUTOFF',
      'BROKER_NOT_FLAT_OR_PROTECTED','UNCERTAIN_ORDER_MUST_RECONCILE_NO_RETRY'):
    raise
if __name__=='__main__':main()
