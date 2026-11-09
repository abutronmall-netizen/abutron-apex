"""APEX protected operator FP Markets read-only UI routes.

Reads root-published sanitized evidence; the reverse proxy applies the existing
/apex/ operator protection. No broker or order APIs.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import json,os,stat,time

PUBLISHED=Path('/var/lib/apex/operator-live/fp-markets-ui.json')
SCHEMA='abutron.fpmarkets.ui.readonly.v1'
FRAMES=('M1','M5','M15','H1','H4','D1')
SYMBOLS=('XAUUSD','BTCUSD','EURUSD','GBPUSD','USDJPY','AUDUSD',
         'US100','US30','SP500','GER40','USOIL','USDCHF','NZDUSD')

def current(path=PUBLISHED,now=None):
 now=time.time() if now is None else float(now)
 st=path.lstat()
 if not stat.S_ISREG(st.st_mode) or not 100<=st.st_size<=1_000_000:
  raise ValueError('FP_UI_FILE_UNTRUSTED')
 fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
 try:
  before=os.fstat(fd);raw=os.read(fd,1_000_001);after=os.fstat(fd)
 finally:os.close(fd)
 if (before.st_ino,before.st_mtime_ns,before.st_size)!=(
     after.st_ino,after.st_mtime_ns,after.st_size) or len(raw)>1_000_000:
  raise ValueError('FP_UI_FILE_CHANGED')
 obj=json.loads(raw)
 timestamp=datetime.fromisoformat(obj['generated_at_utc'].replace('Z','+00:00')).timestamp()
 common=(-30<=now-timestamp<=180
    and obj.get('schema')==SCHEMA and obj.get('available') is True
    and obj.get('environment')=='DEMO' and obj.get('broker')=='FP Markets'
    and obj.get('execution_enabled') is False
    and obj.get('orders_submitted_by_collector')==0
    and isinstance(obj.get('symbols'),list) and len(obj['symbols'])==13
    and {r.get('symbol') for r in obj['symbols'] if isinstance(r,dict)}==set(SYMBOLS))
 complete=(obj.get('fresh_quotes')==13 and obj.get('timeframe_series')==78
    and set(obj.get('candles',{}))==set(SYMBOLS))
 # Partial research is display-only. It never counts as execution-ready,
 # even if every available FP symbol has fresh broker-native candles.
 verified=[r for r in obj.get('symbols',[]) if isinstance(r,dict) and r.get('available') is True]
 missing=[r for r in obj.get('symbols',[]) if isinstance(r,dict) and r.get('available') is False]
 partial=(obj.get('status')=='CONNECTED_PARTIAL'
    and obj.get('source_quality')=='PARTIAL_NOT_CERTIFIED'
    and obj.get('coverage_complete') is False
    and isinstance(obj.get('trading_controls'),dict)
    and set(obj['trading_controls'])=={'desired_enabled','effective_enabled'}
    and all(type(obj['trading_controls'][key]) is bool
            for key in ('desired_enabled','effective_enabled'))
    and (not obj['trading_controls']['effective_enabled']
         or obj['trading_controls']['desired_enabled'])
    and type(obj.get('fresh_quotes')) is int and 1<=obj['fresh_quotes']<13
    and len(verified)==obj['fresh_quotes'] and len(missing)==13-len(verified)
    and obj.get('timeframe_series')==len(verified)*6
    and set(obj.get('candles',{}))=={r['symbol'] for r in verified}
    and set(obj.get('unavailable_symbols',[]))=={r['symbol'] for r in missing}
    and all(r.get('final_decision')=='HOLD' and r.get('orders_enabled') is False
        and r.get('execution_authorized') is False for r in obj['symbols'])
    and all(r.get('proposal')=='HOLD' and r.get('broker_symbol')=='UNAVAILABLE'
        and r.get('m5_bar_time') is None and r.get('smc')=='VETO'
        and r.get('ict')=='VETO' for r in missing)
    and all(r.get('broker_status')=='MAPPED' and r.get('symbol') in obj['candles']
        for r in verified))
 if not common or not (complete or partial):
  raise ValueError('FP_UI_FEED_STALE_OR_UNVERIFIED')
 return obj

def overview(*,path=PUBLISHED,now=None):
 try:
  d=current(path,now=now)
  return {k:v for k,v in d.items() if k!='candles'}
 except (OSError,ValueError,TypeError,KeyError,OverflowError,UnicodeError):
  return {'schema':SCHEMA,'available':False,'broker':'FP Markets',
     'reason':'FP broker-native UI evidence unavailable or stale',
     'execution_enabled':False,'symbols':[]}

def chart(symbol,frame,path=PUBLISHED,now=None):
 if symbol not in SYMBOLS:raise KeyError('FP_SYMBOL_UNKNOWN')
 if frame not in FRAMES:raise KeyError('FP_FRAME_UNKNOWN')
 d=current(path,now=now)
 if symbol not in d['candles']:
  raise KeyError('FP_BROKER_SYMBOL_UNAVAILABLE')
 cand=d['candles'][symbol][frame]
 if not isinstance(cand,list) or len(cand)<60:
  raise ValueError('FP_NATIVE_BARS_MISSING')
 bars=[{'t':int(r[0]),'o':float(r[1]),'h':float(r[2]),'l':float(r[3]),'c':float(r[4])}
       for r in cand]
 return {'ok':True,'broker':'FP Markets','environment':'DEMO',
    'source':'FP Markets MT5 native completed candles',
    'symbol':symbol,'timeframe':frame,'bars':bars,
    'generated_at_utc':d['generated_at_utc'],
    'execution_enabled':False}


# Independently published FP DEMO operator data. The reverse proxy protects /apex/.
# Each publication is broker-native and fail-closed; no private client files read.
MULTI=Path('/var/lib/apex/operator-live')
import re
ACCOUNT_FILE=re.compile(r'^fp-market-account-[0-9a-f]{32}\.json$')

def account_paths():
    files=[PUBLISHED]
    files.extend(sorted(p for p in MULTI.glob('fp-market-account-*.json')
                        if ACCOUNT_FILE.fullmatch(p.name)))
    return files[:6]

def accounts():
    rows=[]
    for slot,path in enumerate(account_paths()):
        doc=overview(path=path)
        rows.append({'slot':slot,'available':doc.get('available') is True,
                     'account_masked':doc.get('account_masked','UNVERIFIED'),
                     'status':doc.get('status','UNVERIFIED'),
                     'fresh_quotes':doc.get('fresh_quotes',0),
                     'required_quotes':13,
                     'timeframe_series':doc.get('timeframe_series',0),
                     'coverage_complete':doc.get('coverage_complete') is True,
                     'source_quality':doc.get('source_quality','UNVERIFIED'),
                     'trading_controls':doc.get('trading_controls',{}),
                     'execution_enabled':False})
    return {'schema':'abutron.fpmarkets.operator.accounts.readonly.v1',
            'accounts':rows,'account_count':len(rows),'execution_authorized':False}

def account_overview(slot):
    paths=account_paths()
    if type(slot) is not int or not 0<=slot<len(paths):
        raise KeyError('FP_OPERATOR_SLOT_UNAVAILABLE')
    return overview(path=paths[slot])

def account_chart(slot,symbol,frame):
    paths=account_paths()
    if type(slot) is not int or not 0<=slot<len(paths):
        raise KeyError('FP_OPERATOR_SLOT_UNAVAILABLE')
    return chart(symbol,frame,path=paths[slot])
