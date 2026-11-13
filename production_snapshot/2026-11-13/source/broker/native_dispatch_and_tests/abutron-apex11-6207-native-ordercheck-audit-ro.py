#!/usr/bin/env python3
"""Independently match an actual native 6207 MT5 no-send OrderCheck receipt to an APEX order draft.
Never marks native OrderCheck passed without a fresh real on-terminal receipt.
Does not authorize CRM, submit broker orders, or treat manual trades as APEX.
"""
from __future__ import annotations
import json,os,re,stat,sys,time
from pathlib import Path
from decimal import Decimal,InvalidOperation
from datetime import datetime,timezone

BASE=Path('/var/lib/abutron-apex11-6207')
DRAFT=BASE/'exact-order-draft-latest.json'
OUT=BASE/'native-exact-ordercheck-audit.json'
CID='d6fc2524ec373b8d1bc278a8be3ec635'
STATE=Path('/var/lib/private/abutron-client-mt5-'+CID)
RELEASE='/usr/local/lib/abutron-6207-v4/AbutronApexExistingDerivV4_6207.ex5'
EXPECTED_SHA='0581985fdd90b14349468889880cd3b7b4cba83405be8fc874dc6947e37162fe'
HEX64=re.compile('^[0-9a-f]{64}$')

def safe_read(p:Path,uid:int,size=30000,max_age=45):
    if p.is_symlink():raise ValueError('SYMLINK_DENIED')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        a=os.fstat(fd)
        if (not stat.S_ISREG(a.st_mode) or a.st_uid!=uid or
            a.st_mode&0o022 or not 1<a.st_size<=size or
            not -2<=time.time()-a.st_mtime<=max_age):
            raise ValueError('FILE_OWNER_MODE_FRESHNESS_DENIED')
        data=os.read(fd,size+1)
        b=os.fstat(fd)
        if (len(data)!=a.st_size or
            (a.st_dev,a.st_ino,a.st_mtime_ns,a.st_size)!=
            (b.st_dev,b.st_ino,b.st_mtime_ns,b.st_size)):
            raise ValueError('FILE_RACED')
        return data
    finally:os.close(fd)

def verify_receipt(lines,d,nonce,now):
    if len(lines)!=24:return 'BAD_NATIVE_RECEIPT_LENGTH'
    order=d['order']
    try:
        ts=int(lines[12]);ret=int(lines[16])
        stop=Decimal(lines[18]);profit=Decimal(lines[19]);margin=Decimal(lines[20])
        actual={k:Decimal(v) for k,v in (
            ('volume',lines[8]),('price',lines[9]),('sl',lines[10]),('tp',lines[11]))}
        expected={k:Decimal(str(order[k])) for k in actual}
        broker_bid,broker_ask=Decimal(lines[21]),Decimal(lines[22])
    except (ValueError,TypeError,InvalidOperation,KeyError):
        return 'BAD_NATIVE_NUMBERS'
    if (lines[:4]!=['ABUTRON_APEX11_EXACT_CHECK_NATIVE_NO_SEND_V1',nonce,'32456207','Deriv-Demo'] or
        lines[4]!=d['source_decision_id'] or lines[5]!=d['signal_id'] or
        lines[6]!=d['symbol'] or lines[7]!=d['side'] or
        any(actual[k]!=expected[k] for k in ('volume','sl','tp')) or
        not all(v.is_finite() and v>0 for v in (*actual.values(),broker_bid,broker_ask)) or
        broker_bid>broker_ask or
        actual['price']!=(broker_ask if d['side']=='BUY' else broker_bid) or
        not HEX64.fullmatch(lines[5]) or
        str(order.get('magic'))!='73113011' or order['type']!='ORDER_TYPE_'+d['side'] or
        lines[23]!='NO_ORDER_SEND;NO_CRM_CHANGE;NO_BROKER_ACK'):
        return 'APEX_ORDER_NATIVE_RECEIPT_IDENTITY_MISMATCH'
    if not -3<=now-ts<=45 or ts>d['expires_utc']+2:
        return 'NATIVE_PROOF_STALE_OR_EXPIRED'
    if lines[15]!='ORDER_CHECK_CALLED':
        return 'NATIVE_ORDERCHECK_NOT_CALLED'
    if lines[13]!='CHECK_PASS_NO_SEND' or lines[14]!='BROKER_NATIVE_EXACT_CHECK_ONLY':
        return 'NATIVE_ORDERCHECK_NOT_PASSED'
    if ret not in (0,10009) or not stop.is_finite() or not profit.is_finite() or not margin.is_finite():
        return 'NATIVE_ORDERCHECK_RETCODE_OR_PROFIT_INVALID'
    if stop>=0 or profit<=0 or margin<0:
        return 'NATIVE_RISK_RR_INVALID'
    if -stop>Decimal(d['risk_budget_usd']):
        return 'NATIVE_STOP_EXCEEDS_DRAFT_BUDGET'
    if profit/(-stop)<Decimal('1.5'):
        return 'NATIVE_RISK_RR_INVALID'
    return 'NATIVE_EXACT_ORDERCHECK_PROVEN_NO_SEND'

def run():
    now=int(time.time())
    checks=[]
    try:
        d=json.loads(safe_read(DRAFT,0,size=30000,max_age=60))
        h=json.loads(safe_read(STATE/'worker-health.json',STATE.stat().st_uid,
                               size=30000,max_age=20))
        nonce=h['nonce']
        assert h['id']==CID and h['broker']=='Deriv' and h['mode']=='DEMO' and h['server']=='Deriv-Demo'
        assert h['status']=='CONNECTED' and h['heartbeat_fresh'] is True
        assert d['state']=='DRAFT_ONLY_NO_BROKER_ORDER_CHECK_OR_EXECUTION_AUTHORITY'
        for p in d['drafts']:
            key=p.get('signal_id','')
            if not isinstance(key,str) or not HEX64.fullmatch(key):
                checks.append(dict(symbol=p.get('symbol'),status='APEX_SIGNAL_ID_INVALID'))
                continue
            file=STATE/'terminal/MQL5/Files/ABUTRON/execution-audit'/('apex11-check-'+key+'.txt')
            if not file.is_file():
                checks.append(dict(symbol=p['symbol'],status='NO_NATIVE_EXACT_CHECK_RECEIPT'))
                continue
            try:
                lines=safe_read(file,STATE.stat().st_uid,size=4000,max_age=60).decode('utf-8-sig').splitlines()
                result=verify_receipt(lines,p,nonce,now)
            except (ValueError,OSError,UnicodeError) as ex:
                result='UNTRUSTED_NATIVE_RECEIPT_'+str(ex)[:80]
            checks.append(dict(symbol=p['symbol'],status=result))
        status='NATIVE_ORDER_CHECK_VERIFIED_NO_SEND' if bool(checks) and all(x['status']=='NATIVE_EXACT_ORDERCHECK_PROVEN_NO_SEND' for x in checks) else 'NATIVE_ORDER_CHECK_PENDING'
    except Exception as ex:
        checks.append(dict(status='PRODUCTION_SOURCE_UNVERIFIED',reason=type(ex).__name__))
        status='NATIVE_ORDER_CHECK_PENDING'
    report=dict(schema='abutron.apex11.6207.native_ordercheck.independent_audit.v1',
                checked_utc=datetime.now(timezone.utc).isoformat(),
                state=status,checks=checks,
                native_exact_ordercheck_verified=(status=='NATIVE_ORDER_CHECK_VERIFIED_NO_SEND'),
                broker_execution_ack_verified=False,crm_execution_ack_verified=False,
                broker_order_authorized=False,orders_submitted=0,
                manual_trades_excluded_from_apex_signal_provenance=True)
    tmp=OUT.with_name('.native-check.'+str(os.getpid())+'.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(report,f,sort_keys=True,separators=(',',':'));f.write('\n')
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,OUT)
    finally:tmp.unlink(missing_ok=True)
    print(json.dumps({'state':report['state'],'checks':checks,'orders':0}))
if __name__=='__main__':run()
