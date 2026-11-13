#!/usr/bin/env python3
"""ABUTRON causal PROSPECTIVE DEMO market-outcome study V2.
An entry is always a *future* M5 open after the first captured decision.
Read-only: cannot place orders, enable accounts, modify positions or EAs.
"""
from __future__ import annotations
import datetime as dt,json,math,os,sqlite3,sys,hashlib,tempfile,grp
from pathlib import Path
sys.path[:0]=['/opt/apex/runtime','/opt/apex-client-mt5/quant-first']
import abutron_entry_forward_v1 as prior
import abutron_entry_model_v1 as strategy

ROOT=Path('/var/lib/abutron-quant-first')
DB=ROOT/'entry-model-causal-v2.sqlite3'
REPORT=ROOT/'entry-model-causal-v2-latest.json'
COST=prior.COST
MICRO=ROOT/'broker-native-cost-evidence-latest.json'
MODEL=prior.MODEL
MAX_SIGNAL_AGE_S=180
HOLD_BARS=12
SCHEMA='abutron.quant.causal_forward_market_outcome.v2'

def init_db(c):
 c.execute("""CREATE TABLE IF NOT EXISTS observed(
  symbol TEXT NOT NULL,model TEXT NOT NULL,signal_m5_start INTEGER NOT NULL,
  first_observed_utc TEXT NOT NULL,signal_age_sec REAL NOT NULL,
  planned_entry_m5_start INTEGER,
  side TEXT NOT NULL,atr REAL NOT NULL,signal_bar_hash TEXT NOT NULL,
  model_sha256 TEXT NOT NULL,cost_sha256 TEXT NOT NULL,
  stop_floor REAL NOT NULL,commission_per_lot REAL NOT NULL,
  usd_per_price_point_per_lot REAL NOT NULL,
  broker_spread_p95_bps REAL NOT NULL,
  status TEXT NOT NULL,entry_price REAL,exit_price REAL,exit_reason TEXT,
  gross_return_bps REAL,net_0bps REAL,net_1bps REAL,net_5bps REAL,
  net_10bps REAL,resolved_utc TEXT,
  PRIMARY KEY(symbol,model,signal_m5_start)
 )""")
 c.execute('CREATE INDEX IF NOT EXISTS causal_pending ON observed(status,planned_entry_m5_start)')

def planned_entry_ts(observed_time):
 # Strictly after capture; never uses the already-past next open of the signal candle.
 if not math.isfinite(observed_time) or observed_time<=0:raise ValueError('INVALID_OBSERVATION_TIME')
 entry=(int(observed_time)//300+1)*300
 if entry<=observed_time or entry-observed_time>300:raise ValueError('NOT_A_FUTURE_M5_OPEN')
 return entry

def capture(c,now,suggestions,cost,spreads,modelhash,costhash):
 observed=accepted=rejected=0
 nowts=now.timestamp()
 for symbol,(bar,atr,picks) in suggestions.items():
  price=cost['instruments'][symbol]
  micro=spreads['spreads'][symbol]
  floor=float(price['minimum_broker_stop_price_distance'])
  comm=float(price['commission_usd_roundtrip_per_lot_median'])
  p95=float(micro['spread_bps_p95'])
  unit=float(price['ordercalcprofit_usd_per_price_point_per_lot'])
  equity=float(cost['research_reference_equity_usd'])
  minvol=float(price['minimum_volume'])
  if not all(math.isfinite(x) and x>0 for x in (atr,unit,equity,minvol)) or p95<0 or comm<0:
   raise ValueError('BROKER_CONTRACT_OR_COST_INVALID')
  if floor<0:raise ValueError('BROKER_STOP_FLOOR_INVALID')
  signalclose=int(bar['time'])+300
  age=nowts-signalclose
  if age<0:raise ValueError('FUTURE_CANDLE_NOT_COMPLETED')
  entry=planned_entry_ts(nowts)
  assert entry>=signalclose and entry>nowts
  minrisk=minvol*unit*max(floor*1.02,1.2*atr)
  for model,side in picks.items():
   if model not in strategy.STRATEGIES or side not in ('BUY','SELL'):
    raise ValueError('UNKNOWN_DECISION')
   observed+=1
   if age>MAX_SIGNAL_AGE_S:
    status='REJECTED_SOURCE_SIGNAL_TOO_OLD';rejected+=1
   elif minrisk>equity*.001:
    status='REJECTED_MIN_VOLUME_RISK_GT_POINT_ONE_PERCENT';rejected+=1
   else:
    status='WAITING_FOR_GENUINELY_FUTURE_ENTRY';accepted+=1
   c.execute("""INSERT OR IGNORE INTO observed(
     symbol,model,signal_m5_start,first_observed_utc,signal_age_sec,
     planned_entry_m5_start,side,atr,signal_bar_hash,model_sha256,cost_sha256,
     stop_floor,commission_per_lot,usd_per_price_point_per_lot,
     broker_spread_p95_bps,status)
     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
     (symbol,model,int(bar['time']),now.isoformat(),round(age,3),
      entry,side,atr,prior.feed.digest(bar),modelhash,costhash,
      floor,comm,unit,p95,status))
 return observed,accepted,rejected

def settle(c,now,market,modelhash,costhash):
 measured=invalid=0
 rows=c.execute("""SELECT symbol,model,signal_m5_start,first_observed_utc,
   signal_age_sec,planned_entry_m5_start,side,atr,signal_bar_hash,
   model_sha256,cost_sha256,stop_floor,commission_per_lot,
   usd_per_price_point_per_lot,broker_spread_p95_bps
   FROM observed WHERE status='WAITING_FOR_GENUINELY_FUTURE_ENTRY'""").fetchall()
 for sym,model,bar,first,age,entry,side,atr,digest,ms,cs,floor,comm,unit,p95 in rows:
  observed=dt.datetime.fromisoformat(first)
  assert observed.tzinfo is not None
  if not entry>observed.timestamp() or not 0<=age<=MAX_SIGNAL_AGE_S:
   raise ValueError('FUTURE_ENTRY_CAUSAL_CONTRACT_BROKEN')
  if ms!=modelhash or cs!=costhash:
   c.execute("""UPDATE observed SET status='SOURCE_OR_COST_CHANGED_INVALID',
       resolved_utc=? WHERE symbol=? AND model=? AND signal_m5_start=?""",
       (now.isoformat(),sym,model,bar));invalid+=1
   continue
  bars=market[sym]['M5']
  sourcebar=next((x for x in bars if int(x['time'])==bar),None)
  if sourcebar is None:
   if bars[-1]['time']-bar>100*300:
    c.execute("""UPDATE observed SET status='SIGNAL_CANDLE_NOT_VERIFIABLE',
       resolved_utc=? WHERE symbol=? AND model=? AND signal_m5_start=?""",
      (now.isoformat(),sym,model,bar));invalid+=1
   continue
  if prior.feed.digest(sourcebar)!=digest:
   c.execute("""UPDATE observed SET status='ORIGINAL_SIGNAL_CANDLE_REVISED',
      resolved_utc=? WHERE symbol=? AND model=? AND signal_m5_start=?""",
      (now.isoformat(),sym,model,bar));invalid+=1
   continue
  idx=next((i for i,x in enumerate(bars) if int(x['time'])==entry),None)
  if idx is None:
   if bars[-1]['time']>entry+300:
    c.execute("""UPDATE observed SET status='MISSING_PLANNED_ENTRY_CANDLE',
       resolved_utc=? WHERE symbol=? AND model=? AND signal_m5_start=?""",
       (now.isoformat(),sym,model,bar));invalid+=1
   continue
  if idx==0 or idx+HOLD_BARS>len(bars):continue
  seq=[(int(x['time']),float(x['open']),float(x['high']),
        float(x['low']),float(x['close'])) for x in bars]
  outcome=strategy.price_outcome(seq,idx-1,side,atr,floor,hold=HOLD_BARS)
  if outcome is None:
   c.execute("""UPDATE observed SET status='BROKER_BAR_GAP_OR_STOP_RULE_INVALID',
      resolved_utc=? WHERE symbol=? AND model=? AND signal_m5_start=?""",
      (now.isoformat(),sym,model,bar));invalid+=1
   continue
  net0=outcome['gross_bps']-comm/(outcome['entry']*unit)*10000-p95
  nets=(net0,net0-1,net0-5,net0-10)
  c.execute("""UPDATE observed SET status='PROSPECTIVE_MARKET_OUTCOME_MEASURED',
    entry_price=?,exit_price=?,exit_reason=?,gross_return_bps=?,
    net_0bps=?,net_1bps=?,net_5bps=?,net_10bps=?,resolved_utc=?
    WHERE symbol=? AND model=? AND signal_m5_start=?""",
    (outcome['entry'],outcome['exit'],outcome['reason'],outcome['gross_bps'],
     *nets,now.isoformat(),sym,model,bar))
  measured+=1
 return measured,invalid

def report(c,now,counts,measured,invalid,modelhash,costhash):
 rows=c.execute("""SELECT symbol,model,status,net_10bps,signal_age_sec,
   first_observed_utc,planned_entry_m5_start FROM observed
   ORDER BY first_observed_utc,model""").fetchall()
 summaries={}
 for sym in prior.feed.SYMS:
  summaries[sym]={}
  for model in strategy.STRATEGIES:
   sub=[x for x in rows if x[0]==sym and x[1]==model]
   net=[x[3] for x in sub if x[2]=='PROSPECTIVE_MARKET_OUTCOME_MEASURED' and x[3] is not None]
   summaries[sym][model]={
    'signal_observations':len(sub),
    'accepted_future_entries':sum(x[2] in ('WAITING_FOR_GENUINELY_FUTURE_ENTRY','PROSPECTIVE_MARKET_OUTCOME_MEASURED') for x in sub),
    'rejected_stale_or_risk':sum(x[2].startswith('REJECTED_') for x in sub),
    'fully_future_market_outcomes':len(net),
    'net10_mean_bps':round(sum(net)/len(net),4) if net else None,
    'broker_order_acknowledged_from_model':0}
 examples=[{'symbol':sym,'model':model,'status':status,'signal_delay_sec':round(lag,2),
   'capture_utc':observed,'planned_future_entry_utc':dt.datetime.fromtimestamp(entry,dt.timezone.utc).isoformat()}
   for sym,model,status,_,lag,observed,entry in rows[-12:]]
 return {'schema':SCHEMA,'checked_at_utc':now.isoformat(),
   'status':'RESEARCH_ONLY_NO_TRADING',
   'definition':'ENTRY_AT_FIRST_FUTURE_M5_OPEN_AFTER_THE_TIMESTAMPED_DECISION',
   'max_causal_signal_lag_sec':MAX_SIGNAL_AGE_S,
   'entry_guaranteed_after_first_observed':True,
   'source':'DERIV_DEMO_NATIVE_COMPLETED_M5_H1_BARS',
   'historical_model_not_identical_to_this_delayed_execution_variant':True,
   'cost_model':'HISTORICAL_AUTHENTICATED_DEAL_COMMISSIONS_PLUS_BROKER_NATIVE_TICK_SPREAD_P95',
   'slippage_bps_stress':[0,1,5,10],
   'realized_execution_slippage_unknown':True,
   'latest_decisions_seen':counts[0],
   'latest_decisions_accepted_by_time_and_risk':counts[1],
   'latest_decisions_rejected':counts[2],
   'latest_forward_outcomes_resolved':measured,
   'latest_invalidated_outcomes':invalid,
   'total_valid_outcomes':sum(x[2]=='PROSPECTIVE_MARKET_OUTCOME_MEASURED' for x in rows),
   'total_rejected_stale_or_risk':sum(x[2].startswith('REJECTED_') for x in rows),
   'total_current_awaiting_future_entry_or_exit':sum(x[2]=='WAITING_FOR_GENUINELY_FUTURE_ENTRY' for x in rows),
   'strategy_model_sha256':modelhash,'cost_model_sha256':costhash,
   'new_orders_submitted':0,'broker_fills_from_this_variant':0,
   'can_promote_to_trading':False,
   'models':summaries,'samples':examples}

def main():
 now,market,cost,modelhash,costhash=prior.verified_inputs()
 spread=json.loads(MICRO.read_text())
 if (spread.get('schema')!='abutron.deriv.microstructure_cost_deal_evidence.v1' or
    len(spread.get('spreads',{}))!=5):raise ValueError('BROKER_TICK_SPREAD_EVIDENCE_NOT_VERIFIED')
 # Preserve source integrity: measured costs from a prior authenticated window.
 if MICRO.is_symlink() or not MICRO.is_file():raise ValueError('UNTRUSTED_MICROSTRUCTURE_SOURCE')
 choices=prior.candidate_decisions(market)
 if DB.is_symlink() or REPORT.is_symlink():raise ValueError('UNTRUSTED_DATA_DESTINATION')
 with sqlite3.connect(str(DB),timeout=12) as conn:
  conn.execute('PRAGMA busy_timeout=12000')
  conn.execute('BEGIN IMMEDIATE')
  init_db(conn)
  counts=capture(conn,now,choices,cost,spread,modelhash,costhash)
  measured,invalid=settle(conn,now,market,modelhash,costhash)
  r=report(conn,now,counts,measured,invalid,modelhash,costhash)
  conn.commit()
  assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 DB.chmod(0o640);os.chown(DB,0,grp.getgrnam('apexagent').gr_gid)
 fd,tmp=tempfile.mkstemp(prefix='.entry-causal-',dir=REPORT.parent)
 try:
  with os.fdopen(fd,'w') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o640);os.chown(tmp,0,grp.getgrnam('apexagent').gr_gid)
  os.replace(tmp,REPORT)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 print('CAUSAL_FORWARD_RESEARCH_V2','DECISIONS',counts[0],
       'ACCEPTED',counts[1],'REJECTED',counts[2],
       'PROSPECTIVE_OUTCOMES_NOW',measured,'PROSPECTIVE_OUTCOMES_TOTAL',r['total_valid_outcomes'],
       'BROKER_ORDERS',0)
if __name__=='__main__':main()
