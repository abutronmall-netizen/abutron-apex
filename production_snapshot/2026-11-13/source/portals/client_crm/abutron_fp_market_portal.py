"""Owner-isolated, broker-native FP Markets client/admin research reader.
Read-only. Returns NO prices for invalid, disconnected or stale accounts.
"""
from __future__ import annotations
import json,os,re,stat,time,hashlib
from datetime import datetime
from pathlib import Path

ROOT=Path('/var/lib/apex-signup/fp-market-ui')
SCHEMA='abutron.fpmarkets.ui.readonly.v1'
CID=re.compile(r'^[0-9a-f]{32}$')
MAX_AGE=180
MAX_SIZE=1_000_000
SYMBOLS={'XAUUSD','BTCUSD','EURUSD','GBPUSD','USDJPY','AUDUSD',
         'US100','US30','SP500','GER40','USOIL','USDCHF','NZDUSD'}

def safe_file(path):
    st=path.lstat()
    if (not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode)
        or not 100<=st.st_size<=MAX_SIZE):
        raise ValueError('FP_UI_FILE_UNTRUSTED')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        before=os.fstat(fd); raw=os.read(fd,MAX_SIZE+1); after=os.fstat(fd)
    finally:os.close(fd)
    if ((before.st_ino,before.st_mtime_ns,before.st_size)!=
        (after.st_ino,after.st_mtime_ns,after.st_size) or len(raw)>MAX_SIZE):
        raise ValueError('FP_UI_FILE_CHANGED')
    doc=json.loads(raw)
    if not isinstance(doc,dict):raise ValueError('FP_UI_INVALID_OBJECT')
    return doc

def verify(doc,now=None):
    now=time.time() if now is None else float(now)
    try:
        stamp=datetime.fromisoformat(doc['generated_at_utc'].replace('Z','+00:00'))
        if stamp.tzinfo is None:raise ValueError('UNZONED')
        age=now-stamp.timestamp()
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('FP_UI_TIME_INVALID') from exc
    valid=(-30<=age<=MAX_AGE and doc.get('schema')==SCHEMA
        and doc.get('available') is True and doc.get('broker')=='FP Markets'
        and doc.get('environment')=='DEMO' and doc.get('broker_server')=='FPMarketsSC-Demo'
        and doc.get('execution_enabled') is False
        and doc.get('orders_submitted_by_collector')==0)
    if not valid:raise ValueError('FP_UI_STALE_OR_UNVERIFIED')
    controls=doc.get('trading_controls')
    if (not isinstance(controls,dict)
        or set(controls)!={'desired_enabled','effective_enabled'}
        or any(type(v) is not bool for v in controls.values())
        or (controls['effective_enabled'] and not controls['desired_enabled'])):
        raise ValueError('FP_UI_ACCOUNT_CONTROL_INVALID')
    rows=doc.get('symbols')
    if (not isinstance(rows,list) or len(rows)!=13
        or any(not isinstance(r,dict) for r in rows)
        or {r.get('symbol') for r in rows}!=SYMBOLS
        or any(r.get('final_decision')!='HOLD'
                or r.get('orders_enabled') is not False
                or r.get('execution_authorized') is not False for r in rows)):
        raise ValueError('FP_UI_ROWS_INVALID')
    covered=[r for r in rows if r.get('available') is True]
    missing=[r for r in rows if r.get('available') is False]
    count=doc.get('fresh_quotes')
    frame=doc.get('timeframe_series')
    if not(type(count) is int and 1<=count<=13 and type(frame) is int
           and frame==count*6 and doc.get('quote_count')==count
           and count==len(covered) and len(missing)==13-count):
        raise ValueError('FP_UI_COVERAGE_INVALID')
    if (set(doc.get('candles',{}))!={r['symbol'] for r in covered}
        or set(doc.get('unavailable_symbols',[]))!={r['symbol'] for r in missing}
        or any(r.get('broker_status')!='MAPPED' or r.get('broker_symbol')=='UNAVAILABLE'
               for r in covered)
        or any(r.get('proposal')!='HOLD' or r.get('broker_symbol')!='UNAVAILABLE'
               or r.get('m5_bar_time') is not None for r in missing)):
        raise ValueError('FP_UI_BROKER_IDENTITY_UNVERIFIED')
    if count<13:
        if (doc.get('status')!='CONNECTED_PARTIAL'
            or doc.get('source_quality')!='PARTIAL_NOT_CERTIFIED'
            or doc.get('coverage_complete') is not False):
            raise ValueError('FP_UI_PARTIAL_NOT_LABELED')
    else:
        if (doc.get('coverage_complete') is not True
            or doc.get('source_quality')!='BROKER_NATIVE_13X6_VERIFIED'):
            raise ValueError('FP_UI_COMPLETE_STATUS_UNVERIFIED')
    if type(doc.get('verified_trade_history_available')) is not bool:
        raise ValueError('FP_UI_HISTORY_STATUS_INVALID')
    if not doc['verified_trade_history_available']:
        if any(doc.get(k) is not None for k in
               ('verified_open_positions_count','verified_pending_orders_count',
                'verified_broker_trade_deals_90d','verified_equity_usd')):
            raise ValueError('FP_UI_UNVERIFIED_HISTORY_VALUES')
    return doc

def _connected(db_connect,owner=None):
    query="""SELECT a.id,a.account_id,a.account_reference FROM apex_mt5_connections a
             WHERE a.broker='FP Markets' AND a.environment='DEMO'
             AND a.broker_server='FPMarketsSC-Demo' AND a.status='CONNECTED'"""
    params=()
    if owner is not None:query+=' AND a.account_id=?';params=(owner,)
    query+=' ORDER BY a.id LIMIT 8'
    with db_connect() as db:
        rows=db.execute(query,params).fetchall()
    for cid,aid,ref in rows:
        if (not isinstance(cid,str) or not CID.fullmatch(cid)
            or not isinstance(aid,str) or not CID.fullmatch(aid)
            or not isinstance(ref,str) or not ref.isdigit()):
            raise ValueError('FP_UI_DB_IDENTITY_INVALID')
    return rows

def _bound(row,now,root):
    cid,owner,login=row
    doc=verify(safe_file(root/(cid+'.json')),now)
    if doc.get('account_masked')!='••••'+login[-4:]:
        raise ValueError('FP_UI_ACCOUNT_OWNERSHIP_MISMATCH')
    if doc.get('verified_trade_history_available') and doc.get('account_masked')!='••••'+login[-4:]:
        raise ValueError('FP_UI_HISTORY_ACCOUNT_MISMATCH')
    return doc

def client_snapshot(db_connect,account_id,now=None,root=ROOT):
    if not isinstance(account_id,str) or not CID.fullmatch(account_id):
        raise ValueError('FP_CLIENT_SESSION_INVALID')
    rows=_connected(db_connect,account_id)
    if not rows:
        return {'available':False,'reason':'NO_CONNECTED_FP_DEMO_ACCOUNT',
                'broker':'FP Markets','execution_enabled':False}
    if len(rows)!=1:raise ValueError('FP_CLIENT_MULTI_ACCOUNT_SELECTION_REQUIRED')
    return _bound(rows[0],now,root)

def admin_snapshot(db_connect,now=None,root=ROOT):
    rows=_connected(db_connect)
    if not rows:
        return {'available':False,'reason':'NO_CONNECTED_FP_DEMO_ACCOUNT',
                'broker':'FP Markets','execution_enabled':False,'accounts':[]}
    if len(rows)>6:raise ValueError('FP_ADMIN_ACCOUNT_COUNT_UNSAFE')
    accounts=[]
    for row in rows:
        d=_bound(row,now,root)
        accounts.append({
          'account_masked':d['account_masked'],
          'status':d['status'],'source_quality':d['source_quality'],
          'coverage_complete':d['coverage_complete'],
          'generated_at_utc':d['generated_at_utc'],
          'fresh_quotes':d['fresh_quotes'],'timeframe_series':d['timeframe_series'],
          'scanner_proposals':d['scanner_proposals'],
          'ai_agreements':d['ai_agreements'],
          'tradingagents_ai_agreements':d.get('tradingagents_ai_agreements',0),
          'trading_controls':d['trading_controls'],
          'unavailable_symbols':d['unavailable_symbols'],
          'symbols':[{k:s.get(k) for k in
             ('symbol','broker_symbol','proposal','ai_status','m5_candle_body',
              'higher_timeframe_direction','final_decision','scanner_reason')}
             for s in d['symbols']]})
    return {'schema':'abutron.fpmarkets.admin.multi_account.readonly.v1',
      'available':True,'broker':'FP Markets','environment':'DEMO',
      'source_quality':'ACCOUNT_SCOPED_PARTIAL_NOT_CERTIFIED',
      'account_count':len(accounts),'accounts':accounts,
      'fresh_quotes':sum(x['fresh_quotes'] for x in accounts),
      'required_quotes':13*len(accounts),
      'timeframe_series':sum(x['timeframe_series'] for x in accounts),
      'required_timeframe_series':78*len(accounts),
      'execution_enabled':False,'execution_authorized':False}
