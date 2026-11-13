#!/usr/bin/env python3
"""ABUTRON DEMO 6207 research-to-order read-only preflight; NO broker order code."""
from pathlib import Path
import json,sqlite3,hashlib,datetime as dt,time,tempfile,os
ROOT=Path('/var/lib/abutron-quant-first')
RESULT=ROOT/'6207-research-to-order-preflight-latest.json'
AUTH=Path('/etc/abutron/optionc-live-010.json')
ACC=Path('/var/lib/apex-signup/accounts.sqlite3')
LEDGER=Path('/var/lib/apex-client-feed/execution-ledger.sqlite3')
FORWARD=ROOT/'entry-model-causal-v2-latest.json'
PROSPECT=ROOT/'prospective-v25-v50-v75-readiness-v1.json'
AUDIT=ROOT/'prospective-execution-audit-readiness-v1.json'
COST=ROOT/'broker-native-cost-evidence-latest.json'
MODEL=Path('/opt/apex-client-mt5/quant-first/abutron_entry_model_v1.py')
COSTREF=Path('/var/backups/abutron-cost-research-20261106T2235Z/BROKER_COST_REFERENCE_EQUITY_V2.json')
FORWARD_DB=ROOT/'entry-model-causal-v2.sqlite3'
ALLOWED={'Volatility 25 Index.0','Volatility 50 Index.0','Volatility 75 Index.0'}
def safe_json(path):
 if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<4_000_000:
  raise ValueError('UNTRUSTED_SOURCE_'+path.name)
 return json.loads(path.read_text())
def stamp(value):
 t=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
 if t.tzinfo is None:raise ValueError('NAIVE_TIMESTAMP')
 return t.timestamp()
def digest(path):
 if path.is_symlink() or not path.is_file():raise ValueError('MODEL_UNTRUSTED')
 return hashlib.sha256(path.read_bytes()).hexdigest()
def key(owner,cid,sym,bar,side):
 return hashlib.sha256((owner+'|'+cid+'|'+sym+'|M5|'+str(bar)+'|'+side).encode()).hexdigest()
def classify(row,now,modelhash,costhash):
 sym,model,bar,first,age,entry,side,barhash,mh,ch,status=row
 if sym not in ALLOWED or side not in ('BUY','SELL'):return 'SYMBOL_OR_SIDE_DENIED'
 if status!='WAITING_FOR_GENUINELY_FUTURE_ENTRY':return 'NOT_PENDING'
 try:observed=stamp(first)
 except (ValueError,TypeError):return 'INVALID_TIMESTAMP'
 if (type(bar)!=int or type(entry)!=int or entry%300 or
     not 0<=age<=180 or not bar+300<=observed<entry or not 0<entry-observed<=300):
  return 'NONCAUSAL_OR_STALE_SIGNAL'
 if mh!=modelhash or ch!=costhash or not isinstance(barhash,str) or len(barhash)!=64:
  return 'MODEL_COST_OR_SOURCE_CHANGED'
 if now>=entry+15:return 'ENTRY_WINDOW_EXPIRED'
 if now<entry:return 'AWAIT_FUTURE_M5_OPEN'
 return 'ENTRY_WINDOW_SHADOW_ONLY'
def run(now=None):
 now=time.time() if now is None else float(now)
 report={'schema':'abutron.6207.research_to_order_preflight.v1',
  'checked_at_utc':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
  'account_suffix':'6207','mode':'READONLY_NO_NATIVE_REQUESTS',
  'orders_submitted':0,'broker_order_acknowledged':0,
  'order_submission_allowed':False,'broker_fills_claimed':0,
  'candidates':[],'blockers':[]}
 try:
  policy=safe_json(AUTH)
  ids=policy.get('deriv_connection_allowlist')
  if (policy.get('schema')!='abutron.optionc.activation.v2' or
      policy.get('demo_only') is not True or policy.get('deriv_enabled') is not True or
      policy.get('risk_budget_pct_per_trade')!=0.1 or
      policy.get('portfolio_ceiling_pct')!=20 or
      not isinstance(ids,list) or len(ids)!=1):
   raise ValueError('6207_ADAPTIVE_POLICY_INVALID')
  cid=ids[0]
  if not isinstance(cid,str) or len(cid)!=32 or any(c not in '0123456789abcdef' for c in cid):
   raise ValueError('6207_CONNECTION_NOT_VALID')
  with sqlite3.connect('file:'+str(ACC)+'?mode=ro',uri=True) as con:
   con.execute('PRAGMA query_only=ON')
   owner,broker,env,server,status,login=con.execute(
    'SELECT account_id,broker,environment,broker_server,status,account_reference FROM apex_mt5_connections WHERE id=?',(cid,)).fetchone()
  if (broker,env,server,status)!=('Deriv','DEMO','Deriv-Demo','CONNECTED') or not str(login).endswith('6207'):
   raise ValueError('6207_BROKER_IDENTITY_NOT_VERIFIED')
  feed=safe_json(Path('/var/lib/apex-client-feed')/(cid+'.json'))
  if feed.get('broker_data_verified') is not True or not -15<=now-stamp(feed.get('checked_at_utc'))<=160:
   raise ValueError('6207_BROKER_FEED_NOT_FRESH')
  f=safe_json(FORWARD);a=safe_json(AUDIT);p=safe_json(PROSPECT);c=safe_json(COST)
  if (f.get('schema')!='abutron.quant.causal_forward_market_outcome.v2' or
      f.get('strategy_model_sha256')!=digest(MODEL) or f.get('cost_model_sha256')!=digest(COSTREF) or
      not -15<=now-stamp(f.get('checked_at_utc'))<=160):
   raise ValueError('PROSPECTIVE_MODEL_HASH_OR_FRESHNESS_INVALID')
  if a.get('account_suffix')!='6207' or a.get('active_ea_audit_hook_verified') is not True:
   raise ValueError('6207_NATIVE_AUDIT_HOOK_NOT_READY')
  if c.get('collection')!='REAL_AUTHENTICATED_DERIV_DEMO_NATIVE_MQL5_TICKS':
   raise ValueError('COST_SOURCE_NOT_AUTHENTICATED')
  report['account_identity_verified']=True
  report['matured_forward_outcomes']=f.get('total_valid_outcomes')
  report['models_passing_prospective_edge_gate']=p.get('passed_stress_test_not_execution_approval')
  report['native_tick_reference_count']=c.get('tick_count')
  report['native_snapshot_quote_samples']=a.get('native_quote_samples_total')
  report['request_to_fill_slippage_observations']=a.get('true_request_to_fill_slippage_observations')
  report['zero_spread_snapshots_never_substituted_for_tick_cost_evidence']=True
  with sqlite3.connect('file:'+str(FORWARD_DB)+'?mode=ro',uri=True) as con:
   con.execute('PRAGMA query_only=ON')
   if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('FORWARD_DB_CORRUPT')
   rows=con.execute('SELECT symbol,model,signal_m5_start,first_observed_utc,signal_age_sec,planned_entry_m5_start,side,signal_bar_hash,model_sha256,cost_sha256,status FROM observed WHERE status=? ORDER BY planned_entry_m5_start DESC LIMIT 160',('WAITING_FOR_GENUINELY_FUTURE_ENTRY',)).fetchall()
  with sqlite3.connect('file:'+str(LEDGER)+'?mode=ro',uri=True) as con:
   con.execute('PRAGMA query_only=ON')
   for row in rows:
    verdict=classify(row,now,f['strategy_model_sha256'],f['cost_model_sha256'])
    if verdict not in ('AWAIT_FUTURE_M5_OPEN','ENTRY_WINDOW_SHADOW_ONLY'):continue
    sym,model,bar,_,_,entry,side,*_=row
    k=key(owner,cid,sym,bar,side)
    duplicate=con.execute('SELECT state FROM attempts WHERE signal_key=?',(k,)).fetchone()
    busy=con.execute('SELECT count(*) FROM attempts WHERE connection_id=? AND symbol=? AND state IN (?,?,?,?,?)',(cid,sym,'RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED','OPEN_PROTECTED','UNPROTECTED')).fetchone()[0]
    report['candidates'].append({'symbol':sym,'model':model,'side':side,
     'key_prefix':k[:12],'entry_utc':dt.datetime.fromtimestamp(entry,dt.timezone.utc).isoformat(),
     'causality':verdict,'durable_ledger_state':duplicate[0] if duplicate else ('SYMBOL_BUSY' if busy else 'NO_DUPLICATE'),
     'native_tick_spread_p95_bps_prior_window':c.get('spreads',{}).get(sym,{}).get('spread_bps_p95'),
     'broker_order_allowed':False})
  report['blockers']=['NOT_POSITIVE_EXPECTANCY_APPROVED','RESEARCH_CANDIDATE_NOT_PUBLISHED_TO_NATIVE_ROUTER',
   'NO_ONE_ORDER_PILOT_RELEASE','REAL_REQUEST_TO_FILL_SLIPPAGE_UNMEASURED']
 except Exception as exc:
  report['blockers']=['FAIL_CLOSED_'+str(exc)[:120]]
 if RESULT.is_symlink():raise ValueError('OUTPUT_SYMLINK_DENIED')
 fd,tmp=tempfile.mkstemp(prefix='.6207-r2o-',dir=RESULT.parent)
 try:
  with os.fdopen(fd,'w') as out:
   json.dump(report,out,indent=2,allow_nan=False);out.write('\n');out.flush();os.fsync(out.fileno())
  os.chmod(tmp,0o640);os.replace(tmp,RESULT)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 print('6207_RESEARCH_TO_ORDER_PREFLIGHT','ACCOUNT_BOUND',report.get('account_identity_verified',False),
  'PRECOMMITTED_CANDIDATES',len(report['candidates']),'ORDERS',0,'BLOCKED',bool(report['blockers']))
 return report
if __name__=='__main__':run()
