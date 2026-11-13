#!/usr/bin/python3
"""Publish strictly read-only FP Markets DEMO data to active ABUTRON UI surfaces.

No order, account-control, MT5 or broker-worker modules. The client copy is
private to authenticated owner access: never served as a static web file.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,math,os,sqlite3,stat,tempfile,time

FEED=Path('/var/lib/abutron-fpmarkets-feed')
SCAN=Path('/var/lib/abutron-fp-scanner/latest.json')
AI=Path('/var/lib/abutron-fp-scanner/ai/latest.json')
DB=Path('/var/lib/apex-signup/accounts.sqlite3')
WORKERS=Path('/var/lib/private')
OPERATOR=Path('/var/lib/apex/operator-live/fp-markets-ui.json')
CUSTOMER=Path('/var/lib/apex-signup/fp-market-ui')
FRAMES=('M1','M5','M15','H1','H4','D1')
PERIOD={'M1':60,'M5':300,'M15':900,'H1':3600,'H4':14400,'D1':86400}
SYMBOLS=('XAUUSD','BTCUSD','EURUSD','GBPUSD','USDJPY','AUDUSD',
         'US100','US30','SP500','GER40','USOIL','USDCHF','NZDUSD')
SCHEMA='abutron.fpmarkets.ui.readonly.v1'

def require(ok,code):
 if not ok:raise ValueError(code)

def load(path,limit=1_600_000):
 st=path.lstat()
 require(stat.S_ISREG(st.st_mode) and 2<=st.st_size<=limit,'SOURCE_INVALID')
 fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
 try:
  before=os.fstat(fd)
  raw=os.read(fd,limit+1)
  after=os.fstat(fd)
 finally:os.close(fd)
 require(before.st_ino==after.st_ino and before.st_size==after.st_size
         and before.st_mtime_ns==after.st_mtime_ns and len(raw)<=limit,
         'SOURCE_CHANGED')
 obj=json.loads(raw)
 require(isinstance(obj,dict),'SOURCE_JSON_INVALID')
 return obj

def stamp(value):
 try:
  d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
  require(d.tzinfo is not None,'TIMESTAMP_TIMEZONE_MISSING')
  return d.timestamp()
 except (TypeError,ValueError,OverflowError,AttributeError) as e:
  raise ValueError('TIMESTAMP_INVALID') from e

def finite(v):
 return type(v) in (float,int) and math.isfinite(float(v))

def atomic(path,data,uid,gid):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.fp-ui-',dir=str(path.parent))
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as h:
   json.dump(data,h,separators=(',',':'),allow_nan=False)
   h.flush();os.fsync(h.fileno())
  os.chown(tmp,uid,gid);os.chmod(tmp,0o640);os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def data_for_ui(*,now=None,feed=FEED,scan=SCAN,ai=AI,db=DB,workers=WORKERS):
 now=time.time() if now is None else float(now)
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=6) as c:
  c.execute('PRAGMA query_only=ON')
  active=c.execute("""SELECT a.id,a.account_id,a.account_reference,a.broker_server,
      coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
      FROM apex_mt5_connections a LEFT JOIN apex_trade_controls t
      ON a.id=t.connection_id
      WHERE a.broker='FP Markets' AND a.environment='DEMO'
      AND a.broker_server='FPMarketsSC-Demo' AND a.status='CONNECTED'
      ORDER BY a.created_at DESC LIMIT 3""").fetchall()
 require(len(active)==1,'FP_CONNECTED_ACCOUNT_NOT_UNIQUE')
 cid,owner,login,server,desired,effective=active[0]
 require(type(cid) is str and len(cid)==32 and type(owner) is str and len(owner)==32,
         'FP_ACCOUNT_ID_INVALID')
 # The active FP scanner is read-only; exposing its output never enables an account.
 native=load(feed/'market'/(cid+'.json'))
 summary=load(feed/'summary.json',300_000)
 scanner=load(scan,350_000)
 try:review=load(ai,250_000)
 except (OSError,ValueError,UnicodeError):review={}
 require(native.get('schema')=='abutron.fpmarkets.native.candles.v1'
   and native.get('connection_id')==cid and native.get('source')=='FP Markets DEMO MT5'
   and native.get('account_mode')=='DEMO' and native.get('broker_server')==server
   and native.get('execution_enabled') is False and native.get('orders_submitted')==0,
   'FP_NATIVE_IDENTITY_OR_ORDER_POLICY_FAILED')
 require(-25<=now-stamp(native.get('checked_at_utc'))<=160,
         'FP_NATIVE_FEED_STALE')
 require(summary.get('native_feeds_complete')==1 and summary.get('orders_submitted')==0
         and summary.get('execution_enabled') is False
         and -25<=now-stamp(summary.get('checked_at_utc'))<=160,
         'FP_SUMMARY_NOT_CURRENT')
 require(any(c.get('connection_id')==cid and
             c.get('status')=='BROKER_NATIVE_DATA_COMPLETE'
             and c.get('fresh_quotes')==13 and c.get('timeframes_verified')==78
             for c in summary.get('connections',[])),
         'FP_NATIVE_SYMBOL_COVERAGE_INCOMPLETE')
 require(scanner.get('schema')=='abutron.fpmarkets.apex.scanner.readonly.v1'
         and scanner.get('status')=='FP_SCANNER_READONLY_ACTIVE'
         and scanner.get('execution_authorized') is False
         and scanner.get('orders_enabled') is False
         and scanner.get('symbols')==13 and scanner.get('timeframes_per_symbol')==6
         and scanner.get('account_fingerprint')==hashlib.sha256(cid.encode()).hexdigest()[:24]
         and -25<=now-stamp(scanner.get('checked_at_utc'))<=190,
         'FP_SCANNER_INVALID_OR_STALE')
 health=load(workers/('abutron-client-mt5-'+cid)/'worker-health.json',25_000)
 require(health.get('status')=='CONNECTED' and health.get('heartbeat_fresh') is True
         and health.get('id')==cid and health.get('server')==server,
         'FP_HEARTBEAT_UNVERIFIED')
 hfile=workers/('abutron-client-mt5-'+cid)/'terminal'/'MQL5'/'Files'/(
      'ABUTRON_SESSION_HEARTBEAT_V1_'+health['nonce']+'.txt')
 require(-10<=now-hfile.stat().st_mtime<=20,'FP_NATIVE_HEARTBEAT_OLD')
 mapping=native.get('mapping')
 quotes=native.get('quotes')
 bars=native.get('bars')
 ensure=set(SYMBOLS)
 require(all(isinstance(x,dict) and set(x)==ensure for x in (mapping,quotes,bars)),
         'FP_SYMBOLS_MISMATCH')
 observed=scanner.get('instruments')
 require(isinstance(observed,list) and
         {x.get('symbol') for x in observed}==ensure,
         'FP_SCANNER_SYMBOLS_MISMATCH')
 scanner_by={x['symbol']:x for x in observed}
 ai_ok=(review.get('schema')=='abutron.fpmarkets.apex.ai_selective_tradingagents.v1'
        and review.get('status')=='FP_AI_RESEARCH_ONLY'
        and review.get('orders_enabled') is False and
        review.get('execution_authorized') is False and
        -25<=now-stamp(review.get('reviewed_at_utc'))<=440
        if review.get('reviewed_at_utc') else False)
 ai_reviews={x['symbol']:x for x in review.get('reviews',[]) if isinstance(x,dict)
             and x.get('symbol') in ensure} if ai_ok else {}
 entries=[];chart={}
 for sym in SYMBOLS:
  m=mapping[sym];q=quotes[sym];sc=scanner_by[sym]
  require(m.get('status')=='MAPPED' and q.get('symbol')==m.get('actual'),
          'FP_BROKER_SYMBOL_UNTRUSTED')
  require(type(q.get('time')) is int and -25<=now-q['time']<=300,
          'FP_BROKER_QUOTE_STALE')
  require(q.get('broker_clock_offset_seconds')==7200
          and finite(q.get('bid')) and finite(q.get('ask'))
          and 0<q['bid']<=q['ask'],'FP_BROKER_QUOTE_INVALID')
  frm=bars[sym]
  require(isinstance(frm,dict) and set(frm)==set(FRAMES),'FP_BROKER_FRAME_INVALID')
  cleaned={}
  for tf in FRAMES:
   raw=frm[tf]
   require(isinstance(raw,list) and len(raw)>=60,'FP_INCOMPLETE_OHLC')
   previous=-1;clean=[]
   for v in raw[-70:]:
    t=v.get('time')
    o,h,l,c=(v.get(z) for z in ('open','high','low','close'))
    require(type(t) is int and t>previous and t+PERIOD[tf]<=now+1,
            'FP_UNCLOSED_OR_INVALID_BAR')
    require(all(finite(x) and x>0 for x in (o,h,l,c)) and
            l<=min(o,c)<=max(o,c)<=h,'FP_INVALID_OHLC')
    clean.append([t,float(o),float(h),float(l),float(c)])
    previous=t
   require(tf not in ('M1','M5') or now-clean[-1][0]<=900,
           'FP_SHORT_FRAME_NOT_FRESH')
   cleaned[tf]=clean
  chart[sym]=cleaned
  require(sc.get('orders_enabled') is False and sc.get('execution_authorized') is False
          and sc.get('final_decision')=='HOLD'
          and sc.get('m5_closed_bar')==cleaned['M5'][-1][0],
          'FP_SCANNER_CANDLE_OR_EXECUTION_MISMATCH')
  review_row=ai_reviews.get(sym,{})
  matched=(review_row.get('m5_closed_bar')==sc['m5_closed_bar']
       and review_row.get('scanner_proposal')==sc.get('proposal')
       and review_row.get('evidence_status')=='MODEL_REVIEW_COMPLETED'
       and -30<=now-stamp(review_row.get('reviewed_at_utc'))<=440
       if review_row.get('reviewed_at_utc') else False)
  ai_dir=review_row.get('llm_direction') if matched else None
  ai_status=('PASS' if ai_dir==sc.get('proposal')
             and ai_dir in ('BUY','SELL') else
             'VETO' if matched else 'PENDING')
  smc_stat=sc.get('smc',{}).get('status')
  ict_stat=sc.get('ict',{}).get('status')
  require(smc_stat in ('REMOVED','VETO') and ict_stat in ('REMOVED','VETO'),
          'FP_SMC_ICT_STATUS_INVALID')
  proposal=sc.get('proposal')
  require(proposal in ('BUY','SELL','HOLD'),'FP_PROPOSAL_INVALID')
  research=('BUY' if proposal=='BUY' else 'SELL' if proposal=='SELL' else 'HOLD') if (
    ai_status=='PASS') else 'HOLD'
  latest=cleaned['M5'][-1]
  previous=cleaned['M5'][-2]
  # Same completed-candle trend columns used by the original Deriv scanner.
  # Read only the already-verified FP scanner indicators for this market candle.
  indicators=sc.get('indicators')
  require(isinstance(indicators,dict) and set(indicators)==set(FRAMES),
          'FP_SCANNER_TIMEFRAME_INDICATORS_MISSING')
  tf_trends={}
  for tf in FRAMES:
   item=indicators.get(tf)
   require(isinstance(item,dict) and item.get('trend') in ('UP','DOWN','MIXED')
           and type(item.get('bar_time')) is int,
           'FP_SCANNER_TREND_INVALID')
   tf_trends[tf]=item['trend']
  require(indicators['M5']['bar_time']==sc['m5_closed_bar'],
          'FP_SCANNER_M5_INDICATOR_CANDLE_MISMATCH')
  family=('Metal' if sym=='XAUUSD' else 'Crypto' if sym=='BTCUSD'
          else 'Commodity' if sym=='USOIL' else 'Index'
          if sym in ('US100','US30','SP500','GER40') else 'Forex')
  m5_body=('BUY' if latest[4]>latest[1] else 'SELL' if latest[4]<latest[1] else 'FLAT')
  entries.append({'symbol':sym,'broker_symbol':m['actual'],
     'family':family,'timeframe_trends':tf_trends,'m5_candle_body':m5_body,
     'bid':round(float(q['bid']),8),'ask':round(float(q['ask']),8),
     'quote_timestamp_utc':datetime.fromtimestamp(q['time'],timezone.utc).isoformat(),
     'quote_age_seconds':round(now-q['time'],1),
     'm5_last_close':round(latest[4],8),
     'm5_change_pct':round((latest[4]/previous[4]-1)*100,4),
     'm5_close_utc':datetime.fromtimestamp(latest[0],timezone.utc).isoformat(),
     'm5_bar_time':latest[0],
     'proposal':proposal,'m5_direction':sc.get('m5_direction'),
     'higher_timeframe_direction':sc.get('higher_timeframe_direction'),
     'rsi14':sc.get('indicators',{}).get('M5',{}).get('rsi14'),
     'atr14':sc.get('indicators',{}).get('M5',{}).get('atr14'),
     'scanner_reason':str(sc.get('reason',''))[:100],
     'smc':smc_stat,'smc_score':sc.get('smc',{}).get('score'),
     'smc_reason':','.join(sc.get('smc',{}).get('reasons',[]))[:150],
     'ict':ict_stat,'liquidity_sweep':bool(sc.get('ict',{}).get('liquidity_sweep')),
     'zone_retest':bool(sc.get('ict',{}).get('zone_retest')),
     'premium_discount':str(sc.get('ict',{}).get('premium_discount',''))[:24],
     'ai_status':ai_status,'ai_direction':ai_dir if ai_dir in ('BUY','SELL','HOLD') else None,
     'ai_model':str(review_row.get('model',''))[:70] if matched else '',
     'ai_analysis':str(review_row.get('analysis',''))[:180] if matched else '',
     'research_direction':research,'final_decision':'HOLD',
     'orders_enabled':False,'execution_authorized':False})
 return cid,owner,{'schema':SCHEMA,'available':True,
  'generated_at_utc':datetime.fromtimestamp(now,timezone.utc).isoformat(),
  'broker':'FP Markets','environment':'DEMO',
  'account_masked':'••••'+str(login)[-4:],
  'broker_server':server,'status':'CONNECTED',
  'quote_count':len(entries),'fresh_quotes':len(entries),
  'timeframe_series':len(entries)*len(FRAMES),
  'symbol_list':list(SYMBOLS),'timeframes':list(FRAMES),
  'scanner_proposals':sum(r['proposal']!='HOLD' for r in entries),
  'ai_agreements':sum(r['ai_status']=='PASS' for r in entries),
  'smc_ict_ai_agreements':0,
  'tradingagents_ai_agreements':sum(r['research_direction']!='HOLD' for r in entries),
  'native_feed_at_utc':native['checked_at_utc'],
  'scanner_at_utc':scanner['checked_at_utc'],
  'ai_review_at_utc':review.get('reviewed_at_utc') if ai_ok else None,
  'execution_enabled':False,'orders_submitted_by_collector':0,
  'trading_controls':{'desired_enabled':bool(desired),'effective_enabled':bool(effective)},
  'verified_trade_history_available':False,
  'trade_history_notice':'FP Markets broker-native open positions and closed-deal history are not connected to this view. No positions, fills or P&L are inferred from signals.',
  'symbols':entries,'candles':chart}

def publish(*, operator=OPERATOR,customer=CUSTOMER,now=None,
            feed=FEED,scan=SCAN,ai=AI,db=DB,workers=WORKERS):
 import pwd,grp
 cid,owner,doc=data_for_ui(now=now,feed=feed,scan=scan,ai=ai,db=db,workers=workers)
 operator_uid=pwd.getpwnam('apexagent').pw_uid
 operator_gid=grp.getgrnam('apexagent').gr_gid
 client_uid=pwd.getpwnam('apexsignup').pw_uid
 client_gid=grp.getgrnam('apexsignup').gr_gid
 customer.mkdir(mode=0o700,parents=True,exist_ok=True)
 os.chown(customer,client_uid,client_gid);os.chmod(customer,0o700)
 # Neither destination is below a public static root.
 atomic(operator,doc,0,operator_gid)
 atomic(customer/(cid+'.json'),doc,client_uid,client_gid)
 return {'status':'FP_UI_PUBLISHED','symbols':len(doc['symbols']),
   'frames':doc['timeframe_series'],'owner_scoped':True,
   'fresh_quotes':doc['fresh_quotes'],'ai_agreements':doc['ai_agreements'],
   'all_positive':doc['smc_ict_ai_agreements'],'orders_enabled':False}
if __name__=='__main__':
 try:print(json.dumps(publish(),sort_keys=True))
 except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,OverflowError) as e:
  print('FP_UI_SAFE_HOLD',str(e)[:130])
  raise SystemExit(1)
