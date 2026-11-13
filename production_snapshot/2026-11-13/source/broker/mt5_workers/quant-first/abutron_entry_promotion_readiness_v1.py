#!/usr/bin/env python3
"""ABUTRON read-only model-promotion eligibility: never approves orders itself."""
import datetime as dt,hashlib,json,math,os,sqlite3,statistics,tempfile,grp
from pathlib import Path
HIST=Path('/var/backups/abutron-tick-slippage-research-20261106T2303Z/CAUSAL_DELAY_MATCHED_HISTORICAL_REPLAY_V2.json')
COST=Path('/var/backups/abutron-cost-research-20261106T2235Z/BROKER_COST_REFERENCE_EQUITY_V2.json')
FORWARD=Path('/var/lib/abutron-quant-first/entry-model-causal-v2-latest.json')
FWD_DB=Path('/var/lib/abutron-quant-first/entry-model-causal-v2.sqlite3')
POLICY=Path('/etc/abutron/optionc-live-010.json')
ACCOUNT_DB=Path('/var/lib/apex-signup/accounts.sqlite3')
FEED_ROOT=Path('/var/lib/apex-client-feed')
OUTPUT=Path('/var/lib/abutron-quant-first/entry-promotion-readiness-latest.json')
MODELPATH=Path('/opt/apex-client-mt5/quant-first/abutron_entry_model_v1.py')
MIN_TRAIN=40;MIN_VALID=30;MIN_PROSPECTIVE=30
def import_json(p):
 if p.is_symlink() or not p.is_file() or p.stat().st_size>4_000_000:raise ValueError('INVALID_EVIDENCE_FILE')
 return json.loads(p.read_text())
def live_forward_stats(db,model,symbol):
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
  c.execute('pragma query_only=ON')
  raw=c.execute("SELECT net_10bps FROM observed WHERE model=? AND symbol=? AND status='PROSPECTIVE_MARKET_OUTCOME_MEASURED' ORDER BY signal_m5_start",(model,symbol)).fetchall()
  invalid=c.execute("select count(*) from observed where model=? and symbol=? and status in ('SOURCE_OR_COST_CHANGED_INVALID','SIGNAL_CANDLE_NOT_VERIFIABLE','ORIGINAL_SIGNAL_CANDLE_REVISED','MISSING_PLANNED_ENTRY_CANDLE','BROKER_BAR_GAP_OR_STOP_RULE_INVALID')",(model,symbol)).fetchone()[0]
 vals=[float(row[0]) for row in raw if row[0] is not None and math.isfinite(row[0])]
 n=len(vals);avg=statistics.mean(vals) if n else None
 lb=avg-1.96*statistics.stdev(vals)/math.sqrt(n) if n>1 else None
 return {'n':n,'mean_net_10bps':round(avg,4) if avg is not None else None,
         'lower_95_net_10bps':round(lb,4) if lb is not None else None,
         'invalidated':invalid}
def main():
 now=dt.datetime.now(dt.timezone.utc)
 hist=import_json(HIST);forward=import_json(FORWARD);cost=import_json(COST);policy=import_json(POLICY)
 if hist.get('schema')!='abutron.quant.causal_delay_historical_matching.v2':raise ValueError('MISSING_HISTORICAL_MODEL_EVIDENCE')
 if forward.get('schema')!='abutron.quant.causal_forward_market_outcome.v2':raise ValueError('MISSING_GENUINE_FORWARD_JOURNAL')
 if forward.get('strategy_model_sha256')!=hashlib.sha256(MODELPATH.read_bytes()).hexdigest():raise ValueError('FORWARD_MODEL_HASH_CHANGED')
 if forward.get('cost_model_sha256')!=hashlib.sha256(COST.read_bytes()).hexdigest():raise ValueError('FORWARD_COST_HASH_CHANGED')
 if policy.get('demo_only') is not True or policy.get('risk_budget_pct_per_trade')!=0.1 or policy.get('portfolio_ceiling_pct')!=20:
  raise ValueError('RISK_POLICY_NOT_APPROVED')
 allow=policy.get('deriv_connection_allowlist')
 if not isinstance(allow,list) or len(allow)!=1:raise ValueError('DEMO_ONE_ACCOUNT_ALLOWLIST_INVALID')
 with sqlite3.connect('file:'+str(ACCOUNT_DB)+'?mode=ro',uri=True) as db:
  c=db.execute("select account_reference,status from apex_mt5_connections where id=? AND broker='Deriv' AND environment='DEMO'",(allow[0],)).fetchone()
 if not c or not str(c[0]).endswith('6207'):raise ValueError('DEMO_ALLOWLIST_ACCOUNT_MISMATCH')
 feed=import_json(FEED_ROOT/(allow[0]+'.json'))
 account=feed.get('account',{})
 account_state={
  'suffix':'6207','status':c[1],'broker_data_verified':feed.get('broker_data_verified') is True,
  'open_positions':account.get('open_positions'),'all_positions_protected':account.get('all_positions_protected'),
  'equity_usd_at_check':account.get('equity_usd'),
 }
 model_results=[]
 for symbol,data in sorted(hist['instruments'].items()):
  for name in ('trend_pullback','failed_breakout','ema_reversion','range_sweep','trend_breakout','streak_fade'):
   development=data['entry_models']['development'][name]
   validation=data['entry_models']['validation'][name]
   d=development['cost_scenarios']['5'];v=validation['cost_scenarios']['5']
   future=live_forward_stats(FWD_DB,name,symbol)
   hist_pass=(development['trades']>=MIN_TRAIN and validation['trades']>=MIN_VALID and d['normal_95_lower_bps'] is not None and v['normal_95_lower_bps'] is not None and d['normal_95_lower_bps']>0 and v['normal_95_lower_bps']>0)
   fut_pass=future['n']>=MIN_PROSPECTIVE and future['lower_95_net_10bps'] is not None and future['lower_95_net_10bps']>0 and future['invalidated']==0
   model_results.append({'symbol':symbol,'model':name,'historical_pass':hist_pass,'forward_pass':fut_pass,'forward':future})
 blockers=[]
 if not any(z['historical_pass'] and z['forward_pass'] for z in model_results):blockers.append('NO_HISTORICAL_AND_PROSPECTIVE_POSITIVE_NET_COST_EDGE')
 blockers.append('MATCHED_HISTORICAL_HOLDOUT_PREVIOUSLY_INSPECTED_FRESH_FORWARD_PROOF_REQUIRED')
 if account_state['open_positions']!=0:blockers.append('BROKER_ACCOUNT_HAS_EXISTING_PROTECTED_POSITION')
 if account_state['status']!='CONNECTED' or not account_state['broker_data_verified']:blockers.append('BROKER_ACCOUNT_NOT_FRESHLY_AUTHENTICATED')
 blockers+=['ACTUAL_HISTORICAL_SPREAD_SLIPPAGE_NOT_VERIFIED',
            'NEW_QUANT_MODEL_NOT_CONNECTED_TO_NATIVE_ORDER_ROUTER',
            'NO_INDEPENDENT_FINAL_PROSPECTIVE_MODEL_APPROVAL']
 report={'schema':'abutron.apex.model.promotion.readiness.v1','checked_at_utc':now.isoformat(),
   'result':'BLOCKED','order_submission_allowed':False,'new_orders_sent':0,
   'risk_mode':'DEMO_0P10_PERCENT_PER_TRADE_20_PERCENT_PORTFOLIO_CEILING',
   'research_data_source':'DERIV_BROKER_NATIVE_COMPLETED_CANDLES',
   'model_comparison':'30_PREDEFINED_SYMBOL_STRATEGY_PAIRS',
   'prospective_outcome_definition':'FIRST_FUTURE_M5_OPEN_AFTER_RECORDED_SIGNAL_NOT_REAL_ORDER_FILLS',
   'causal_forward_report_latest_utc':forward.get('checked_at_utc'),
   'previous_v1_four_late_signals_disqualified':True,
   'historical_delayed_entry_variant_matched':True,
   'historical_delayed_entry_slippage_stress_bps':5,
   'old_historical_holdout_previously_inspected':True,
   'broker_actual_execution_costs_complete':False,
   'broker_ack_for_new_model_verified':False,
   'blockers':blockers,'allowed_account':account_state,
   'historical_pass_count':sum(z['historical_pass'] for z in model_results),
   'forward_positive_lower95_count':sum(z['forward_pass'] for z in model_results),
   'forward_outcomes_total':sum(z['forward']['n'] for z in model_results),
   'models':model_results}
 fd,tmp=tempfile.mkstemp(prefix='.entry-readiness-',dir=OUTPUT.parent)
 try:
  with os.fdopen(fd,'w') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o640);os.chown(tmp,0,grp.getgrnam('apexagent').gr_gid)
  os.replace(tmp,OUTPUT)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 print('PROMOTION_READONLY',report['result'],'FWD_OUTCOMES',report['forward_outcomes_total'],'BLOCKERS',','.join(report['blockers']),'ORDERS',0)
if __name__=='__main__':main()
