#!/usr/bin/env python3
"""ABUTRON live FORWARD SHADOW journal. Read-only broker market; no order/EA controls."""
from __future__ import annotations
import datetime as dt,hashlib,json,math,os,sqlite3,sys,time,grp,tempfile
from pathlib import Path
sys.path[:0]=['/opt/apex/runtime','/opt/apex-client-mt5/quant-first']
import apex_fast_scanner as fast
import abutron_quant_first_v1 as quant
from abutron_cost_aware_replay_v2 import stop_first
SOURCE=Path('/var/lib/apex/operator-live/native-market.json')
ROOT=Path('/var/lib/abutron-quant-first')
DB=ROOT/'forward-cost-shadow-v1.sqlite3'
OUT=ROOT/'forward-cost-shadow-latest.json'
SYMS=tuple(sorted(quant.DERIV_SCOPE))
SCHEMA='abutron.quant.forward_cost.shadow.v1'
MAX_SIGNAL_AGE=480
HOLD_BARS=12

def digest(bar):
    return hashlib.sha256(json.dumps([bar[k] for k in ('time','open','high','low','close')],separators=(',',':')).encode()).hexdigest()

def source_data(path=SOURCE,now=None):
    now=dt.datetime.now(dt.timezone.utc) if now is None else now
    if path.is_symlink() or not path.is_file() or path.stat().st_size>8_000_000:
        raise ValueError('UNTRUSTED_OR_OVERSIZED_BROKER_DATA')
    st=path.stat();doc=json.loads(path.read_text(encoding='utf-8'))
    if (path.stat().st_size,path.stat().st_mtime_ns)!=(st.st_size,st.st_mtime_ns):
        raise ValueError('BROKER_DATA_CHANGED_DURING_READ')
    universe=fast.validate_snapshot(doc,now)
    if any(s not in universe for s in SYMS):
        raise ValueError('MISSING_DERIV_BROKER_SYMBOL')
    for symbol in SYMS:
        bar=universe[symbol]['M5'][-1]
        age=now.timestamp()-(bar['time']+300)
        if not -10 <= age <= MAX_SIGNAL_AGE:
            raise ValueError('STALE_M5_FORWARD_ONLY_DENIED')
    return universe

def init_db(c):
    c.execute("""CREATE TABLE IF NOT EXISTS observations(
        symbol TEXT NOT NULL,model TEXT NOT NULL,bar_time INTEGER NOT NULL,
        recorded_utc TEXT NOT NULL,side TEXT NOT NULL,atr REAL NOT NULL,
        bar_digest TEXT NOT NULL,status TEXT NOT NULL,exit_reason TEXT,
        gross_bps REAL,settled_utc TEXT,PRIMARY KEY(symbol,model,bar_time)
    )""")
    c.execute('CREATE INDEX IF NOT EXISTS idx_observations_pending ON observations(status,bar_time)')

def evaluate_pending(c,source,now):
    completed=invalid=0
    for sym,model,bar_time,side,atr,hash_expected in c.execute(
        "SELECT symbol,model,bar_time,side,atr,bar_digest FROM observations WHERE status='PENDING'").fetchall():
        bars=source.get(sym,{}).get('M5',[])
        idx=next((i for i,r in enumerate(bars) if r.get('time')==bar_time),None)
        if idx is None:
            # Do not silently infer outcomes if future candles disappeared.
            if bars and bars[-1]['time']-bar_time>100*300:
                c.execute("UPDATE observations SET status='UNVERIFIABLE_GAP',settled_utc=? WHERE symbol=? AND model=? AND bar_time=?",
                     (now.isoformat(),sym,model,bar_time));invalid+=1
            continue
        if digest(bars[idx])!=hash_expected:
            c.execute("UPDATE observations SET status='SOURCE_CANDLE_REVISED',settled_utc=? WHERE symbol=? AND model=? AND bar_time=?",
                     (now.isoformat(),sym,model,bar_time));invalid+=1
            continue
        if idx+HOLD_BARS>=len(bars):continue
        outcome=stop_first(bars,idx,side,atr,horizon=HOLD_BARS)
        if outcome is None:
            c.execute("UPDATE observations SET status='UNVERIFIABLE_GAP',settled_utc=? WHERE symbol=? AND model=? AND bar_time=?",
                     (now.isoformat(),sym,model,bar_time));invalid+=1
            continue
        c.execute("""UPDATE observations SET status='EVALUATED',exit_reason=?,gross_bps=?,settled_utc=?
             WHERE symbol=? AND model=? AND bar_time=?""",
             (outcome['exit_reason'],outcome['gross_bps'],now.isoformat(),sym,model,bar_time))
        completed+=1
    return completed,invalid

def record_now(c,universe,now):
    written=0
    for sym in SYMS:
        frames=universe[sym];bar=frames['M5'][-1]
        a=fast.frame_state(frames['M5'])['atr14']
        direction=fast.evaluate(sym,frames)['proposal']
        quant_direction=quant.assess(sym,frames,'Deriv',now=now.timestamp())['research_bias']
        for model,side in (('apex',direction),('quant',quant_direction)):
            if side not in ('BUY','SELL','HOLD') or not math.isfinite(a) or a<=0:
                raise ValueError('FORWARD_SCANNER_INVALID')
            status='PENDING' if side in ('BUY','SELL') else 'HOLD'
            c.execute("""INSERT OR IGNORE INTO observations
             (symbol,model,bar_time,recorded_utc,side,atr,bar_digest,status)
             VALUES(?,?,?,?,?,?,?,?)""",
             (sym,model,bar['time'],now.isoformat(),side,a,digest(bar),status))
            written+=c.execute('SELECT changes()').fetchone()[0]
    return written

def stats(c):
    rows=c.execute("""SELECT symbol,model,status,side,gross_bps,exit_reason
         FROM observations ORDER BY symbol,model,bar_time""").fetchall()
    result={}
    for sym in SYMS:
        result[sym]={}
        for model in ('apex','quant'):
            x=[r for r in rows if r[0]==sym and r[1]==model]
            measured=[r[4] for r in x if r[2]=='EVALUATED' and r[4] is not None]
            pending=sum(r[2]=='PENDING' for r in x)
            holds=sum(r[2]=='HOLD' for r in x)
            result[sym][model]={
                'decision_candles_seen':len(x),'hold_decisions':holds,'pending_buy_sell':pending,
                'forward_outcomes_measured':len(measured),
                'unverifiable_outcomes':sum(r[2] in ('UNVERIFIABLE_GAP','SOURCE_CANDLE_REVISED') for r in x),
                'gross_mean_bps':round(sum(measured)/len(measured),4) if measured else None,
                'hypothetical_mean_after_20bps':round(sum(y-20 for y in measured)/len(measured),4) if measured else None,
                'historical_or_forward_broker_execution_confirmed':False,
            }
    return result

def run(*,src=SOURCE,db=DB,out=OUT):
    now=dt.datetime.now(dt.timezone.utc)
    universe=source_data(src,now)
    if db.is_symlink() or out.is_symlink():
        raise ValueError('UNSAFE_DESTINATION_LINK')
    if not db.parent.is_dir() or not out.parent.is_dir():
        raise ValueError('DESTINATION_MISSING')
    with sqlite3.connect(str(db),timeout=10) as c:
        c.execute('PRAGMA busy_timeout=10000')
        c.execute('BEGIN IMMEDIATE')
        init_db(c)
        observed=record_now(c,universe,now)
        completed,invalid=evaluate_pending(c,universe,now)
        summary=stats(c)
        c.commit()
        if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise ValueError('FORWARD_JOURNAL_DB_CORRUPT')
    db.chmod(0o640)
    try:os.chown(db,0,grp.getgrnam('apexagent').gr_gid)
    except PermissionError:pass
    payload={
      'schema':SCHEMA,'checked_at_utc':now.isoformat(),
      'mode':'LIVE_BROKER_NATIVE_FORWARD_SHADOW_NO_TRADING',
      'source':'DERIV_MT5_VERIFIED_COMPLETED_CANDLES',
      'new_signal_observations':observed,'new_verified_candle_outcomes':completed,
      'excluded_unverifiable':invalid,'min_forward_outcomes_before_statistical_review':30,
      'cost_assumption':'20_BPS_HYPOTHETICAL_SPREAD_COMMISSIONS_SLIPPAGE_NOT_MEASURED',
      'entry_exit':'NEXT_M5_OPEN_1p2ATR_SL_1p8ATR_TP_MAX_12_M5_STOP_FIRST',
      'broker_fill_proof':False,'order_execution_enabled_by_module':False,
      'orders_submitted':0,'real_trading_switches_modified':False,
      'signal_promotion_authorized':False,'instruments':summary}
    fd,name=tempfile.mkstemp(prefix='.forward-research-',dir=out.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(payload,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.chmod(name,0o640)
        os.chown(name,0,grp.getgrnam('apexagent').gr_gid)
        os.replace(name,out)
    finally:
        if os.path.exists(name):os.unlink(name)
    return payload

if __name__=='__main__':
    print(json.dumps({k:v for k,v in run().items() if k!='instruments'},sort_keys=True))
