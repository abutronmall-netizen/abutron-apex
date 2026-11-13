#!/usr/bin/env python3
"""FP Markets DEMO and LIVE native-symbol/price/bar intake. Read-only and fail-closed.
Never imports/order-routes Deriv execution; never synthesizes broker quotes.
"""
from __future__ import annotations
import hashlib,json,math,os,re,sqlite3,stat,time,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
REG=json.loads((BASE/'registry.json').read_text())
DB=Path('/var/lib/apex-signup/accounts.sqlite3')
STATE=Path('/var/lib/private')
OUTPUT=Path(os.environ.get('ABUTRON_FP_FEED_OUTPUT','/var/lib/abutron-fpmarkets-feed'))
CID=re.compile(r'^[0-9a-f]{32}$')
ALLOWED={"FPMarketsSC-Demo":"DEMO","FPMarketsSC-Demo Server":"DEMO",
 "FPMarketsLtd-Demo2":"DEMO","FPMarketsSC-Live":"LIVE","FPMarketsLtd-Live2":"LIVE"}
TARGET={x['canonical']:set(x['aliases']) for x in REG['targets']}
FRAMES=tuple(REG['timeframes'])
MAX_BARS=13*len(FRAMES)*70
MAX_BYTES=5_000_000
FP_SIDECAR_SHA256='55748a797f1d5d6298fb59d7c438add02051ee14ebb98ff4b729907fd082abe9'
FP_SIDECAR_MAP={'XAUUSD':'XAUUSD.r','USOIL':'XTIUSD'}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def write_atomic(dest, doc):
    dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temp=dest.with_name('.'+dest.name+'.tmp.'+str(os.getpid()))
    with temp.open('x',encoding='utf-8') as h:
        json.dump(doc,h,separators=(',',':'),allow_nan=False)
        h.flush();os.fsync(h.fileno())
    os.chmod(temp,0o600)
    os.replace(temp,dest)

def finite(v, *, positive=False):
    n=float(v)
    if not math.isfinite(n) or (positive and n<=0):
        raise ValueError('INVALID_NUMERIC_FIELD')
    return n

def native_file(path,magic,nonce,owner,server,login,mode,limit=MAX_BYTES,min_lines=9):
    # Do not follow a file redirect planted in a client worker directory.
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size<40 or st.st_size>limit:
        raise ValueError('INVALID_NATIVE_FILE')
    age=time.time()-st.st_mtime
    if age>180 or age< -10: raise ValueError('NATIVE_FILE_STALE')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        pre=os.fstat(fd)
        raw=os.read(fd,limit+1)
        post=os.fstat(fd)
    finally: os.close(fd)
    if len(raw)>limit or pre.st_ino!=st.st_ino or pre.st_mtime_ns!=post.st_mtime_ns or pre.st_size!=post.st_size:
        raise ValueError('NATIVE_FILE_RACED')
    lines=raw.decode('utf-8-sig').splitlines()
    if len(lines)<min_lines or lines[:6]!=[magic,nonce,owner,server,login,mode]:
        raise ValueError('NATIVE_ACCOUNT_PROOF_MISMATCH')
    emitted=int(lines[6])
    if abs(time.time()-emitted)>240:raise ValueError('NATIVE_EXPORT_TIMESTAMP_STALE')
    if not lines[-1].startswith('END\t'):raise ValueError('NATIVE_EXPORT_INCOMPLETE')
    return lines

def attest(cid,server,login,mode):
    if CID.fullmatch(cid) is None or ALLOWED.get(server)!=mode or not login.isdigit():
        raise ValueError('INVALID_ACCOUNT_BINDING')
    worker=STATE/('abutron-client-mt5-'+cid)
    health_file=worker/'worker-health.json'
    h=json.loads(health_file.read_text(encoding='utf-8'))
    if h.get('status')!='CONNECTED' or not h.get('heartbeat_fresh') or h.get('id')!=cid or \
       h.get('broker')!='FP Markets' or h.get('server')!=server or h.get('mode')!=mode:
        raise ValueError('FP_WORKER_NOT_ATTESTED')
    nonce=h.get('nonce')
    owner=h.get('proof_owner')
    if not isinstance(nonce,str) or CID.fullmatch(nonce) is None or \
       not isinstance(owner,str) or len(owner)!=36:
        raise ValueError('INVALID_NATIVE_CHALLENGE')
    heartbeat=worker/'terminal'/'MQL5'/'Files'/('ABUTRON_SESSION_HEARTBEAT_V1_'+nonce+'.txt')
    st=heartbeat.lstat()
    if not stat.S_ISREG(st.st_mode) or time.time()-st.st_mtime>17 or time.time()-st.st_mtime < -10:
        raise ValueError('FP_DEMO_HEARTBEAT_STALE')
    lines=heartbeat.read_text(encoding='utf-8-sig').splitlines()
    if lines!=['ABUTRON_MT5_NATIVE_HEARTBEAT_V1',nonce,owner,
               'FP_MARKETS',server,mode,'CONNECTED','NO_ORDER_FUNCTIONS']:
        raise ValueError('FP_DEMO_HEARTBEAT_REJECTED')
    return worker/'terminal'/'MQL5'/'Files',nonce,owner

def catalog(lines):
    available=set()
    mapped={}
    maps=0
    for line in lines[8:-1]:
        row=line.split('\t')
        if row[0]=='S' and len(row)==3:
            if len(row[1])>160 or not row[1]:raise ValueError('CATALOG_SYMBOL_NAME_INVALID')
            available.add(row[1])
        elif row[0]=='M' and len(row)==9:
            _,canonical,actual,status,trade_mode,contract,vmin,vstep,digits=row
            if canonical not in TARGET or canonical in mapped:
                raise ValueError('CATALOG_CANONICAL_DUPLICATE')
            if status not in {'MAPPED','MISSING','AMBIGUOUS'}:raise ValueError('CATALOG_STATUS_INVALID')
            if status=='MAPPED' and (actual not in TARGET[canonical] or actual not in available):
                raise ValueError('CATALOG_ALIAS_NOT_VERIFIED')
            if status!='MAPPED' and actual!='':raise ValueError('CATALOG_UNVERIFIED_MAPPING')
            mapped[canonical]={'actual':actual if status=='MAPPED' else None,
              'status':status,'trade_mode':int(trade_mode),'contract_size':finite(contract),
              'min_lot':finite(vmin),'lot_step':finite(vstep),'digits':int(digits)}
            maps+=1
        else:raise ValueError('CATALOG_ROW_INVALID')
    end=lines[-1].split('\t')
    if len(end)!=3 or int(end[1])!=len(available) or int(end[2])!=13 or maps!=13:
        raise ValueError('CATALOG_COUNT_MISMATCH')
    return available,mapped

def infer_broker_clock_offset(lines, *, emitted_utc=None):
    """Estimate integer-hour broker timestamp offset from fresh signed-session tick exports.
    Quotes are broker-native; only timestamps are normalized to UTC. A cohort of
    >=5 independent symbols must agree with a single whole-hour offset.
    """
    if emitted_utc is None:
        emitted_utc=int(lines[6])
    if abs(time.time()-emitted_utc)>240:
        raise ValueError('BROKER_CLOCK_EXPORT_STALE')
    delta=[]
    for raw in lines[7:-1]:
        fields=raw.split('\t')
        if len(fields)!=5:raise ValueError('QUOTE_ROW_INVALID')
        _,_,ts,bid,ask=fields
        tick=int(ts)
        b=finite(bid,positive=True);a=finite(ask,positive=True)
        if a<b:raise ValueError('QUOTE_BID_ASK_INVALID')
        delta.append(tick-emitted_utc)
    if len(delta)<5:
        raise ValueError('BROKER_CLOCK_INSUFFICIENT_QUOTES')
    med=statistics.median(delta)
    candidate=int(round(med/3600.0))*3600
    if abs(candidate)>14*3600 or abs(med-candidate)>150:
        raise ValueError('BROKER_CLOCK_OFFSET_UNVERIFIED')
    # A strict majority of broker ticks must establish the clock.
    # Closed-market stale ticks cannot influence the clock or reach consumers.
    inliers=[v for v in delta if -300<=v-candidate<=30]
    if any(v-candidate>30 for v in delta) or len(inliers)<5 or len(inliers)*2<=len(delta):
        raise ValueError('BROKER_CLOCK_QUOTE_COHORT_INCONSISTENT')
    return candidate

def quotes(lines,mapping, *, offset_seconds=0):
    result={}
    seen=set()
    actual_count=0
    for line in lines[7:-1]:
        row=line.split('\t')
        if len(row)!=5:raise ValueError('QUOTE_ROW_INVALID')
        canonical,actual,utc,bid,ask=row
        if canonical not in TARGET or canonical in seen or \
           mapping[canonical]['actual']!=actual:
            raise ValueError('QUOTE_SYMBOL_MISMATCH')
        seen.add(canonical)
        actual_count+=1
        raw_time=int(utc); n=raw_time-offset_seconds
        b=finite(bid,positive=True);a=finite(ask,positive=True)
        now=time.time()
        if a<b or n>now+30 or n<0:raise ValueError('QUOTE_BID_ASK_INVALID')
        # A closed/illiquid instrument never qualifies as a fresh market quote.
        if now-n>300:continue
        result[canonical]={'symbol':actual,'time':n,'broker_time_raw':raw_time,
                           'broker_clock_offset_seconds':offset_seconds,
                           'bid':b,'ask':a,'age_seconds':round(time.time()-n,2)}
    end=lines[-1].split('\t')
    if len(end)!=2 or int(end[1])!=actual_count:raise ValueError('QUOTE_COUNT_MISMATCH')
    return result

def bars(lines,mapping, *, offset_seconds=0):
    points=defaultdict(list)
    actual_count=0
    for line in lines[7:-1]:
        row=line.split('\t')
        if len(row)!=8:raise ValueError('BAR_ROW_INVALID')
        canonical,actual,frame,utc,op,hi,lo,cl=row
        if canonical not in TARGET or frame not in FRAMES or mapping[canonical]['actual']!=actual:
            raise ValueError('BAR_BROKER_SYMBOL_MISMATCH')
        broker_time_raw=int(utc)
        t=broker_time_raw-offset_seconds
        o,h,l,c=[finite(x,positive=True) for x in (op,hi,lo,cl)]
        if not (l<=min(o,c)<=max(o,c)<=h) or t>time.time()+300 or t<100000000:
            raise ValueError('BAR_OHLC_INVALID')
        key=(canonical,frame)
        if points[key] and t<=points[key][-1]['time']:
            raise ValueError('BAR_ORDER_OR_DUPLICATE_INVALID')
        points[key].append({'time':t,'broker_time_raw':broker_time_raw,
                             'open':o,'high':h,'low':l,'close':c})
        if len(points[key])>70:raise ValueError('BAR_FRAME_LIMIT_EXCEEDED')
        actual_count+=1
        if actual_count>MAX_BARS:raise ValueError('BAR_TOTAL_LIMIT_EXCEEDED')
    end=lines[-1].split('\t')
    if len(end)!=2 or int(end[1])!=actual_count:
        raise ValueError('BAR_COUNT_MISMATCH')
    return points

def sidecar_files(files,nonce,owner,server,login,mode,available,mapping,offset):
    """Accept only exact same authenticated FP MT5 terminal and trusted read-only indicator."""
    indicator=files.parent/'Indicators'/'ABUTRON'/'AbutronFPMarketsNativeSidecarV100.ex5'
    if not indicator.is_file():
        return {},{},False
    if hashlib.sha256(indicator.read_bytes()).hexdigest()!=FP_SIDECAR_SHA256:
        raise ValueError('FP_SIDECAR_BINARY_UNTRUSTED')
    request=files/'ABUTRON_FP_SIDECAR_REQUEST_V1.txt'
    st=request.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size>500 or st.st_size<120:
        raise ValueError('FP_SIDECAR_REQUEST_INVALID')
    content=request.read_text(encoding='utf-8-sig').splitlines()
    if content!=['ABUTRON_FP_SIDECAR_REQUEST_V1',nonce,owner,'FP_MARKETS',server,login,mode]:
        raise ValueError('FP_SIDECAR_REQUEST_BINDING_FAILED')
    def read(kind):
        return native_file(files/('ABUTRON_FP_SIDECAR_'+kind+'_V1_'+nonce+'.txt'),
            'ABUTRON_FP_SIDECAR_'+kind+'_V1',nonce,owner,server,login,mode,min_lines=8)
    ca=read('CATALOG')
    rows=[ln.split('\t') for ln in ca[7:-1]]
    if len(rows)!=2 or ca[-1]!='END\t2':
        raise ValueError('FP_SIDECAR_MAP_COUNT')
    seen=set()
    for row in rows:
        if len(row)!=9 or row[0]!='M':
            raise ValueError('FP_SIDECAR_MAP_ROW_INVALID')
        _,canonical,actual,status,trade,contract,vmin,vstep,digits=row
        if canonical in seen or FP_SIDECAR_MAP.get(canonical)!=actual or \
           canonical not in mapping or actual not in available or actual not in TARGET[canonical] or status!='MAPPED':
            raise ValueError('FP_SIDECAR_UNAUTHORIZED_INSTRUMENT')
        seen.add(canonical)
        mapping[canonical]={'actual':actual,'status':'MAPPED',
            'trade_mode':int(trade),'contract_size':finite(contract,positive=True),
            'min_lot':finite(vmin,positive=True),'lot_step':finite(vstep,positive=True),
            'digits':int(digits)}
    if seen!=set(FP_SIDECAR_MAP):
        raise ValueError('FP_SIDECAR_MAP_INCOMPLETE')
    qlines=read('QUOTES')
    blines=read('BARS')
    q=quotes(qlines,mapping,offset_seconds=offset)
    b=bars(blines,mapping,offset_seconds=offset)
    if any(k not in FP_SIDECAR_MAP for k in q) or any(k[0] not in FP_SIDECAR_MAP for k in b):
        raise ValueError('FP_SIDECAR_DATA_SCOPE_INVALID')
    return q,b,True

# Six executable Forex contracts are obtained only from the independently
# authenticated, read-only V305 exporter. The original native source and
# authenticated XAUUSD/USOIL sidecar remain the authority for other symbols.
FP_V305_SHA256='845c6a30034b2e0b6aa33625e6582b1a9130d568a8621ec980c4aca77455897e'
FP_V305_SHA256_0512='615ba5a53590a90400033a4259f1931a49157b2551b77cde483bc6861c3352b8'
FP_V305_FOREX=('EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF','NZDUSD')
FP_V305_GOLD_OIL=('XAUUSD','USOIL')

def authenticated_v305_subset(files,nonce,owner,server,login,mode,cid,expected_offset,symbols):
    """Broker-native DEMO MQL5 V305 source, same-account and hash attested."""
    if mode!='DEMO' or server!='FPMarketsSC-Demo':
        raise ValueError('FP_V305_DEMO_ONLY')
    binary=STATE/('abutron-client-mt5-'+cid)/'terminal/MQL5/Experts/ABUTRON/AbutronFPMarketsNativeFeedParallelV305.ex5'
    st=binary.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size>250000:
        raise ValueError('FP_V305_BINARY_TYPE_INVALID')
    # Exact verified V306 read-only export is used by FP0512 and now FP2582.
    # All other customers retain their existing pinned independent release.
    expected_sha=(FP_V305_SHA256_0512 if cid in (
        '35b81a287b6a030f2f46ff426b135e6c',
        '6c396441ac5d4b76b2f1ffaf2951beb3') else FP_V305_SHA256)
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=expected_sha:
        raise ValueError('FP_V305_BINARY_HASH_MISMATCH')
    schemas={'CATALOG':'ABUTRON_FP_CATALOG_V1',
             'BARS':'ABUTRON_FP_BARS_V1',
             'QUOTES':'ABUTRON_FP_QUOTES_V1'}
    exports={}
    for kind,magic in schemas.items():
        path=files/('ABUTRON_FP_'+kind+'_V305_'+nonce+'.txt')
        exports[kind]=native_file(path,magic,nonce,owner,server,login,mode)
    _,native_mapping=catalog(exports['CATALOG'])
    offset=infer_broker_clock_offset(exports['QUOTES'])
    if offset!=expected_offset:
        raise ValueError('FP_V305_BROKER_CLOCK_CONFLICT')
    q=quotes(exports['QUOTES'],native_mapping,offset_seconds=offset)
    b=bars(exports['BARS'],native_mapping,offset_seconds=offset)
    overrides={}
    for sym in symbols:
        expected='XTIUSD' if sym=='USOIL' else sym+'.r'
        m=native_mapping.get(sym)
        if not m or (m.get('status'),m.get('actual'),m.get('trade_mode'))!=('MAPPED',expected,4):
            raise ValueError('FP_V305_BROKER_CONTRACT_UNVERIFIED')
        if sym not in q or q[sym]['symbol']!=expected or not -10<=q[sym]['age_seconds']<=300:
            raise ValueError('FP_V305_NATIVE_QUOTE_UNVERIFIED')
        for frame in FRAMES:
            if (sym,frame) not in b or len(b[(sym,frame)])<60:
                raise ValueError('FP_V305_NATIVE_CLOSED_BARS_MISSING')
        overrides[sym]=(m,q[sym],{frame:b[(sym,frame)] for frame in FRAMES})
    if len(overrides)!=len(symbols):
        raise ValueError('FP_V305_SYMBOL_SCOPE_INCOMPLETE')
    return overrides

def authenticated_forex_r(files,nonce,owner,server,login,mode,cid,expected_offset):
    return authenticated_v305_subset(files,nonce,owner,server,login,mode,cid,expected_offset,FP_V305_FOREX)

def authenticated_gold_oil_r(files,nonce,owner,server,login,mode,cid,expected_offset):
    return authenticated_v305_subset(files,nonce,owner,server,login,mode,cid,expected_offset,FP_V305_GOLD_OIL)

def collect_one(cid,owner,broker,mode,server,login,worker_binding,status):
    result={'connection_id':cid,'broker':'FP Markets','mode':mode,
      'checked_at_utc':now_iso(),'status':'BLOCKED','symbol_count':0,
      'timeframes_verified':0,'execution_enabled':False,'orders_submitted':0}
    try:
        if mode not in ('DEMO','LIVE') or ALLOWED.get(server)!=mode or status!='CONNECTED' or worker_binding!='abutron-client-mt5-'+cid:
            raise ValueError('NO_CONNECTED_MATCHING_FP_WORKER')
        files,nonce,proof_owner=attest(cid,server,login,mode)
        ca=native_file(files/('ABUTRON_FP_CATALOG_V1_'+nonce+'.txt'),
            'ABUTRON_FP_CATALOG_V1',nonce,proof_owner,server,login,mode)
        ba=native_file(files/('ABUTRON_FP_BARS_V1_'+nonce+'.txt'),
            'ABUTRON_FP_BARS_V1',nonce,proof_owner,server,login,mode)
        qu=native_file(files/('ABUTRON_FP_QUOTES_V1_'+nonce+'.txt'),
            'ABUTRON_FP_QUOTES_V1',nonce,proof_owner,server,login,mode)
        available,mapping=catalog(ca)
        offset_seconds=infer_broker_clock_offset(qu)
        q=quotes(qu,mapping,offset_seconds=offset_seconds)
        b=bars(ba,mapping,offset_seconds=offset_seconds)
        sidecar_problem=None
        try:
            sidecar_q,sidecar_b,sidecar_active=sidecar_files(
                files,nonce,proof_owner,server,login,mode,available,mapping,offset_seconds)
            if set(q)&set(sidecar_q) or set(b)&set(sidecar_b):
                raise ValueError('FP_SIDECAR_DUPLICATE_BASE_FEED')
            q.update(sidecar_q)
            b.update(sidecar_b)
        except (OSError,ValueError,TypeError,KeyError,OverflowError,UnicodeError) as err:
            # Never trust a stale or invalid sidecar; retain the independently
            # authenticated, already validated original FP native feed.
            sidecar_problem='FP_SIDECAR_'+str(err)[:95]
            sidecar_active=False
            # Restore mapping to the original broker-native catalogue.
            available,mapping=catalog(ca)
        # Overlay ONLY the six validated full-trade .r Forex instruments.
        # This must not reduce baseline index/metal/commodity quote coverage.
        parallel_forex_status='ORIGINAL_V1_FOREX_FALLBACK'
        parallel_forex_blocker=None
        try:
            forex=authenticated_forex_r(
                files,nonce,proof_owner,server,login,mode,cid,offset_seconds)
            for canonical,(native_contract,native_quote,native_frames) in forex.items():
                mapping[canonical]=native_contract
                q[canonical]=native_quote
                for frame,native_bars in native_frames.items():
                    b[(canonical,frame)]=native_bars
            parallel_forex_status='SIX_FOREX_R_VERIFIED_V305'
        except (OSError,ValueError,TypeError,KeyError,OverflowError,UnicodeError) as err:
            parallel_forex_blocker=type(err).__name__
        # Gold/oil are an independent read-only V305 overlay. Their absence
        # must never disable the separately authenticated six Forex contracts.
        gold_oil_status='UNVERIFIED'
        gold_oil_blocker=None
        try:
            additional=authenticated_gold_oil_r(
                files,nonce,proof_owner,server,login,mode,cid,offset_seconds)
            for canonical,(native_contract,native_quote,native_frames) in additional.items():
                mapping[canonical]=native_contract
                q[canonical]=native_quote
                for frame,native_bars in native_frames.items():
                    b[(canonical,frame)]=native_bars
            gold_oil_status='GOLD_OIL_BROKER_NATIVE_V305_VERIFIED'
        except (OSError,ValueError,TypeError,KeyError,OverflowError,UnicodeError) as err:
            gold_oil_blocker=type(err).__name__
        matched=[k for k,x in mapping.items() if x['status']=='MAPPED']
        ready_q=[k for k in matched if k in q and -10<=q[k]['age_seconds']<=300]
        ready_b=[(k,f) for k in matched for f in FRAMES if len(b[(k,f)])>=60]
        result.update({'status':'BROKER_NATIVE_DATA_PARTIAL','symbol_count':len(matched),
         'broker_catalog_count':len(available),'fresh_quotes':len(ready_q),
         'timeframes_verified':len(ready_b),
         'mappings':mapping,
         'stale_or_unquoted_symbols':[k for k in matched if k not in q],
         'native_sidecar_active':sidecar_active,
         'native_sidecar_blocker':sidecar_problem,
         'source':'FP Markets '+mode+' MT5 native','no_simulated_quotes':True,
         'parallel_forex_status':parallel_forex_status,
         'parallel_forex_blocker':parallel_forex_blocker,
         'native_gold_oil_status':gold_oil_status,
         'native_gold_oil_blocker':gold_oil_blocker,
         'broker_clock_offset_seconds':offset_seconds,
         'export_sha256':hashlib.sha256(('\n'.join(ca+ba+qu)).encode()).hexdigest()})
        # Publish authenticated, independently validated partial research data
        # without ever declaring the 13x6 feed certified.
        partial_symbols=[k for k in matched if k in ready_q and all(
            len(b[(k,frame)])>=60 for frame in FRAMES)]
        if partial_symbols:
            partial={'schema':'abutron.fpmarkets.native.partial.readonly.v1',
              'checked_at_utc':now_iso(),'source':'FP Markets '+mode+' MT5 native',
              'status':'PARTIAL_NOT_CERTIFIED','connection_id':cid,
              'account_mode':mode,'broker_server':server,
              'broker_clock_offset_seconds':offset_seconds,
              'symbol_count':len(partial_symbols),'required_symbol_count':13,
              'timeframes':list(FRAMES),'mapping':mapping,
              'parallel_forex_status':parallel_forex_status,
              'quotes':{k:q[k] for k in partial_symbols},
              'bars':{k:{frame:b[(k,frame)] for frame in FRAMES} for k in partial_symbols},
              'execution_enabled':False,'orders_submitted':0}
            write_atomic(OUTPUT/'partial'/(cid+'.json'),partial)
        if len(matched)==13 and len(ready_q)==13 and len(ready_b)==78:
            result['status']='BROKER_NATIVE_DATA_COMPLETE' 
            snapshot={'schema':'abutron.fpmarkets.native.candles.v1',
             'checked_at_utc':now_iso(),'source':'FP Markets '+mode+' MT5',
             'connection_id':cid,'account_mode':mode,'broker_server':server,
             'timeframes':list(FRAMES),'mapping':mapping,'quotes':q,
             'bars':{name:{frame:b[(name,frame)] for frame in FRAMES} for name in matched},
             'execution_enabled':False,'orders_submitted':0}
            write_atomic(OUTPUT/'market'/(cid+'.json'),snapshot)
    except (OSError,ValueError,TypeError,KeyError,OverflowError,UnicodeError,sqlite3.Error) as e:
        result['blocker']=str(e)[:120]
    return result

def collect_with_retry(row, collector=collect_one, pause=time.sleep):
    """Recover transient native-export races without weakening any proof.

    For the one connected FP DEMO account, repeat the *entire* authenticated
    collection on an incomplete result. Never retry disconnected or LIVE
    accounts; never synthesize missing quotes, candles or session evidence.
    The final result alone controls the existing fail-closed cleanup.
    """
    result=collector(*row)
    attempts=1
    if row[2]=='FP Markets' and row[3]=='DEMO' and row[7]=='CONNECTED' and result.get('status')!='BROKER_NATIVE_DATA_COMPLETE':
        for delay in (0.20,0.50):
            pause(delay)
            attempts+=1
            newer=collector(*row)
            result=newer
            if result.get('status')=='BROKER_NATIVE_DATA_COMPLETE':
                break
    result['collection_attempts']=attempts
    result['recovered_transient_collection']=(
        attempts>1 and result.get('status')=='BROKER_NATIVE_DATA_COMPLETE')
    return result

def run():
    with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=5) as c:
        rows=c.execute("""SELECT id,account_id,broker,environment,
          broker_server,account_reference,worker_binding,status
          FROM apex_mt5_connections WHERE broker='FP Markets' ORDER BY id""").fetchall()
    reports=[]
    for cid,owner,broker,mode,server,login,worker,status in rows:
        report=collect_with_retry((cid,owner,broker,mode,server,login,worker,status))
        reports.append(report)
        if report['status']!='BROKER_NATIVE_DATA_COMPLETE' and CID.fullmatch(cid or ''):
            (OUTPUT/'market'/(cid+'.json')).unlink(missing_ok=True)
        if report['status']=='BLOCKED':
            (OUTPUT/'partial'/(cid+'.json')).unlink(missing_ok=True)
    partial_dir=OUTPUT/'partial'
    if partial_dir.exists():
        active={r['connection_id'] for r in reports if r['status'] in
            ('BROKER_NATIVE_DATA_PARTIAL','BROKER_NATIVE_DATA_COMPLETE')}
        for item in partial_dir.glob('*.json'):
            if item.stem not in active:item.unlink(missing_ok=True)
    market_dir=OUTPUT/'market'
    if market_dir.exists():
        valid={r['connection_id'] for r in reports if r['status']=='BROKER_NATIVE_DATA_COMPLETE'}
        for item in market_dir.glob('*.json'):
            if item.stem not in valid: item.unlink(missing_ok=True)
    summary={'schema':'abutron.fpmarkets.feed.readonly.v1',
      'checked_at_utc':now_iso(),'broker':'FP Markets','modes':['DEMO','LIVE'],
      'requested_symbols':list(TARGET),'requested_timeframes':list(FRAMES),
      'fp_accounts_linked':len(rows),'native_feeds_complete':sum(
       x['status']=='BROKER_NATIVE_DATA_COMPLETE' for x in reports),
      'execution_enabled':False,'orders_submitted':0,
      'status':'WAITING_FOR_FP_MARKETS_ACCOUNT_LINK' if not rows else 'FP_MARKETS_RESEARCH_ONLY',
      'connections':reports}
    write_atomic(OUTPUT/'summary.json',summary)
    print('FP_MARKETS_FEED',summary['status'],'ACCOUNTS',len(rows),
          'COMPLETE_FEEDS',summary['native_feeds_complete'],
          'ORDERS_SUBMITTED',summary['orders_submitted'])
    return summary

if __name__=='__main__':
    run()
