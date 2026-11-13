#!/usr/bin/python3
"""Publish actual account-bound Deriv MT5 M5 APEX decisions. No order transport."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, math, os, sqlite3, stat, sys, time

PKG=Path('/opt/abutron-apex11-staging/native-v4-guarded-20261108')
sys.path.insert(0,str(PKG))
from abutron_replacement.production_contracts import read_deriv_native_m5
from abutron_replacement.account_bound_publisher import DecisionJournal,publish_native_m5

CID='1ead1f08b44dc5ae284eadc9554b1381'
BASE=Path('/var/lib/private/abutron-client-mt5-'+CID)
SIDE=Path('/var/lib/private/abutron-native-readonly-mt5-9244/worker-health.json')
DB='file:/var/lib/apex-signup/accounts.sqlite3?mode=ro'
OUTPUT=Path('/var/lib/abutron-apex11-9244')
ALLOWED=('Volatility 10 Index.0','Volatility 25 Index.0','Volatility 50 Index.0',
         'Volatility 75 Index.0','Volatility 100 Index.0')

def secure_json(p,limit,age):
    if p.is_symlink():raise ValueError('UNTRUSTED_SYMLINK')
    with p.open('rb') as f:
        st=os.fstat(f.fileno())
        if (not stat.S_ISREG(st.st_mode) or st.st_mode&0o022 or
                st.st_size<5 or st.st_size>limit or not -2<=time.time()-st.st_mtime<=age):
            raise ValueError('UNTRUSTED_FILE_AGE_MODE_OR_SIZE')
        raw=f.read(limit+1)
        after=os.fstat(f.fileno())
        if len(raw)!=st.st_size or (st.st_ino,st.st_mtime_ns,st.st_size)!=(after.st_ino,after.st_mtime_ns,after.st_size):
            raise ValueError('UNTRUSTED_FILE_RACE')
    return json.loads(raw)

def inspect_inputs():
    with sqlite3.connect(DB,uri=True,timeout=6) as c:
        c.execute('pragma query_only=on')
        rows=c.execute("""SELECT x.account_id,x.account_reference,x.broker_server,
                x.status,a.status FROM apex_mt5_connections x JOIN accounts a ON a.id=x.account_id
                WHERE x.id=? AND x.broker='Deriv' AND x.environment='DEMO'""",(CID,)).fetchall()
    if len(rows)!=1:raise ValueError('CRM_CONNECTION_NOT_UNIQUE')
    owner,login,server,connected,approved=rows[0]
    if (not isinstance(owner,str) or len(owner)!=32 or
        str(login)!='202699244' or server!='Deriv-Demo' or
        connected!='CONNECTED' or approved!='approved'):
        raise ValueError('CRM_NATIVE_IDENTITY_OR_OWNER_NOT_APPROVED')
    h=secure_json(BASE/'worker-health.json',30000,20)
    s=secure_json(SIDE,30000,35)
    nonce=h.get('nonce','')
    if (h.get('id')!=CID or h.get('broker')!='Deriv' or h.get('mode')!='DEMO'
       or h.get('server')!=server or h.get('status')!='CONNECTED'
       or h.get('heartbeat_fresh') is not True or len(nonce)!=32
       or s.get('broker')!='Deriv' or s.get('environment')!='DEMO'
       or s.get('status')!='CONNECTED'
       or s.get('broker_session_identity_verified') is not True
       or s.get('native_history_source_authenticated') is not True
       or s.get('execution_authority') is not False
       or s.get('orders_submitted')!=0
       or not -2<=time.time()-float(s.get('broker_checked_utc',0))<=35):
        raise ValueError('INDEPENDENT_NATIVE_ACCOUNT_AUTHENTICATION_MISSING')
    return owner,str(login),server,nonce

def run():
    owner,login,server,nonce=inspect_inputs()
    folder=BASE/'terminal/MQL5/Files'
    streams=read_deriv_native_m5(
        connection_id=CID,health_path=BASE/'worker-health.json',
        bars_path=folder/('ABUTRON_NATIVE_BARS_V2_'+nonce+'.txt'),
        account_path=folder/('ABUTRON_NATIVE_ACCOUNT_V2_'+nonce+'.txt'),
        login=login,server=server)
    if (OUTPUT.is_symlink() or OUTPUT.stat().st_uid!=0 or
        OUTPUT.stat().st_mode&0o077):
        raise ValueError('UNTRUSTED_REPORT_DESTINATION')
    journal=DecisionJournal(OUTPUT/'account-bound-m5-journal.sqlite3')
    result=[]
    at=datetime.now(timezone.utc)
    for symbol in ALLOWED:
        feed=streams.get(symbol)
        if not feed:raise ValueError('VERIFIED_NATIVE_SYMBOL_FEED_MISSING')
        # Explicitly research-only until real broker instrument specs/costs are bound.
        instrument=dict(symbol=symbol,broker='deriv',asset_class='deriv_synthetic',
                        tick_size=0.001,spread_bps=3.0,commission_bps=0.0,
                        annual_vol=0.75,max_weight=0.2,timeframe_seconds=300)
        publication=publish_native_m5(feed=feed,instrument=instrument,
           customer_id=owner,account_id=CID,journal=journal,now=at,
           supervisor_attested=True)
        result.append(dict(symbol=symbol,status=publication.status,
             publication_id=publication.publication_id,
             broker_order_authorized=publication.broker_order_authorized,
             orders_submitted=publication.orders_submitted))
    report=dict(schema='abutron.apex11.9244.account_bound_publications.readonly.v1',
         checked_utc=at.isoformat(),state='ACCOUNT_BOUND_M5_SHADOW_JOURNALED',
         account_suffix='9244',source='INDEPENDENT_DERIV_DEMO_WORKER_AND_NATIVE_M5',
         cost_manifest_source='RESEARCH_ASSUMPTIONS_NOT_BROKER_VERIFIED',
         publications=result,orders_submitted=0,
         broker_order_authorized=False,crm_modified=False,
         native_requests_queued=0,live_execution_enabled=False)
    path=OUTPUT/('account-bound-publisher.'+str(os.getpid())+'.tmp')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(report,f,sort_keys=True,separators=(',',':'));f.write('\n')
            f.flush();os.fsync(f.fileno())
        os.replace(path,OUTPUT/'account-bound-publisher-latest.json')
    finally:path.unlink(missing_ok=True)
    print(json.dumps({'state':report['state'],
        'published':len(result),'new':sum(x['status'].startswith('PUBLISHED') for x in result),
        'orders':0}))

if __name__=='__main__':
    run()
