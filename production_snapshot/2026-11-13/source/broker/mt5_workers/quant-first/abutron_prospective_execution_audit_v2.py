#!/usr/bin/env python3
"""One-account authenticated MT5 execution audit. READ ONLY; never sends an order."""
from __future__ import annotations
import datetime as dt
import glob
import hashlib
import json
import math
import os
import re
import sqlite3
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path

ACCOUNT_DB=Path('/var/lib/apex-signup/accounts.sqlite3')
PRIVATE=Path('/var/lib/private')
EVIDENCE=Path('/var/lib/abutron-quant-first')
OUTPUT=EVIDENCE/'prospective-execution-audit-readiness-v1.json'
DEPLOYMENT=Path('/var/backups/abutron-6207-audit-one-account-prechange-20261107/audit-deployment-manifest.json')
V212_RELEASE=Path('/var/backups/abutron-five-volatility-prechange-20261107T105218Z/candidate/VERIFIED_V212_AUDIT_RELEASE.json')
HEX64=re.compile(r'^[0-9a-f]{64}$')
HEX32=re.compile(r'^[0-9a-f]{32}$')
SYMS={'Volatility 25 Index.0','Volatility 50 Index.0','Volatility 75 Index.0'}
FIELDS={
 '.client.txt':('ABUTRON_NATIVE_CLIENT_CONTEXT_V1',9),
 '.request.txt':('ABUTRON_NATIVE_REQUEST_AUDIT_V1',18),
 '.result.txt':('ABUTRON_NATIVE_RESULT_AUDIT_V1',17),
 '.protected.txt':('ABUTRON_NATIVE_PROTECTED_AUDIT_V1',23)
}

def atomic_json(file,payload):
    if file.is_symlink():raise ValueError('OUTPUT_SYMLINK_NOT_ALLOWED')
    fd,tmp=tempfile.mkstemp(prefix='.execution-audit-',dir=file.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(payload,f,indent=2,allow_nan=False);f.write('\n')
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640);os.replace(tmp,file)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def readlines(file,header,count,max_size=12000):
    if file.is_symlink() or not file.is_file():raise ValueError('INVALID_NATIVE_FILE')
    if file.stat().st_size<=0 or file.stat().st_size>max_size:raise ValueError('SIZE_BOUND')
    rows=file.read_text(encoding='utf-8-sig').splitlines()
    if len(rows)!=count or rows[0]!=header:raise ValueError('NATIVE_FORMAT_OR_HEADER_INVALID')
    return rows

def account():
    with sqlite3.connect('file:'+str(ACCOUNT_DB)+'?mode=ro',uri=True,timeout=5) as db:
        db.execute('pragma query_only=on')
        rows=db.execute("""SELECT id,account_reference,status
                    FROM apex_mt5_connections
                    WHERE broker='Deriv' AND environment='DEMO'""").fetchall()
    rows=[row for row in rows if str(row[1]).endswith('6207')]
    if len(rows)!=1:raise ValueError('UNIQUE_DEMO_6207_NOT_VERIFIED')
    cid,login,status=rows[0]
    if not re.fullmatch(r'[a-f0-9]{32}',str(cid)):raise ValueError('INVALID_ACCOUNT_CONNECTION_ID')
    term=PRIVATE/('abutron-client-mt5-'+cid)/'terminal/MQL5'
    if not term.is_dir() or term.is_symlink():raise ValueError('ACCOUNT_TERMINAL_NOT_VERIFIED')
    return term,str(login),str(status)

def ea_status(files,terminal,login):
    hb=list(files.glob('ABUTRON_SESSION_HEARTBEAT_V1_*.txt'))
    if len(hb)!=1:return False,'UNIQUE_FRESH_HEARTBEAT_MISSING',None
    try:
        h=readlines(hb[0],'ABUTRON_MT5_NATIVE_HEARTBEAT_V1',8)
        nonce=h[1]
        if not HEX32.fullmatch(nonce):return False,'NATIVE_NONCE_INVALID',None
        if hb[0].name!='ABUTRON_SESSION_HEARTBEAT_V1_'+nonce+'.txt':
            return False,'NATIVE_NONCE_FILE_MISMATCH',None
        marker=files/('ABUTRON_EXECUTION_AUDIT_V1_'+nonce+'.txt')
        r=readlines(marker,'ABUTRON_EXECUTION_AUDIT_READY_V1',8)
        now=dt.datetime.now(dt.timezone.utc).timestamp()
        if r[1:4]!=[nonce,login,'Deriv-Demo'] or h[1]!=nonce:
            return False,'MQL5_AUDIT_ACCOUNT_MISMATCH',None
        if abs(now-int(r[4]))>20 or now-marker.stat().st_mtime>20:
            return False,'MQL5_AUDIT_CAPABILITY_STALE',None
        if r[6]!='1' or r[7]!='1':return False,'MQL5_ADAPTIVE_PROOF_INPUT_OFF',None
        binary=terminal/'Experts/ABUTRON/AbutronApexNativeOrderBridgeV2.ex5'
        if not binary.is_file() or binary.is_symlink():return False,'EA_BINARY_UNTRUSTED',None
        digest=hashlib.sha256(binary.read_bytes()).hexdigest()
        if not DEPLOYMENT.exists():return False,'NO_DEPLOYMENT_VERIFICATION_MANIFEST',None
        expected=json.loads(DEPLOYMENT.read_text()).get('new_audit_binary_sha256')
        if expected!=digest:
            # Register a separately verified, account-bound V2.12 release;
            # never rewrite the original V2.11 deployment provenance.
            release=V212_RELEASE
            if release.is_symlink() or not release.is_file():
                return False,'V212_RELEASE_MANIFEST_MISSING',None
            st=release.stat()
            if st.st_uid!=0 or st.st_mode&0o077:
                return False,'V212_RELEASE_MANIFEST_UNTRUSTED',None
            approved=json.loads(release.read_text())
            if (approved.get('schema')!='abutron.6207.v212.provenance.v1' or
                approved.get('target_suffix')!='6207' or
                approved.get('broker')!='Deriv' or
                approved.get('environment')!='DEMO' or
                approved.get('new_ea_version')!='2.12' or
                approved.get('previous_audit_manifest_expected_hash')!=expected or
                approved.get('new_audit_binary_sha256')!=digest or
                approved.get('native_ea_identity_verified') is not True):
                return False,'V212_RELEASE_PROVENANCE_MISMATCH',None
            worker=Path('/opt/apex-client-mt5/worker_feed_v4_usd50_canary.py')
            overlay=Path('/opt/apex-client-mt5/overrides/deriv-demo-6207-execution-audit-v1/AbutronApexNativeOrderBridgeV2.ex5')
            if (worker.is_symlink() or overlay.is_symlink() or not worker.is_file() or not overlay.is_file() or
                hashlib.sha256(worker.read_bytes()).hexdigest()!=approved.get('new_worker_sha256') or
                hashlib.sha256(overlay.read_bytes()).hexdigest()!=digest):
                return False,'V212_RELEASE_OVERLAY_OR_WORKER_DRIFT',None
            proof=files/('ABUTRON_6207_RISK_PATCH_V212_'+nonce+'.txt')
            rows=readlines(proof,'ABUTRON_6207_ADAPTIVE_RISK_PATCH_V212',5,1024)
            if (rows[1:4]!=[nonce,login,'Deriv-Demo'] or
                not 0<=now-int(rows[4])<=20 or
                now-proof.stat().st_mtime>20):
                return False,'V212_RUNTIME_MARKER_STALE_OR_WRONG_ACCOUNT',None

        return True,'FRESH_NATIVE_AUDIT_EA_READY',nonce
    except (OSError,UnicodeError,ValueError,IndexError,TypeError) as e:
        return False,'AUDIT_MARKER_OR_HASH_INVALID_'+type(e).__name__,None

def validate_capture(paths,nonce,login):
    """Interpret authentic native files, fail closed on absent, stale, or inconsistent links."""
    try:
        records={}
        for suffix,(header,n) in FIELDS.items():
            records[suffix]=readlines(paths[suffix],header,n)
        c,q,r,p=[records[x] for x in FIELDS]
        k=c[1]
        if not HEX64.fullmatch(k) or any(x[1]!=k for x in (q,r,p)):
            raise ValueError('SIGNAL_KEY_MISMATCH')
        if any(x[2:5]!=[nonce,login,'Deriv-Demo'] for x in (c,q,r,p)):
            raise ValueError('NATIVE_ACCOUNT_NONCE_MISMATCH')
        if any(x[5:7]!=c[5:7] for x in (q,p)):
            raise ValueError('SYMBOL_SIDE_MISMATCH')
        sym,side=c[5],c[6]
        if sym not in SYMS or side not in ('BUY','SELL'):
            raise ValueError('UNAPPROVED_SYMBOL_OR_SIDE')
        created=int(c[7]);backend_mono=int(c[8]);send_utc=int(r[5]);send_mono=int(r[6])
        response_utc=int(r[7]);response_mono=int(r[8]);protected_utc=int(p[21])
        # Client and MQL5 use the same host UTC clock with second-granularity MQL5 proof.
        if not (created>0 and backend_mono>0 and 0<=send_utc-created/1e9<=25
                and send_utc<=response_utc<=protected_utc and
                send_mono<=response_mono and response_mono-send_mono<=90000):
            raise ValueError('INCONSISTENT_CAUSAL_TIMING')
        if r[9]!='1' or int(r[10]) not in (10009,10010):
            raise ValueError('BROKER_SEND_ACK_NOT_VERIFIED')
        order,deal=int(r[12]),int(r[13])
        if order<=0 or deal<=0 or order!=int(p[7]) or deal!=int(p[8]):
            raise ValueError('BROKER_ORDER_DEAL_MISMATCH')
        if int(p[9])<=0 or int(p[12])<=0 or int(p[16])<=0:
            raise ValueError('BROKER_POSITION_OR_FILL_TIME_MISSING')
        requested=float(q[8]);bid=float(q[11]);ask=float(q[12])
        fill=float(p[11]);entry=float(p[13]);sl=float(p[14]);tp=float(p[15])
        if not all(math.isfinite(z) for z in (requested,bid,ask,fill,entry,sl,tp)):
            raise ValueError('NONFINITE_NATIVE_PRICE')
        if min(requested,bid,ask,fill,entry,sl,tp)<=0 or bid>ask:
            raise ValueError('BROKER_PRICE_INVALID')
        if (side=='BUY' and not(sl<entry<tp)) or (side=='SELL' and not(tp<entry<sl)):
            raise ValueError('BROKER_PROTECTION_GEOMETRY_INVALID')
        if p[22]!='OPEN_PROTECTED':raise ValueError('NO_AUTHENTICATED_OPEN_PROTECTED_POSITION')
        if int(q[13])<=0:raise ValueError('NO_NATIVE_QUOTE_TIMESTAMP')
        if abs(float(q[7])-float(p[10]))>1e-8:
            raise ValueError('BROKER_VOLUME_MISMATCH')
        if abs(float(q[9])-sl)>max(abs(sl)*1e-4,0.1) or abs(float(q[10])-tp)>max(abs(tp)*1e-4,0.1):
            raise ValueError('REQUESTED_AND_CONFIRMED_STOPS_DIFFER')
        commission=float(p[18]);fee=float(p[19]);swap=float(p[20])
        if not all(math.isfinite(z) for z in (commission,fee,swap)):
            raise ValueError('NONFINITE_NATIVE_FEES')
        adverse=(fill-requested) if side=='BUY' else (requested-fill)
        return {'signal_key_prefix':k[:12], 'symbol':sym,'side':side,
                'actual_broker_fill_price':fill,'actual_native_requested_price':requested,
                'adverse_slippage_bps':round(adverse/requested*10000,6),
                'quote_spread_bps_at_request':round((ask-bid)/(0.5*(ask+bid))*10000,6),
                'order_send_duration_ms':int(response_mono-send_mono),
                'setup_to_fill_broker_ms':round((int(p[12])-int(p[16])),3),
                'entry_commission_usd':commission,'entry_fee_usd':fee,'entry_swap_usd':swap,
                'broker_sl':sl,'broker_tp':tp,'position_protected':True}
    except (OSError,UnicodeError,ValueError,IndexError,KeyError,OverflowError) as e:
        return {'rejected_reason':str(e)[:140]}

def quote_summary(folder):
    """Sampled two-second MQL5 bid/ask observations, NEVER claimed full tick history."""
    data=defaultdict(list);rows=0
    if not folder.is_dir() or folder.is_symlink():return {},0
    for f in sorted(folder.glob('broker-spread-*.tsv'))[-8:]:
        if f.is_symlink() or f.stat().st_size>30_000_000:continue
        try:
            with f.open(encoding='utf-8-sig') as fh:
                for line in fh:
                    bits=line.strip().split('\t')
                    if len(bits)!=7 or bits[2] not in SYMS:continue
                    recv,mono,sym,quote_ms,bid,ask,spread=bits
                    if int(recv)<=0 or int(quote_ms)<=0:continue
                    x=float(spread);a=float(ask);b=float(bid)
                    if not (math.isfinite(x) and x>=0 and b>0 and a>=b):continue
                    if abs(x-(a-b)*20000/(a+b))>0.05:continue
                    data[sym].append(x);rows+=1
        except (OSError,UnicodeError,ValueError,OverflowError):continue
    summary={}
    for s in SYMS:
        arr=sorted(data[s])
        nonzero=sum(x>0 for x in arr)
        # Zero-spread snapshots can occur on synthetic symbols even while the
        # independent authenticated CopyTicksRange history has positive costs.
        # Never override the broker-native history distribution with these.
        reliable=len(arr)>=100 and nonzero>=max(1,int(len(arr)*.95))
        summary[s]={'quote_samples':len(arr),
                    'nonzero_quote_spread_samples':nonzero,
                    'zero_quote_spread_samples':len(arr)-nonzero,
                    'periodic_snapshot_spread_distribution_eligible':reliable,
                    'median_spread_bps':round(statistics.median(arr),6) if reliable else None,
                    'p95_spread_bps':round(arr[min(len(arr)-1,math.ceil(.95*len(arr))-1)],6) if reliable else None,
                    'zero_spread_snapshot_does_not_prove_zero_execution_cost':True}
    return summary,rows

def main():
    now=dt.datetime.now(dt.timezone.utc)
    result={'schema':'abutron.apex.execution_evidence.readonly.v2',
      'checked_at_utc':now.isoformat(),'mode':'READONLY_NO_BROKER_ORDERS',
      'account_suffix':'6207','active_ea_audit_hook_verified':False,
      'client_created_timestamp_logging_verified':False,
      'mt5_requested_price_logging_verified':False,
      'broker_ack_and_fill_linkage_verified_events':0,
      'protected_native_events':0,'true_request_to_fill_slippage_observations':0,
      'order_submission_allowed':False,'one_order_test_eligible':False,
      'orders_submitted_by_audit':0,
      'live_mt5_accounts_modified':0,'live_eas_modified_by_audit':0}
    try:
        terminal,login,status=account()
        files=terminal/'Files';audit=files/'ABUTRON/execution-audit'
        valid,reason,nonce=ea_status(files,terminal,login)
        result['active_ea_audit_hook_verified']=valid
        result['audit_capability_status']=reason
        result['account_status']=status
        if valid:
            result['mt5_requested_price_logging_verified']=True
            # The immutable client context must actually be produced by
            # the Python native router; do not infer from EA-only timestamps.
            router=Path('/opt/apex-client-mt5/apex_native_order_runtime.py')
            if router.is_file() and 'atomic_audit_client_context(' in router.read_text():
                result['client_created_timestamp_logging_verified']=True
            keys=set()
            if audit.is_dir() and not audit.is_symlink():
                for f in audit.glob('*.request.txt'):
                    key=f.name[:-len('.request.txt')]
                    if HEX64.fullmatch(key):keys.add(key)
            events=[];rejected=[]
            for key in sorted(keys)[-50:]:
                p={suffix:audit/(key+suffix) for suffix in FIELDS}
                event=validate_capture(p,nonce,login)
                if event.get('position_protected'):events.append(event)
                else:rejected.append({'key_prefix':key[:12], **event})
            result['protected_native_events']=len(events)
            result['broker_ack_and_fill_linkage_verified_events']=len(events)
            result['true_request_to_fill_slippage_observations']=len(events)
            result['last_native_events']=events[-5:]
            result['last_rejected_or_incomplete_events']=rejected[-5:]
        result['native_quote_sample_summary'],result['native_quote_samples_total']=quote_summary(audit)
    except Exception as e:
        result['audit_capability_status']='ACCOUNT_OR_AUDIT_READ_FAILED_'+type(e).__name__
    atomic_json(OUTPUT,result)
    print('BROKER_EXEC_AUDIT',result['audit_capability_status'],
          'NATIVE_SPREAD_QUOTE_SAMPLES',result.get('native_quote_samples_total',0),
          'PROTECTED_NEW_MODEL_EVENTS',result['protected_native_events'],
          'ORDERS_SENT_BY_AUDITOR=0')
if __name__=='__main__':main()
