#!/usr/bin/env python3
"""ABUTRON APEX read-only FP Markets native-feed strategy research adapter.

Reuses the exact ORIGINAL APEX EMA/RSI/ATR utilities and existing SMC/ICT
confirmation functions. No router, order, broker-worker or account writes.
"""
from __future__ import annotations
import datetime as dt, hashlib, importlib.util, json, math, os, sqlite3
import stat, sys, tempfile, time
from pathlib import Path

ROOT=Path('/opt/apex-client-mt5/fpmarkets-scanner')
REG=Path('/opt/apex-client-mt5/fpmarkets-feed/registry.json')
FEED=Path('/var/lib/abutron-fpmarkets-feed')
ACCOUNTS=Path('/var/lib/apex-signup/accounts.sqlite3')
PRIVATE=Path('/var/lib/private')
OUT=Path('/var/lib/abutron-fp-scanner')
FAS=Path('/opt/apex/runtime/apex_fast_scanner.py')
SMC=Path('/opt/apex-smc-shadow-v1/smc_shadow.py')
SCHEMA='abutron.fpmarkets.apex.scanner.readonly.v1'
FRAMES=('M1','M5','M15','H1','H4','D1')
PERIOD=dict(zip(FRAMES,(60,300,900,3600,14400,86400)))

def verify(ok,reason):
    if not ok:raise ValueError(reason)

def read(path,max_size=10_000_000):
    st=path.lstat()
    verify(stat.S_ISREG(st.st_mode) and 10<=st.st_size<=max_size,'FP_SOURCE_FILE_INVALID')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        pre=os.fstat(fd);body=os.read(fd,max_size+1);post=os.fstat(fd)
    finally:os.close(fd)
    verify((pre.st_ino,pre.st_mtime_ns,pre.st_size)==
           (post.st_ino,post.st_mtime_ns,post.st_size) and len(body)<=max_size,
           'FP_SOURCE_FILE_CHANGED')
    obj=json.loads(body)
    verify(isinstance(obj,dict),'FP_JSON_NOT_OBJECT')
    return obj

def timestamp(value):
    try:
        d=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        verify(d.tzinfo is not None,'FP_TIMESTAMP_WITHOUT_TIMEZONE')
        return d.timestamp()
    except (TypeError,OverflowError,AttributeError) as exc:
        raise ValueError('FP_TIMESTAMP_INVALID') from exc

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    verify(spec is not None and spec.loader is not None,'ORIGINAL_APEX_LIBRARY_MISSING')
    o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o);return o

def universe():
    cfg=read(REG,100_000)
    verify(cfg.get('schema')=='abutron.fpmarkets.registry.v1' and
        cfg.get('broker')=='FP Markets' and cfg.get('execution_enabled') is False,
        'FP_REGISTRY_NOT_TRUSTED')
    syms={x['canonical']:set(x['aliases']) for x in cfg['targets']}
    verify(len(syms)==13 and tuple(cfg['timeframes'])==FRAMES,'FP_REGISTRY_CHANGED')
    return syms

def authenticated_heartbeat_read(hb,expected,now,*,pause=time.sleep):
    """Return True only after an exact, stable, fresh native proof read.

    Some MT5 agents rewrite their proof in-place. An intermediate/truncated
    read is retried for <=90ms; no stale, unauthenticated, symlinked, or
    changing proof can ever count as authenticated.
    """
    for attempt in range(3):
        try:
            st=hb.lstat()
            verify(stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode) and
                   -10<=now-st.st_mtime<=17,'FP_HEARTBEAT_STALE')
            fd=os.open(hb,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
            try:
                pre=os.fstat(fd)
                raw=os.read(fd,2001)
                post=os.fstat(fd)
            finally:
                os.close(fd)
            if (len(raw)<=2000 and pre.st_ino==st.st_ino and
                pre.st_mtime_ns==post.st_mtime_ns and
                pre.st_size==post.st_size and
                raw.decode('utf-8-sig').splitlines()==expected):
                return True
        except (OSError,UnicodeError):
            pass
        if attempt<2:
            pause(0.025 if attempt==0 else 0.065)
    return False

def account_check(source,db=ACCOUNTS,private=PRIVATE,now=None):
    now=time.time() if now is None else now
    cid=source.get('connection_id')
    verify(type(cid) is str and len(cid)==32
           and all(x in '0123456789abcdef' for x in cid),'FP_ACCOUNT_ID_INVALID')
    verify((source.get('account_mode'),source.get('broker_server'))==
        ('DEMO','FPMarketsSC-Demo'),'FP_MODE_OR_SERVER_INVALID')
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=6) as c:
        c.execute('PRAGMA query_only=ON')
        row=c.execute("""SELECT a.broker,a.environment,a.broker_server,a.status,
          a.worker_binding,coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
          FROM apex_mt5_connections a LEFT JOIN apex_trade_controls t
          ON a.id=t.connection_id WHERE a.id=?""",(cid,)).fetchone()
    verify(row is not None and tuple(row[:5])==
           ('FP Markets','DEMO','FPMarketsSC-Demo','CONNECTED',
            'abutron-client-mt5-'+cid),'FP_NOT_CONNECTED_READONLY_DEMO')
    # The feed/scanner remain read-only even if an independent order-control
    # service is enabled. Validate control consistency, not OFF-only state.
    desired,effective=row[5],row[6]
    verify(type(desired) is int and type(effective) is int and
           desired in (0,1) and effective in (0,1) and effective<=desired,
           'FP_ACCOUNT_CONTROL_INCONSISTENT')
    root=private/('abutron-client-mt5-'+cid)
    h=read(root/'worker-health.json',20_000)
    nonce=h.get('nonce');owner=h.get('proof_owner')
    verify(h.get('id')==cid and h.get('status')=='CONNECTED' and
        h.get('heartbeat_fresh') is True and h.get('broker')=='FP Markets'
        and h.get('server')=='FPMarketsSC-Demo' and h.get('mode')=='DEMO'
        and type(nonce) is str and len(nonce)==32
        and type(owner) is str and len(owner)==36,'FP_WORKER_NOT_ATTESTED')
    hb=root/'terminal/MQL5/Files'/('ABUTRON_SESSION_HEARTBEAT_V1_'+nonce+'.txt')
    expected=['ABUTRON_MT5_NATIVE_HEARTBEAT_V1',nonce,owner,'FP_MARKETS',
              'FPMarketsSC-Demo','DEMO','CONNECTED','NO_ORDER_FUNCTIONS']
    verify(authenticated_heartbeat_read(hb,expected,now),
           'FP_HEARTBEAT_NOT_AUTHENTIC')
    return cid

def validate(source,summary,syms,fast,smc,*,now=None,db=ACCOUNTS,private=PRIVATE):
    now=time.time() if now is None else now
    verify(source.get('schema')=='abutron.fpmarkets.native.candles.v1'
           and source.get('source')=='FP Markets DEMO MT5'
           and source.get('execution_enabled') is False
           and source.get('orders_submitted')==0,'FP_SOURCE_NOT_NATIVE_READONLY')
    verify(-30<=now-timestamp(source.get('checked_at_utc'))<=130,
           'FP_SOURCE_SNAPSHOT_STALE')
    verify(source.get('timeframes')==list(FRAMES),'FP_TIMEFRAMES_CHANGED')
    verify(summary.get('schema')=='abutron.fpmarkets.feed.readonly.v1'
           and summary.get('native_feeds_complete',0)>=1
           and summary.get('orders_submitted')==0
           and summary.get('execution_enabled') is False
           and 0<=now-timestamp(summary.get('checked_at_utc'))<=130,
           'FP_COLLECTOR_NOT_FRESH')
    verify(any(r.get('connection_id')==source.get('connection_id')
         and r.get('status')=='BROKER_NATIVE_DATA_COMPLETE'
         and r.get('symbol_count')==13 and r.get('fresh_quotes')==13
         and r.get('timeframes_verified')==78 for r in summary.get('connections',[])),
         'FP_NATIVE_ACCOUNT_SUMMARY_MISMATCH')
    cid=account_check(source,db=db,private=private,now=now)
    data=source.get('bars');quotes=source.get('quotes');mapping=source.get('mapping')
    expected=set(syms)
    verify(all(isinstance(v,dict) and set(v)==expected
               for v in (data,quotes,mapping)), 'FP_NATIVE_SYMBOLS_INCOMPLETE')
    for symbol in syms:
        meta=mapping[symbol];q=quotes[symbol]
        verify(meta.get('status')=='MAPPED'
               and meta.get('actual') in syms[symbol]
               and q.get('symbol')==meta.get('actual'),
               'FP_NATIVE_SYMBOL_ALIAS_MISMATCH')
        tick=q.get('time')
        verify(type(tick) is int and -30<=now-tick<=300
               and q.get('broker_clock_offset_seconds')==7200,
               'FP_NATIVE_TICK_STALE_OR_CLOCK_INVALID')
        verify(all(fast.finite(q.get(key)) for key in ('bid','ask'))
               and 0<q['bid']<=q['ask'],'FP_NATIVE_QUOTE_INVALID')
        frames=data[symbol]
        verify(isinstance(frames,dict) and set(frames)==set(FRAMES),
               'FP_NATIVE_FRAMESET_INVALID')
        for tf in FRAMES:
            verify(type(frames[tf]) is list and len(frames[tf])>=60,
                   'FP_NATIVE_HISTORY_INSUFFICIENT')
            smc.validate_bars(frames[tf],tf,now=now,enforce_freshness=True)
    return cid,data

def assess(symbol,bars,fast,smc):
    indicators={tf:fast.frame_state(bars[tf]) for tf in FRAMES}
    m5=indicators['M5'];m15=indicators['M15'];h1=indicators['H1'];h4=indicators['H4']
    m5_direction={'UP':'BUY','DOWN':'SELL'}.get(m5['trend'],'HOLD')
    higher=(m15['trend'],h1['trend'],h4['trend'])
    htf='BUY' if higher==('UP',)*3 else 'SELL' if higher==('DOWN',)*3 else 'MIXED'
    proposal='HOLD';why='M5_AND_HIGHER_TIMEFRAME_NOT_ALIGNED'
    if m5_direction=='HOLD':why='M5_MIXED'
    elif m5_direction!=htf:why='M15_H1_H4_CONFLICT'
    elif m5['atr14']<=0:why='M5_ATR_NOT_POSITIVE'
    elif m5_direction=='BUY' and not 53<=m5['rsi14']<=70:why='M5_BUY_RSI_OUTSIDE_ORIGINAL_RANGE'
    elif m5_direction=='SELL' and not 30<=m5['rsi14']<=47:why='M5_SELL_RSI_OUTSIDE_ORIGINAL_RANGE'
    else:proposal=m5_direction;why='M5_M15_H1_H4_RSI_ALIGNED'
    # Restored original EMA/RSI multi-timeframe APEX scanner: no SMC/ICT
    # entry veto, no hidden continuation/retest approval and no order authority.
    return {'symbol':symbol,'broker':'FP Markets','m5_direction':m5_direction,
         'higher_timeframe_direction':htf,'proposal':proposal,'reason':why,
         'm5_closed_bar':m5['bar_time'],'indicators':indicators,
         'smc':{'status':'REMOVED'},'ict':{'status':'REMOVED'},
         'ai':{'status':'AWAITING_SELECTIVE_TRADINGAGENTS','direction':None},
         'requires_ai_and_smc_and_ict':False,
         'candidate_for_ai':proposal in ('BUY','SELL'),
         'final_decision':'HOLD','orders_enabled':False,
         'execution_authorized':False}

def generate(source,summary,syms,*,now=None,db=ACCOUNTS,private=PRIVATE):
    now=time.time() if now is None else now
    fast=module('original_apex_fast_scanner_fp',str(FAS))
    smc=module('original_apex_smc_ict_fp',str(SMC))
    cid,data=validate(source,summary,syms,fast,smc,now=now,db=db,private=private)
    rows=[assess(sym,data[sym],fast,smc) for sym in syms]
    return {'schema':SCHEMA,'status':'FP_SCANNER_READONLY_ACTIVE',
        'checked_at_utc':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
        'source':'FP Markets DEMO MT5 native completed candles',
        'broker':'FP Markets','account_fingerprint':hashlib.sha256(cid.encode()).hexdigest()[:24],
        'native_market_at_utc':source['checked_at_utc'],
        'symbols':len(rows),'timeframes_per_symbol':len(FRAMES),
        'scanner_proposals':sum(x['proposal']!='HOLD' for x in rows),
        'smc_ict_passed':0,
        'ai_reviews_completed':0,'final_decisions':{'HOLD':len(rows)},
        'policy':'RESEARCH_ONLY_NO_ORDER_AUTHORITY',
        'orders_enabled':False,'execution_authorized':False,
        'account_controls_modified':False,'instruments':rows}

def atomic(path,obj):
    path.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=str(path.parent),prefix='.'+path.name+'.')
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(obj,f,allow_nan=False,separators=(',',':'))
            f.flush();os.fsync(f.fileno())
        os.chmod(name,0o640);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def run(feed=FEED,out=OUT,db=ACCOUNTS,private=PRIVATE):
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=6) as c:
        c.execute('PRAGMA query_only=ON')
        rows=c.execute("""SELECT id FROM apex_mt5_connections
            WHERE broker='FP Markets' AND environment='DEMO'
              AND broker_server='FPMarketsSC-Demo' AND status='CONNECTED'""").fetchall()
    # Select the customer-authorized FP DEMO 0512 feed; 1636 remains OFF.
    matches=[row for row in rows if row[0]=='35b81a287b6a030f2f46ff426b135e6c']
    verify(len(matches)==1,'FP_0512_NATIVE_FEED_NOT_CONNECTED')
    source=read(feed/'market'/(matches[0][0]+'.json'))
    result=generate(source,read(feed/'summary.json'),universe(),db=db,private=private)
    # Original scanner is now authoritative; the retired SMC/ICT setup
    # lifecycle is not consulted or allowed to change qualifying proposals.
    atomic(out/'latest.json',result)
    return {'status':result['status'],'symbols':result['symbols'],
        'scanner_proposals':result['scanner_proposals'],
        'smc_ict_passed':0,'orders_enabled':False}

if __name__=='__main__':
    try:print(json.dumps(run(),sort_keys=True))
    except (OSError,ValueError,TypeError,KeyError,OverflowError,sqlite3.Error) as exc:
        atomic(OUT/'latest.json',{'schema':SCHEMA,'status':'BLOCKED',
             'reason':str(exc)[:160],'symbols':0,'instruments':[],
             'orders_enabled':False,'execution_authorized':False,
             'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
        print('FP_APEX_SCANNER_BLOCKED '+str(exc)[:160],file=sys.stderr)
        raise SystemExit(1)
