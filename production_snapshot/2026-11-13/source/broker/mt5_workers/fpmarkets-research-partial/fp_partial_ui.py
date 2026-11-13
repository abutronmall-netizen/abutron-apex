#!/usr/bin/python3
"""FP Markets DEMO partial verified research UI, read-only; no trading API."""
from __future__ import annotations
import datetime as dt, hashlib, importlib.util, json, math, os, pwd, grp, sqlite3, time
from pathlib import Path

ROOT=Path('/opt/apex-client-mt5/fpmarkets-research-partial')
SCANNER=ROOT/'fp_partial_scanner.py'
BASE='/opt/apex-client-mt5/fpmarkets-ui/fp_ui_publish.py'
CID='35b81a287b6a030f2f46ff426b135e6c'
SYMS=('XAUUSD','BTCUSD','EURUSD','GBPUSD','USDJPY','AUDUSD','US100','US30','SP500','GER40','USOIL','USDCHF','NZDUSD')
FRAMES=('M1','M5','M15','H1','H4','D1')
PERIOD=dict(zip(FRAMES,(60,300,900,3600,14400,86400)))
NATIVE=Path('/var/lib/abutron-fpmarkets-feed/partial')/(CID+'.json')
AI=Path('/var/lib/abutron-fp-scanner/ai/latest.json')
OPERATOR=Path('/var/lib/apex/operator-live/fp-markets-ui.json')
HISTORY=Path('/var/lib/apex/operator-live/fp-native-history.json')
CLIENT=Path('/var/lib/apex-signup/fp-market-ui')
DB=Path('/var/lib/apex-signup/accounts.sqlite3')

def module(name,p):
 spec=importlib.util.spec_from_file_location(name,str(p))
 obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

def create(scanner,now=None):
 now=time.time() if now is None else now
 base=module('fp_ui_original_helpers_partial',BASE)
 source=base.load(NATIVE)
 assert source.get('schema')=='abutron.fpmarkets.native.partial.readonly.v1'
 assert source.get('connection_id')==CID
 assert source.get('execution_enabled') is False and source.get('orders_submitted')==0
 assert -30<=now-base.stamp(source['checked_at_utc'])<=130
 assert scanner['status']=='FP_SCANNER_PARTIAL_READONLY' and scanner['orders_enabled'] is False
 assert scanner['execution_authorized'] is False and scanner['account_controls_modified'] is False
 assert -30<=now-base.stamp(scanner['checked_at_utc'])<=160
 assert scanner['native_market_at_utc']==source['checked_at_utc']
 with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=7) as c:
  c.execute('PRAGMA query_only=ON')
  active=c.execute("""SELECT account_id,account_reference,broker_server,
    COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0)
    FROM apex_mt5_connections a LEFT JOIN apex_trade_controls t ON a.id=t.connection_id
    WHERE a.id=? AND a.broker='FP Markets' AND a.environment='DEMO'
      AND a.status='CONNECTED'""",(CID,)).fetchone()
 assert (active and active[2]=='FPMarketsSC-Demo' and
  type(active[3]) is int and type(active[4]) is int and
  active[3] in (0,1) and active[4] in (0,1) and active[4]<=active[3])
 owner,login,server,desired,effective=active
 assert len(owner)==32 and str(login).isdigit()
 mapping=source['mapping'];quotes=source['quotes'];bars=source['bars']
 assert set(mapping)==set(SYMS) and set(quotes)==set(bars)
 rows=scanner['instruments']
 assert len(rows)==13 and {r['symbol'] for r in rows}==set(SYMS)
 sc={r['symbol']:r for r in rows}
 try:review=base.load(AI,260000)
 except (OSError,ValueError,TypeError):review={}
 ai_valid=(review.get('schema')=='abutron.fpmarkets.apex.ai_selective_tradingagents.v1'
   and review.get('status')=='FP_AI_RESEARCH_ONLY'
   and review.get('orders_enabled') is False and review.get('execution_authorized') is False
   and review.get('reviewed_at_utc') and -30<=now-base.stamp(review['reviewed_at_utc'])<=440)
 ai_reviews={r.get('symbol'):r for r in review.get('reviews',[]) if isinstance(r,dict)} if ai_valid else {}
 entries=[];candles={}
 verified_count=0
 for sym in SYMS:
  m=mapping[sym];r=sc[sym]
  family=r['family']
  assert r['final_decision']=='HOLD' and r['orders_enabled'] is False and r['execution_authorized'] is False
  if not r['available']:
   # Session-stale broker bars may exist. Retain them as unavailable,
   # never promoting their quotes/candles to verified signal inputs.
   if r['broker_status']=='STALE_NATIVE_SESSION':
    assert m['status']=='MAPPED' and isinstance(m.get('actual'),str)
    assert sym in quotes and sym in bars and quotes[sym]['symbol']==m['actual']
    assert set(bars[sym])==set(FRAMES) and any(
     isinstance(bars[sym][tf],list) and bars[sym][tf] and
     now-bars[sym][tf][-1].get('time',0)>900 for tf in ('M1','M5'))
   else:
    assert sym not in quotes and sym not in bars and (
     m['status'] in ('MISSING','AMBIGUOUS') or
     (m['status']=='MAPPED' and r['broker_status']=='BARS_PENDING' and isinstance(m.get('actual'),str)))
   entries.append({'symbol':sym,'broker_symbol':'UNAVAILABLE','family':family,
    'available':False,'broker_status':r['broker_status'],'timeframe_trends':{},
    'm5_candle_body':'UNAVAILABLE','bid':None,'ask':None,
    'quote_timestamp_utc':None,'quote_age_seconds':None,
    'm5_last_close':None,'m5_change_pct':None,'m5_close_utc':None,'m5_bar_time':None,
    'proposal':'HOLD','m5_direction':'HOLD','higher_timeframe_direction':'UNAVAILABLE',
    'rsi14':None,'atr14':None,'scanner_reason':r['reason'],
    'smc':'VETO','smc_score':0,'smc_reason':'BROKER_NATIVE_SYMBOL_UNAVAILABLE',
    'ict':'VETO','liquidity_sweep':False,'zone_retest':False,'premium_discount':'UNVERIFIED',
    'ai_status':'PENDING','ai_direction':None,'ai_model':'','ai_analysis':'',
    'research_direction':'HOLD','final_decision':'HOLD',
    'orders_enabled':False,'execution_authorized':False})
   continue
  assert m['status']=='MAPPED' and quotes[sym]['symbol']==m['actual']
  q=quotes[sym]
  assert type(q['time']) is int and -30<=now-q['time']<=300 and q['broker_clock_offset_seconds']==7200
  assert all(type(q[k]) in (float,int) and math.isfinite(q[k]) for k in ('bid','ask'))
  assert 0<q['bid']<=q['ask']
  assert set(bars[sym])==set(FRAMES)
  clean={}
  for frame in FRAMES:
   raw=bars[sym][frame]
   assert len(raw)>=60
   last_time=-1;points=[]
   for item in raw[-70:]:
    ts=item['time'];o=item['open'];h=item['high'];lo=item['low'];close=item['close']
    assert type(ts) is int and ts>last_time and ts+PERIOD[frame]<=now+1
    assert all(type(n) in (int,float) and math.isfinite(n) and n>0 for n in (o,h,lo,close))
    assert lo<=min(o,close)<=max(o,close)<=h
    points.append([ts,float(o),float(h),float(lo),float(close)])
    last_time=ts
   assert frame not in ('M1','M5') or now-points[-1][0]<=900
   clean[frame]=points
  candles[sym]=clean
  assert r['m5_closed_bar']==clean['M5'][-1][0]
  tf={}
  for frame in FRAMES:
   indicator=r['indicators'][frame]
   assert indicator['trend'] in ('UP','DOWN','MIXED')
   tf[frame]=indicator['trend']
  assert r['indicators']['M5']['bar_time']==r['m5_closed_bar']
  advice=ai_reviews.get(sym,{})
  same=(advice.get('m5_closed_bar')==r['m5_closed_bar'] and
        advice.get('scanner_proposal')==r['proposal'] and
        advice.get('evidence_status')=='MODEL_REVIEW_COMPLETED' and
        advice.get('reviewed_at_utc') and
        -30<=now-base.stamp(advice['reviewed_at_utc'])<=440)
  direction=advice.get('llm_direction') if same else None
  ai_status=('PASS' if same and direction in ('BUY','SELL') and direction==r['proposal']
    else 'VETO' if same else 'PENDING')
  smc=r['smc']['status'];ict=r['ict']['status'];assert smc in ('REMOVED','VETO') and ict in ('REMOVED','VETO')
  confirmed=ai_status=='PASS'
  latest=clean['M5'][-1];previous=clean['M5'][-2]
  entries.append({'symbol':sym,'broker_symbol':m['actual'],'family':family,
    'available':True,'broker_status':'MAPPED','timeframe_trends':tf,
    'm5_candle_body':'BUY' if latest[4]>latest[1] else 'SELL' if latest[4]<latest[1] else 'FLAT',
    'bid':float(q['bid']),'ask':float(q['ask']),
    'quote_timestamp_utc':dt.datetime.fromtimestamp(q['time'],dt.timezone.utc).isoformat(),
    'quote_age_seconds':round(now-q['time'],1),
    'm5_last_close':latest[4],'m5_change_pct':round((latest[4]/previous[4]-1)*100,4),
    'm5_close_utc':dt.datetime.fromtimestamp(latest[0],dt.timezone.utc).isoformat(),
    'm5_bar_time':latest[0],'proposal':r['proposal'],
    'm5_direction':r['m5_direction'],'higher_timeframe_direction':r['higher_timeframe_direction'],
    'rsi14':r['indicators']['M5']['rsi14'],'atr14':r['indicators']['M5']['atr14'],
    'scanner_reason':r['reason'],'smc':smc,'smc_score':r['smc'].get('score',0),
    'smc_reason':','.join(r['smc'].get('reasons',[]))[:150],
    'ict':ict,'liquidity_sweep':bool(r['ict'].get('liquidity_sweep')),
    'zone_retest':bool(r['ict'].get('zone_retest')),
    'premium_discount':str(r['ict'].get('premium_discount'))[:24],
    'ai_status':ai_status,'ai_direction':direction if direction in ('BUY','SELL','HOLD') else None,
    'ai_model':advice.get('model','') if same else '',
    'ai_analysis':str(advice.get('analysis',''))[:180] if same else '',
    'research_direction':r['proposal'] if confirmed else 'HOLD',
    'final_decision':'HOLD','orders_enabled':False,'execution_authorized':False})
  verified_count+=1
 assert verified_count==scanner['symbols_verified'] and verified_count<=len(quotes)
 assert len(candles)==verified_count and len(entries)==13
 missing=[r['symbol'] for r in entries if not r['available']]
 assert missing==scanner['symbols_unavailable'] and len(missing)==13-verified_count
 history_verified=False
 history_positions=None
 history_pending=None
 history_trade_deals=None
 history_equity_usd=None
 try:
  assert HISTORY.is_file() and not HISTORY.is_symlink() and HISTORY.stat().st_size<=300000
  record=base.load(HISTORY,300000)
  valid=(record.get('schema')=='abutron.fpmarkets.native.account_history.readonly.v1'
    and record.get('available') is True and record.get('history_verified_from_mt5') is True
    and record.get('broker')=='FP Markets' and record.get('environment')=='DEMO'
    and record.get('account_masked')=='••••'+str(login)[-4:]
    and record.get('account_currency')=='USD'
    and record.get('execution_enabled') is False
    and record.get('orders_submitted_by_exporter')==0
    and record.get('history_complete_within_selected_window') is True
    and record.get('history_window_days')==90
    and -30<=now-base.stamp(record['generated_at_utc'])<=150
    and -30<=now-base.stamp(record['broker_export_at_utc'])<=150
    and isinstance(record.get('native_file_sha256'),str)
    and len(record['native_file_sha256'])==64
    and all(ch in '0123456789abcdef' for ch in record['native_file_sha256'])
    and type(record.get('open_positions_count')) is int
    and type(record.get('pending_orders_count')) is int
    and type(record.get('trade_deals_count')) is int
    and type(record.get('equity_usd')) in (int,float)
    and math.isfinite(record['equity_usd']) and record['equity_usd']>0
    and isinstance(record.get('positions'),list)
    and isinstance(record.get('pending_orders'),list)
    and isinstance(record.get('trade_deals'),list)
    and len(record['positions'])==record['open_positions_count']
    and len(record['pending_orders'])==record['pending_orders_count']
    and len(record['trade_deals'])==record['history_trade_deals_shown'])
  if valid:
   history_verified=True
   history_positions=record['open_positions_count']
   history_pending=record['pending_orders_count']
   history_trade_deals=record['trade_deals_count']
   history_equity_usd=record['equity_usd']
 except (OSError,ValueError,TypeError,KeyError,AssertionError,OverflowError):
  pass
 history_notice=('FP Markets DEMO broker-native 90-day history verified: '
   +str(history_positions)+' open positions, '+str(history_pending)
   +' pending orders, '+str(history_trade_deals)+' trading deals reported. '
   +'This is not strategy-level P/L.'
   if history_verified else
   'FP Markets broker-native positions and deal history are not currently verified; no fills or P/L inferred from signals.')
 out={'schema':'abutron.fpmarkets.ui.readonly.v1','available':True,
  'generated_at_utc':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
  'broker':'FP Markets','environment':'DEMO',
  'account_masked':'••••'+str(login)[-4:],'broker_server':server,'status':'CONNECTED_PARTIAL',
  'coverage_complete':verified_count==13,'source_quality':'BROKER_NATIVE_13X6_VERIFIED' if verified_count==13 else 'PARTIAL_NOT_CERTIFIED',
  'unavailable_symbols':missing,'quote_count':verified_count,'fresh_quotes':verified_count,
  'timeframe_series':verified_count*6,'symbol_list':list(SYMS),'timeframes':list(FRAMES),
  'scanner_proposals':scanner['scanner_proposals'],
  'ai_agreements':sum(r['ai_status']=='PASS' for r in entries),
  'smc_ict_ai_agreements':0,
  'tradingagents_ai_agreements':sum(r['research_direction']!='HOLD' for r in entries),
  'native_feed_at_utc':source['checked_at_utc'],
  'scanner_at_utc':scanner['checked_at_utc'],
  'ai_review_at_utc':review.get('reviewed_at_utc') if ai_valid else None,
  'execution_enabled':False,'orders_submitted_by_collector':0,
  'trading_controls':{'desired_enabled':bool(desired),'effective_enabled':bool(effective)},
  'verified_trade_history_available':history_verified,
  'verified_open_positions_count':history_positions,
  'verified_pending_orders_count':history_pending,
  'verified_broker_trade_deals_90d':history_trade_deals,
  'verified_equity_usd':history_equity_usd,
  'trade_history_notice':history_notice,
  'symbols':entries,'candles':candles}
 return CID,owner,out

def publish(scanner,*,operator=OPERATOR,customer=CLIENT):
 base=module('fp_original_publisher_part',BASE)
 cid,owner,doc=create(scanner)
 operator_uid=0;operator_gid=grp.getgrnam('apexagent').gr_gid
 client_uid=pwd.getpwnam('apexsignup').pw_uid
 client_gid=pwd.getpwnam('apexsignup').pw_gid
 base.atomic(operator,doc,operator_uid,operator_gid)
 base.atomic(customer/(cid+'.json'),doc,client_uid,client_gid)
 return {'status':'FP_PARTIAL_RESEARCH_PUBLISHED','verified':doc['fresh_quotes'],
   'unavailable':doc['unavailable_symbols'],'frames':doc['timeframe_series'],
   'orders_enabled':False}

if __name__=='__main__':
 scanner=module('fp_partial_scanner_ui',SCANNER).build()
 cid,owner,doc=create(scanner)
 print(json.dumps({'stage':'VALIDATED_ONLY','symbol_count':len(doc['symbols']),
   'fresh_quotes':doc['fresh_quotes'],'missing':doc['unavailable_symbols'],
   'candles':len(doc['candles']),'orders_enabled':doc['execution_enabled']}))

