#!/usr/bin/python3
"""ABUTRON dual-broker RESEARCH archive: Deriv native SQLite plus 2 isolated FP native candle/quote streams.
Read-only broker feeds, append-only isolated research DB. No order capability, no trading switches.
"""
from __future__ import annotations
import datetime as dt,hashlib,importlib.util,json,math,os,sqlite3,stat,statistics,time,tempfile
from pathlib import Path
from collections import defaultdict

FP_FEED=Path('/var/lib/abutron-fpmarkets-feed')
FP_CODE=Path('/opt/apex-client-mt5/fpmarkets-feed/fp_feed_collect.py')
CRM=Path('/var/lib/apex-signup/accounts.sqlite3')
DERIV=Path('/var/lib/apex/precision-history/closed-candles.sqlite3')
OUT=Path(os.environ.get('ABUTRON_DUAL_BROKER_RESEARCH_OUT','/var/lib/abutron-quant-first/dual-broker'))
FRAMES={'M1':60,'M5':300,'M15':900,'H1':3600,'H4':14400,'D1':86400}
SCHEMA='abutron.apex.dualbroker.history_research.readonly.v1'
MAX_BYTES=2_000_000
def clock():
 return dt.datetime.now(dt.timezone.utc).isoformat()
def epoch(iso):
 x=dt.datetime.fromisoformat(str(iso).replace('Z','+00:00'))
 if x.tzinfo is None:raise ValueError('NAIVE_BROKER_TIMESTAMP')
 return x.timestamp()
def attested_json(path):
 st=path.lstat()
 if not stat.S_ISREG(st.st_mode) or not 100<=st.st_size<=MAX_BYTES:raise ValueError('SOURCE_NOT_REGULAR_OR_SIZE')
 age=time.time()-st.st_mtime
 if not -10<=age<=150:raise ValueError('BROKER_PUBLISHED_SOURCE_STALE')
 fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
 try:
  before=os.fstat(fd)
  b=os.read(fd,MAX_BYTES+1)
  after=os.fstat(fd)
 finally:os.close(fd)
 if (len(b)!=st.st_size or before.st_ino!=after.st_ino or
     before.st_mtime_ns!=after.st_mtime_ns or len(b)>MAX_BYTES):
  raise ValueError('BROKER_SOURCE_RACE_OR_TRUNCATION')
 doc=json.loads(b)
 if not isinstance(doc,dict):raise ValueError('SOURCE_NOT_OBJECT')
 return doc,hashlib.sha256(b).hexdigest()
def readonly_db(path):
 c=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=10)
 c.execute('PRAGMA query_only=ON')
 return c
def load_fp_contract():
 spec=importlib.util.spec_from_file_location('fp_native_research_contract',FP_CODE)
 if not spec or not spec.loader:raise ValueError('FP_NATIVE_CONTRACT_MISSING')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module
def accounts():
 with readonly_db(CRM) as c:
  items=c.execute("""SELECT id,account_reference,broker_server,status,environment
    FROM apex_mt5_connections WHERE broker='FP Markets' AND
    environment='DEMO' AND status='CONNECTED'
    ORDER BY id""").fetchall()
 if len(items)!=2 or len({x[0] for x in items})!=2:raise ValueError('TWO_FP_DEMO_ACCOUNTS_NOT_VERIFIED')
 for cid,login,server,status,mode in items:
  if (not isinstance(cid,str) or len(cid)!=32 or
      not all(ch in '0123456789abcdef' for ch in cid) or
      not isinstance(login,str) or not login.isdecimal() or
      server!='FPMarketsSC-Demo' or status!='CONNECTED' or mode!='DEMO'):
   raise ValueError('FP_ACCOUNT_IDENTITY_INVALID')
 return items

def validate_account(fp,summary,cid,login,server,mode,now):
 if (fp.get('schema')!='abutron.fpmarkets.native.candles.v1' or
     fp.get('source')!='FP Markets DEMO MT5' or fp.get('account_mode')!='DEMO' or
     fp.get('broker_server')!=server or fp.get('connection_id')!=cid or
     fp.get('execution_enabled') is not False or fp.get('orders_submitted')!=0 or
     tuple(fp.get('timeframes',()))!=tuple(FRAMES) or
     not isinstance(fp.get('checked_at_utc'),str)):
  raise ValueError('FP_NATIVE_MARKET_IDENTITY_INVALID')
 if not -30<=now-epoch(fp['checked_at_utc'])<=150:raise ValueError('FP_NATIVE_MARKET_SOURCE_STALE')
 if (summary.get('schema')!='abutron.fpmarkets.feed.readonly.v1' or
     summary.get('execution_enabled') is not False or summary.get('orders_submitted')!=0 or
     not isinstance(summary.get('checked_at_utc'),str)):
  raise ValueError('FP_NATIVE_SUMMARY_INVALID')
 if not -30<=now-epoch(summary['checked_at_utc'])<=150:raise ValueError('FP_NATIVE_SUMMARY_STALE')
 matches=[x for x in summary.get('connections',[])
          if isinstance(x,dict) and x.get('connection_id')==cid]
 if len(matches)!=1 or matches[0].get('status')!='BROKER_NATIVE_DATA_COMPLETE' or matches[0].get('mode')!='DEMO' or matches[0].get('fresh_quotes')!=13 or matches[0].get('timeframes_verified')!=78:
  raise ValueError('FP_NATIVE_COVERAGE_UNVERIFIED')
 fp_contract=load_fp_contract()
 # Real MT5 worker nonce/owner/server + signed native heartbeat, not just a copied JSON.
 fp_contract.attest(cid,server,login,mode)
 mapping,quotes,bars=fp.get('mapping'),fp.get('quotes'),fp.get('bars')
 target=fp_contract.TARGET
 if any(not isinstance(x,dict) for x in (mapping,quotes,bars)):raise ValueError('FP_MARKET_STRUCTURE_INVALID')
 if set(mapping)!=set(target) or set(quotes)!=set(target) or set(bars)!=set(target):raise ValueError('FP_13_SYMBOL_COVERAGE_INVALID')
 if len(FRAMES)!=6:raise ValueError('FRAME_CONTRACT_INVALID')
 rows=[];ticks=[];min_bars=None
 for symbol in sorted(target):
  m=mapping[symbol];q=quotes[symbol];frames=bars[symbol]
  actual=m.get('actual')
  if (m.get('status')!='MAPPED' or actual not in target[symbol] or
      m.get('trade_mode')!=4 or not isinstance(frames,dict) or
      set(frames)!=set(FRAMES) or q.get('symbol')!=actual):
   raise ValueError('FP_UNTRUSTED_ALIAS_OR_TRADE_MODE')
  bid,ask=q.get('bid'),q.get('ask')
  quote_time=q.get('time')
  offset=q.get('broker_clock_offset_seconds')
  if (type(quote_time) is not int or type(offset) is not int or abs(offset)>14*3600 or
      type(bid) not in (int,float) or
      type(ask) not in (int,float) or not math.isfinite(bid) or
      not math.isfinite(ask) or bid<=0 or ask<bid or
      q.get('broker_time_raw')-quote_time!=offset):
   raise ValueError('FP_QUOTE_UNVERIFIED')
  if not -30<=now-quote_time<=300:raise ValueError('FP_QUOTE_SOURCE_STALE')
  ticks.append((symbol,actual,int(quote_time),float(bid),float(ask),float(ask-bid)))
  for frame,seconds in FRAMES.items():
   bars_seq=frames[frame]
   if not isinstance(bars_seq,list) or not 65<=len(bars_seq)<=70:
    raise ValueError('FP_TOO_FEW_NATIVE_CANDLES')
   min_bars=len(bars_seq) if min_bars is None else min(min_bars,len(bars_seq))
   previous=0
   for bar in bars_seq:
    t=bar.get('time')
    if (type(t) is not int or t<=previous or t+seconds>now+15 or (t+offset)%seconds!=0 or
        bar.get('broker_time_raw')-t!=offset):
     raise ValueError('FP_BAR_TIMESTAMP_OR_LOOKAHEAD_INVALID')
    values=[bar.get(key) for key in ('open','high','low','close')]
    if not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in values):
     raise ValueError('FP_BAR_PRICE_INVALID')
    op,high,low,close=values
    if low>min(op,close) or high<max(op,close) or high<low:
     raise ValueError('FP_BAR_CANDLE_RANGE_INVALID')
    rows.append((symbol,actual,frame,t,*map(float,values),int(bar['broker_time_raw'])))
    previous=t
   if now-(previous+seconds)>max(2*seconds,300):
    raise ValueError('FP_FRAME_HISTORY_STALE')
 if len(rows)!=13*6*70 or len(ticks)!=13:raise ValueError('FP_NATIVE_13X6_CONTRACT_INCOMPLETE')
 return rows,ticks

def prepare_db(c):
 c.execute('PRAGMA busy_timeout=5000')
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('PRAGMA synchronous=FULL')
 c.executescript("""CREATE TABLE IF NOT EXISTS fp_candles(
    account_fingerprint TEXT NOT NULL, symbol TEXT NOT NULL, actual TEXT NOT NULL,
    timeframe TEXT NOT NULL, start_time_utc INTEGER NOT NULL,
    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
    broker_time_raw INTEGER NOT NULL,
    PRIMARY KEY(account_fingerprint,symbol,timeframe,start_time_utc)
 ) WITHOUT ROWID;
 CREATE TABLE IF NOT EXISTS fp_quotes(
    account_fingerprint TEXT NOT NULL, symbol TEXT NOT NULL, actual TEXT NOT NULL,
    observed_utc INTEGER NOT NULL, bid REAL NOT NULL, ask REAL NOT NULL,
    spread_price REAL NOT NULL,
    PRIMARY KEY(account_fingerprint,symbol,observed_utc)
 ) WITHOUT ROWID;
 CREATE TABLE IF NOT EXISTS fp_imports(
    account_fingerprint TEXT NOT NULL, sha256 TEXT NOT NULL,
    imported_utc TEXT NOT NULL, candles_added INTEGER NOT NULL,
    quote_samples_added INTEGER NOT NULL,
    PRIMARY KEY(account_fingerprint,sha256)
 ) WITHOUT ROWID;
 """)

def append_account(c,fingerprint,rows,ticks,digest):
 if not isinstance(fingerprint,str) or len(fingerprint)!=24 or not all(ch in '0123456789abcdef' for ch in fingerprint):
  raise ValueError('INVALID_ACCOUNT_FINGERPRINT')
 c.execute('BEGIN IMMEDIATE')
 try:
  # Compare ALL repeated historical prices against existing immutable bars.
  # Silent IGNORE would hide source corrections, symbol swaps or account cross-contamination.
  existing={}
  for sym,actual,frame,t,op,hi,lo,cl,raw in rows:
   r=c.execute("""SELECT actual,open,high,low,close,broker_time_raw
     FROM fp_candles WHERE account_fingerprint=? AND symbol=? AND timeframe=? AND start_time_utc=?""",
     (fingerprint,sym,frame,t)).fetchone()
   if r is not None:
    expected=(actual,op,hi,lo,cl,raw)
    if r[0]!=expected[0] or r[5]!=expected[5] or any(not math.isclose(r[i],expected[i],rel_tol=0,abs_tol=1e-10) for i in range(1,5)):
     raise ValueError('IMMUTABLE_BROKER_BAR_CONFLICT')
  before=c.total_changes
  c.executemany("""INSERT OR IGNORE INTO fp_candles
   (account_fingerprint,symbol,actual,timeframe,start_time_utc,open,high,low,close,broker_time_raw)
   VALUES(?,?,?,?,?,?,?,?,?,?)""",
   [(fingerprint,*x) for x in rows])
  new_bars=c.total_changes-before
  before=c.total_changes
  c.executemany("""INSERT OR IGNORE INTO fp_quotes
   (account_fingerprint,symbol,actual,observed_utc,bid,ask,spread_price)
   VALUES(?,?,?,?,?,?,?)""",
   [(fingerprint,*x) for x in ticks])
  new_ticks=c.total_changes-before
  c.execute("""INSERT OR IGNORE INTO fp_imports
    (account_fingerprint,sha256,imported_utc,candles_added,quote_samples_added)
    VALUES(?,?,?,?,?)""",(fingerprint,digest,clock(),new_bars,new_ticks))
  c.execute('COMMIT')
  return new_bars,new_ticks
 except:
  c.execute('ROLLBACK')
  raise

def deriv_summary():
 with readonly_db(DERIV) as c:
  if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('DERIV_NATIVE_DB_INTEGRITY_FAILED')
  date=c.execute('SELECT max(broker_generated_at_utc) FROM imports').fetchone()[0]
  if not 0<=time.time()-epoch(date)<=900:raise ValueError('DERIV_NATIVE_HISTORY_STALE')
  report=[]
  for symbol in ('Volatility 25 Index.0','Volatility 50 Index.0','Volatility 75 Index.0'):
   rows=c.execute("""SELECT timeframe,count(*),min(start_time_utc),max(start_time_utc)
      FROM candles WHERE symbol=? GROUP BY timeframe""",(symbol,)).fetchall()
   if set(x[0] for x in rows)!=set(FRAMES):raise ValueError('DERIV_NATIVE_TIMEFRAMES_MISSING')
   report.append({'symbol':symbol,'timeframes':{tf:{'bars':n,'first_utc':lo,'last_utc':hi} for tf,n,lo,hi in rows}})
 return {'broker':'Deriv','mode':'NATIVE_CLOSED_CANDLES_READONLY','symbols':report,
         'net_profitable_edge_verified':False,'orders_enabled':False}

def report(fp_reports,dbpath,deriv):
 with readonly_db(dbpath) as c:
  accounts=[]
  for item in fp_reports:
   fingerprint=item['fingerprint']
   rows=c.execute("""SELECT symbol,timeframe,count(*),min(start_time_utc),max(start_time_utc)
      FROM fp_candles WHERE account_fingerprint=? GROUP BY symbol,timeframe""",(fingerprint,)).fetchall()
   counts=defaultdict(dict)
   for sym,tf,n,start,end in rows:
    counts[sym][tf]={'bars':n,'first_utc':start,'last_utc':end}
   spreads={}
   for sym,n,avg in c.execute("""SELECT symbol,count(*),avg(spread_price) FROM fp_quotes
    WHERE account_fingerprint=? GROUP BY symbol""",(fingerprint,)):
    spreads[sym]={'samples':n,'mean_spread_price':round(avg,9)}
   accounts.append({'account_fingerprint':fingerprint,
      'status':'NATIVE_VERIFIED_APPEND_ONLY' if item['status']=='OK' else item['status'],
      'instrument_count':len(counts),
      'instrument_timeframes':sum(len(t) for t in counts.values()),
      'symbol_coverage':counts,'observed_spreads':spreads,
      'new_candles_added_this_run':item['new_candles'],
      'new_quote_samples_this_run':item['new_quotes'],
      'broker_native_bars_not_synthetic':True,'historical_execution_costs_verified':False,
      'net_profitable_strategy_certified':False})
 return {'schema':SCHEMA,'checked_at_utc':clock(),'mode':'DUAL_BROKER_SHADOW_RESEARCH_ONLY',
  'brokers':{'Deriv':deriv,'FP Markets':{'account_count':len(accounts),
  'accounts':accounts}},
  'data_integrity':'IMMUTABLE_OHLC_CONFLICTS_FAIL_CLOSED',
  'research_readiness':{'fp_min_m5_bars_for_exploratory_walk_forward':1000,
   'minimum_untouched_holdout_signals_for_validation':30,
   'independent_broker_costs_verified':False,
   'strategy_promotion_eligible':False},
  'FP_costs':'Observed quote spreads only; historical fill spread/commission/slippage unverified',
  'true_order_book_verified':False,
  'net_strategy_profitability_verified':False,'orders_enabled':False,
  'execution_authorized':False,'risk_settings_modified':False,'account_switches_modified':False,
  'positions_modified':False}

def atomic(path,doc):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
 fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.dual-broker-')
 try:
  with os.fdopen(fd,'w') as out:
   json.dump(doc,out,allow_nan=False,sort_keys=True,indent=2);out.flush();os.fsync(out.fileno())
  os.chmod(tmp,0o640);os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def run(out=OUT):
 now=time.time()
 conns=accounts()
 summary,digest_summary=attested_json(FP_FEED/'summary.json')
 proof=deriv_summary()
 input_rows=[]
 for cid,login,server,_,mode in conns:
  doc,digest=attested_json(FP_FEED/'market'/(cid+'.json'))
  rows,ticks=validate_account(doc,summary,cid,login,server,mode,now)
  input_rows.append((hashlib.sha256(cid.encode('ascii')).hexdigest()[:24],rows,ticks,digest))
 out=Path(out);out.mkdir(parents=True,exist_ok=True,mode=0o750)
 dbpath=out/'fp-immutable-native-candles.sqlite3'
 if dbpath.is_symlink() or (dbpath.exists() and dbpath.stat().st_size>300_000_000):
  raise ValueError('FP_RESEARCH_DB_UNSAFE')
 c=sqlite3.connect(str(dbpath),timeout=6,isolation_level=None)
 try:
  prepare_db(c)
  fp_reports=[]
  for fp,rows,ticks,digest in input_rows:
   nb,nq=append_account(c,fp,rows,ticks,digest)
   fp_reports.append({'fingerprint':fp,'status':'OK','new_candles':nb,'new_quotes':nq})
  if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':
   raise ValueError('FP_RESEARCH_DB_CORRUPT')
 finally:c.close()
 dbpath.chmod(0o640)
 d=report(fp_reports,dbpath,proof)
 atomic(out/'latest.json',d)
 return d
if __name__=='__main__':
 try:
  r=run()
 except ValueError as err:
  # A temporarily closed market or disconnected DEMO session must be an explicit
  # data-collection HOLD, not a reason to retry stale prices or degrade trading.
  if str(err) not in {
    'BROKER_PUBLISHED_SOURCE_STALE','FP_QUOTE_SOURCE_STALE',
    'FP_FRAME_HISTORY_STALE','DERIV_NATIVE_HISTORY_STALE',
    'FP_NATIVE_COVERAGE_UNVERIFIED','TWO_FP_DEMO_ACCOUNTS_NOT_VERIFIED',
    'FP_DEMO_HEARTBEAT_STALE','FP_WORKER_NOT_ATTESTED',
    'FP_NATIVE_MARKET_SOURCE_STALE','FP_NATIVE_SUMMARY_STALE'}:
   raise
  status={'schema':SCHEMA,'checked_at_utc':clock(),
      'mode':'DUAL_BROKER_WAITING_VERIFIED_NATIVE_FEED',
      'reason':str(err),'orders_enabled':False,'execution_authorized':False,
      'risk_settings_modified':False,'positions_modified':False,
      'net_strategy_profitability_verified':False}
  atomic(OUT/'last-run.json',status)
  print(json.dumps(status,sort_keys=True))
  raise SystemExit(0)
 atomic(OUT/'last-run.json',{'schema':SCHEMA,'checked_at_utc':clock(),
    'mode':r['mode'],'orders_enabled':False,'execution_authorized':False,
    'net_strategy_profitability_verified':False})
 print(json.dumps({'status':r['mode'],'deriv_symbols':len(r['brokers']['Deriv']['symbols']),
  'fp_accounts':r['brokers']['FP Markets']['account_count'],
  'fp_rows':[{'fingerprint':a['account_fingerprint'],'symbols':a['instrument_count'],
    'timeframes':a['instrument_timeframes'],'new_candles':a['new_candles_added_this_run'],
    'new_quotes':a['new_quote_samples_this_run']} for a in r['brokers']['FP Markets']['accounts']],
  'orders_enabled':False,'net_strategy_profitability_verified':False},sort_keys=True))
