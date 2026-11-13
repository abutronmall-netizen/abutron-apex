#!/usr/bin/env python3
"""Stage exactly one fresh APEX 1.1 Deriv 6207 DEMO OrderCheck-only request.
No OrderSend, broker/CRM switch, order intent, permission escalation, or retry of consumed signal.
"""
from __future__ import annotations
import hashlib,json,os,re,stat,sys,time
from pathlib import Path

CID='d6fc2524ec373b8d1bc278a8be3ec635'
STATE=Path('/var/lib/private/abutron-client-mt5-'+CID)
OUT=Path('/var/lib/abutron-apex11-6207/exact-order-draft-latest.json')
EA=STATE/'terminal/MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_6207.ex5'
EXPECTED='c8422e0a98f9e02570b6f8b77e5cf890fd66676e1aa3b3cf9f7e552d08322d43'
REQ=STATE/'terminal/MQL5/Files/ABUTRON/APEX11_EXACT_CHECK_ONLY.req'
AUD=STATE/'terminal/MQL5/Files/ABUTRON/execution-audit'
HEX64=re.compile('^[a-f0-9]{64}$')
HEX32=re.compile('^[a-f0-9]{32}$')

def read(path,uid,limit,age):
    if path.is_symlink():raise RuntimeError('SOURCE_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=uid or st.st_mode&0o022 or
            st.st_size<=0 or st.st_size>limit or not -3<=time.time()-st.st_mtime<=age):
            raise RuntimeError('SOURCE_UNTRUSTED_AGE_OR_PERMISSIONS')
        raw=os.read(fd,limit+1)
        after=os.fstat(fd)
        if (len(raw)!=st.st_size or
            (st.st_dev,st.st_ino,st.st_mtime_ns,st.st_size)!=(after.st_dev,after.st_ino,after.st_mtime_ns,after.st_size)):
            raise RuntimeError('SOURCE_CHANGED_DURING_READ')
        return raw
    finally:os.close(fd)

def run():
    now=int(time.time())
    if hashlib.sha256(EA.read_bytes()).hexdigest()!=EXPECTED:
        raise RuntimeError('NATIVE_EA_WRONG_BINARY')
    uid=STATE.stat().st_uid
    health=json.loads(read(STATE/'worker-health.json',uid,30000,20))
    nonce=health.get('nonce','')
    if (not isinstance(nonce,str) or not HEX32.fullmatch(nonce) or
        health.get('id')!=CID or health.get('broker')!='Deriv' or
        health.get('mode')!='DEMO' or health.get('server')!='Deriv-Demo' or
        health.get('status')!='CONNECTED' or health.get('heartbeat_fresh') is not True):
        raise RuntimeError('NATIVE_DEMO_WORKER_NOT_AUTHENTIC')
    src=json.loads(read(OUT,0,40000,40))
    if src.get('schema')!='abutron.apex11.6207.order_draft_inspection.ro.v1' or src.get('orders_submitted')!=0:
        raise RuntimeError('UNTRUSTED_APEX_DRAFT')
    if REQ.exists():raise RuntimeError('UNCERTAIN_PENDING_NATIVE_CHECK_REQUEST')
    selected=None
    for d in src.get('drafts',[]):
        key=d.get('signal_id','')
        if not isinstance(key,str) or not HEX64.fullmatch(key):continue
        if (not d.get('source_decision_id') or not HEX64.fullmatch(d['source_decision_id'])
            or d.get('broker')!='Deriv' or d.get('environment')!='DEMO' or
            d.get('connection_id')!=CID or d.get('dispatch_authorized') is not False
            or d.get('broker_exact_ordercheck_verified') is not False):
            continue
        if not now+4<d.get('expires_utc',0):continue
        if (AUD/('apex11-check-'+key+'.consumed')).exists() or (AUD/('apex11-check-'+key+'.txt')).exists():
            continue
        selected=d
        break
    if selected is None:
        print(json.dumps({'state':'NO_NEW_FRESH_APEX_DECISION','checks_requested':0,'orders_submitted':0}));return
    d=selected; o=d['order']
    for n in ('volume','price','sl','tp'):
        s=o.get(n,'')
        if not isinstance(s,str) or not s or not s.isascii() or any(c not in '0123456789.' for c in s):
            raise RuntimeError('APEX_ORDER_NUMERIC_INVALID')
    assert o['type']=='ORDER_TYPE_'+d['side'] and int(o['magic'])==73113011
    lines=['ABUTRON_APEX11_EXACT_CHECK_NO_SEND_V1',nonce,'32456207','Deriv-Demo',
           d['source_decision_id'],d['signal_id'],d['symbol'],d['side'],
           o['volume'],o['price'],o['sl'],o['tp'],str(now+9),'CHECK_ONLY_NEVER_SEND']
    raw=('\r\n'.join(lines)+'\r\n').encode('ascii')
    assert len(lines)==14 and len(raw)<1500
    folder=REQ.parent
    if folder.is_symlink() or not folder.is_dir():raise RuntimeError('NATIVE_REQUEST_FOLDER_INVALID')
    dirfd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    name='.check-'+d['signal_id']+'.tmp'
    try:
        fd=os.open(name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=dirfd)
        try:
            os.fchown(fd,uid,os.fstat(dirfd).st_gid)
            with os.fdopen(fd,'wb') as f:
                f.write(raw);f.flush();os.fsync(f.fileno())
            os.link(name,REQ.name,src_dir_fd=dirfd,dst_dir_fd=dirfd,follow_symlinks=False)
            os.fsync(dirfd)
        finally:
            os.unlink(name,dir_fd=dirfd)
    finally:os.close(dirfd)
    print(json.dumps({'state':'NATIVE_ORDER_CHECK_ONLY_REQUEST_QUEUED',
        'symbol':d['symbol'],'side':d['side'],'signal_id':d['signal_id'],
        'expires_utc':now+9,'broker_order_authority':False,'orders_submitted':0}))

if __name__=='__main__':run()
