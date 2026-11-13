#!/usr/bin/env python3
"""FP-only original TradingAgents/Qwen advisory review. NO broker or order I/O."""
import datetime as dt,fcntl,hashlib,json,os,re,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,'/opt/apex-client-mt5')
import abutron_selective_tradingagents_v1 as selective
ROOT=Path('/var/lib/abutron-fp-scanner')
SCANNER=ROOT/'latest.json'
OUT=ROOT/'ai'
MODEL='qwen2.5:1.5b-instruct'
BROKER_HISTORY=Path('/var/lib/apex/operator-live/fp-native-history.json')
NATIVE_FEED=Path('/var/lib/abutron-fpmarkets-feed/partial/35b81a287b6a030f2f46ff426b135e6c.json')

def prioritization_proofs():
 # Optional hints only. Invalid or stale broker proofs cannot authorize an order.
 # No fallback order creation or relaxation of the native execution checks.
 try:
  history=safe_read(BROKER_HISTORY)
  feed=safe_read(NATIVE_FEED)
  if (history.get('history_verified_from_mt5') is not True
      or history.get('broker')!='FP Markets'
      or history.get('environment')!='DEMO'
      or not 0<=time.time()-stamp(history.get('generated_at_utc'))<=150
      or not 0<=time.time()-stamp(feed.get('checked_at_utc'))<=150
      or type(history.get('open_positions_count')) is not int
      or len(history.get('positions',[]))!=history['open_positions_count']):
   return set(),{},{}
  occupied={p.get('symbol') for p in history['positions']}
  if not all(isinstance(x,str) for x in occupied):return set(),{},{}
  return occupied,feed.get('mapping',{}),feed.get('quotes',{})
 except (OSError,ValueError,TypeError,KeyError,AttributeError):
  return set(),{},{}

def priority_for_review(item,occupied,mapping,quotes):
 # A lower score is reviewed first, without excluding any scanner proposal.
 symbol=item['symbol'];m=mapping.get(symbol,{})
 is_occupied=bool(m.get('actual') in occupied)
 impossible=False
 if symbol=='SP500' and item.get('proposal')=='SELL' and m.get('actual')=='US500':
  q=quotes.get(symbol,{})
  vals=(m.get('min_lot'),m.get('contract_size'),q.get('bid'))
  if all(type(x) in (int,float) and x>0 for x in vals):
   # At a price floor of zero the broker cannot deliver a USD100 SELL TP.
   impossible=vals[0]*vals[1]*vals[2]<98
 return (int(is_occupied),int(impossible))

SYMBOLS=('XAUUSD','BTCUSD','EURUSD','GBPUSD','USDJPY','AUDUSD',
         'US100','US30','SP500','GER40','USOIL','USDCHF','NZDUSD')

def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def stamp(s):
 d=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('NAIVE_TIMESTAMP')
 return d.timestamp()
def safe_read(p):
 if p.is_symlink() or not p.is_file() or p.stat().st_size>4_000_000:
  raise ValueError('FP_RESEARCH_SOURCE_INVALID')
 x=json.loads(p.read_text())
 if not isinstance(x,dict):raise ValueError('RESEARCH_NOT_OBJECT')
 return x
def atomic(p,doc):
 p.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=str(p.parent),prefix='.'+p.name+'.')
 try:
  with os.fdopen(fd,'w') as f:
   json.dump(doc,f,separators=(',',':'),allow_nan=False)
   f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o640);os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def parse_decision(answer):
 match=re.search(r'^\s*(BUY|SELL|HOLD)\b',str(answer).upper())
 return match.group(1) if match else 'HOLD'
def validate(doc,now=None):
 now=time.time() if now is None else now
 if (doc.get('schema') not in ('abutron.fpmarkets.apex.scanner.readonly.v1',
                                 'abutron.fpmarkets.apex.scanner.partial.readonly.v1')
  or doc.get('source')!='FP Markets DEMO MT5 native completed candles'
  or doc.get('orders_enabled') is not False
  or doc.get('execution_authorized') is not False
  or doc.get('status') not in ('FP_SCANNER_READONLY_ACTIVE','FP_SCANNER_PARTIAL_READONLY')
  or not -30<=now-stamp(doc.get('checked_at_utc'))<=260):
  raise ValueError('FP_SCANNER_SOURCE_UNTRUSTED_OR_STALE')
 if doc.get('status')=='FP_SCANNER_PARTIAL_READONLY':
  if (doc.get('schema')!='abutron.fpmarkets.apex.scanner.partial.readonly.v1'
      or doc.get('policy')!='PARTIAL_RESEARCH_NOT_CERTIFIED_NO_TRADES'
      or doc.get('account_controls_modified') is not False):
   raise ValueError('FP_PARTIAL_RESEARCH_POLICY_INVALID')
 else:
  if doc.get('schema')!='abutron.fpmarkets.apex.scanner.readonly.v1':
   raise ValueError('FP_COMPLETE_RESEARCH_SCHEMA_INVALID')
 items=doc.get('instruments')
 if not isinstance(items,list) or len(items)!=13 or {a.get('symbol') for a in items}!=set(SYMBOLS):
  raise ValueError('FP_SCANNER_SYMBOL_UNIVERSE_INVALID')
 for x in items:
  if x.get('proposal') not in ('BUY','SELL','HOLD') or x.get('orders_enabled') is not False:
   raise ValueError('FP_SCANNER_PROPOSAL_INVALID')
  if x.get('available') is False:
   # A missing/ambiguous broker symbol always stays HOLD. The retired
   # SMC/ICT labels are not a route to create or approve a candidate.
   retired=(doc.get('setup_lifecycle_version')=='RETIRED_NOT_A_TRADE_ENTRY_SOURCE'
            and x.get('smc',{}).get('status')=='REMOVED'
            and x.get('ict',{}).get('status')=='REMOVED')
   prior=(x.get('smc',{}).get('status')=='VETO'
          and x.get('ict',{}).get('status')=='VETO')
   if (doc.get('status')!='FP_SCANNER_PARTIAL_READONLY' or
       x.get('proposal')!='HOLD' or x.get('candidate_for_ai') is not False or
       x.get('final_decision')!='HOLD' or
       x.get('m5_closed_bar') is not None or x.get('execution_authorized') is not False
       or not (retired or prior)):
    raise ValueError('FP_UNAVAILABLE_SYMBOL_CANNOT_BE_REVIEWED')
   continue
  if type(x.get('m5_closed_bar')) is not int:
   raise ValueError('FP_SCANNER_BAR_TIME_INVALID')
 if doc.get('status')=='FP_SCANNER_PARTIAL_READONLY':
  available={r['symbol'] for r in items if r.get('available') is True}
  missing={r['symbol'] for r in items if r.get('available') is False}
  if (not available or available & missing or
      len(available)!=doc.get('symbols_verified') or
      doc.get('timeframe_series')!=6*len(available) or
      missing!=set(doc.get('symbols_unavailable',[]))):
   raise ValueError('FP_PARTIAL_REVIEW_COVERAGE_INVALID')
 return items

def evidence_for(row):
 # Exact same deterministic broker-only fingerprint as the native order router.
 payload,digest=selective.validate_evidence('FP Markets DEMO MT5',
    row['symbol'],row['m5_closed_bar'],row['proposal'],row['indicators'])
 return json.dumps(payload,separators=(',',':'),sort_keys=True)


def review_one(row,call_model=None):
 evidence=evidence_for(row)
 if call_model is None:
  result=selective.review('FP Markets DEMO MT5',row['symbol'],
     row['m5_closed_bar'],row['proposal'],row['indicators'])
  direction=result['direction']
  answer=result['analysis']
  status='MODEL_REVIEW_COMPLETED' if result['approved'] else 'MODEL_RESPONSE_INVALID'
  latency=result['latency_seconds']
 else:
  # Test-only injection, never used by the scheduled production service.
  answer=str(call_model(evidence)).strip()[:160]
  direction=answer if answer in ('BUY','SELL','HOLD') else 'HOLD'
  status='MODEL_REVIEW_COMPLETED' if answer in ('BUY','SELL','HOLD') else 'MODEL_RESPONSE_INVALID'
  latency=None
 return {'symbol':row['symbol'],'m5_closed_bar':row['m5_closed_bar'],
  'scanner_proposal':row['proposal'],'reviewed_at_utc':utc(),
  'evidence_sha256':hashlib.sha256(evidence.encode()).hexdigest(),
  'llm_direction':direction,'agreed':direction==row['proposal'],
  'model':MODEL,'framework':'TradingAgentsGraph selective broker-only analyst',
  'latency_seconds':latency,'analysis':answer[:160],
  'evidence_status':status,'execution_authorized_by_llm':False}


def invoke(payload):
 raise RuntimeError('LEGACY_DIRECT_OLLAMA_PATH_RETIRED')


def one_pass(doc=None,old=None,model_fn=None):
 if doc is None:
  # Single source of truth: the native FP order router verifies partial-latest.
  # Reviewing a different scanner would create an unreviewed execution path.
  doc=safe_read(ROOT/'partial-latest.json')
 items=validate(doc)
 old=old if old is not None else safe_read(OUT/'latest.json') if (OUT/'latest.json').exists() else {}
 cached={x['symbol']:x for x in old.get('reviews',[]) if x.get('symbol') in SYMBOLS}
 # Original scanner candidates only; stale M5 bars must HOLD cleanly.
 def timely(item):
  t=item.get('m5_closed_bar')
  return type(t) is int and 0<=time.time()-(t+300)<=225
 eligible=[x for x in items if x.get('available') is True
           and x['proposal'] in ('BUY','SELL')
           and x.get('candidate_for_ai') is True and timely(x)]
 def current(item):
  if not timely(item):return False
  r=cached.get(item['symbol'],{})
  if (r.get('m5_closed_bar')!=item['m5_closed_bar']
      or r.get('scanner_proposal')!=item['proposal']
      or r.get('evidence_status') not in ('MODEL_REVIEW_COMPLETED','MODEL_RESPONSE_INVALID')):
   return False
  try:
   return r.get('evidence_sha256')==hashlib.sha256(evidence_for(item).encode()).hexdigest()
  except (ValueError,TypeError,KeyError):
   return False
 pending=[x for x in eligible if not current(x)]
 if pending:
  occupied,mapping,quotes=prioritization_proofs()
  row=min(pending,key=lambda x:(*priority_for_review(x,occupied,mapping,quotes),
                     cached.get(x['symbol'],{}).get('reviewed_at_utc',''),x['symbol']))
  cached[row['symbol']]=review_one(row,model_fn)
 decisions=[]
 for row in items:
  review=cached.get(row['symbol'],{})
  matched=(row['proposal'] in ('BUY','SELL') and current(row)
       and review.get('llm_direction')==row['proposal']
       and review.get('evidence_status')=='MODEL_REVIEW_COMPLETED')
  all_positive=bool(matched)
  decisions.append({'symbol':row['symbol'],'m5_closed_bar':row['m5_closed_bar'],
   'scanner_proposal':row['proposal'],
   'ai':'PASS' if matched else 'VETO_OR_PENDING',
   'smc':'REMOVED','ict':'REMOVED',
   'research_direction':row['proposal'] if all_positive else 'HOLD',
   'final_execution_decision':'HOLD',
   'execution_authorized':False,'orders_enabled':False})
 return {'schema':'abutron.fpmarkets.apex.ai_selective_tradingagents.v1',
   'status':'FP_AI_RESEARCH_ONLY','reviewed_at_utc':utc(),
   'native_scanner_at_utc':doc['checked_at_utc'],
   'model':MODEL,'candidates':len(eligible),
   'new_reviews':int(bool(pending)),
   'research_all_positive':sum(x['research_direction']!='HOLD' for x in decisions),
   'orders_enabled':False,'execution_authorized':False,'account_controls_modified':False,
   'reviews':[cached[row['symbol']] for row in items
              if row['symbol'] in cached and current(row)],
   'decisions':decisions}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 with (OUT/'review.lock').open('a+') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print('FP_AI_REVIEW_BUSY');return
  try:
   doc=one_pass()
   atomic(OUT/'latest.json',doc)
   print(json.dumps({k:doc[k] for k in ('status','candidates','new_reviews','research_all_positive','orders_enabled')}))
  except (OSError,ValueError,TypeError,KeyError,RuntimeError) as e:
   atomic(OUT/'last_error.json',{'status':'BLOCKED','reason':str(e)[:160],
       'orders_enabled':False,'reviewed_at_utc':utc()})
   print('FP_AI_REVIEW_BLOCKED '+str(e)[:180],file=sys.stderr)
   raise SystemExit(1)
if __name__=='__main__':main()
