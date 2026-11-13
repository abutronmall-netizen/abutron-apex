#!/usr/bin/env python3
"""Reconcile the 6207 V4 pre-CLAIM native rejects against broker HistorySelect(0).
Only completes existing UNKNOWN risk reservations as REJECTED after:
 - native EA-written blocking receipt at the pre-OrderSend root-CLAIM branch;
 - unchanged authentic Deriv DEMO worker and EA binary;
 - CRM direct intent remains APPROVED (never CLAIMED or SEND_UNKNOWN);
 - root CRM has no send lease; broker-native history after the attempt has
   no subsequent deals and native account positions/pending are both zero.
This script never queues orders, toggles CRM, deletes rows, or creates backups.
"""
from __future__ import annotations
import argparse,hashlib,json,os,sqlite3,stat,sys,time
from datetime import datetime,timezone
from pathlib import Path

CID='d6fc2524ec373b8d1bc278a8be3ec635'
OWNER='4fd8991981000ffa4fa0b1c233c5195c'
BASE=Path('/var/lib/abutron-apex11-6207')
CRM=Path('/var/lib/apex-signup/accounts.sqlite3')
WORK=Path('/var/lib/private/abutron-client-mt5-'+CID)
FACT=Path('/var/lib/abutron-v4-broker-crm-supervisor-6207')
EA=WORK/'terminal/MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_6207.ex5'
EA_SHA='83f9ea4c23f81064a1fcdfe9c902f1a9824799d99d799e52d02e5ea3a1dec275'
RES=BASE/'v4-customer-risk-reservations.sqlite3'

def get(p,age,uid=None):
    if p.is_symlink():raise ValueError('UNTRUSTED_SYMLINK')
    s=p.stat()
    if (s.st_mode&0o022 or s.st_nlink!=1 or
        (uid is not None and s.st_uid!=uid) or
        not -2<=time.time()-s.st_mtime<=age):
        raise ValueError('UNTRUSTED_OR_STALE_'+p.name)
    return p.read_bytes()

def evidence():
    if hashlib.sha256(EA.read_bytes()).hexdigest()!=EA_SHA:
        raise ValueError('EA_BINARY_UNMATCHED')
    health=json.loads(get(WORK/'worker-health.json',20,WORK.stat().st_uid))
    nonce=health['nonce']
    if (health.get('id')!=CID or health.get('broker')!='Deriv' or
        health.get('mode')!='DEMO' or health.get('server')!='Deriv-Demo' or
        health.get('status')!='CONNECTED' or health.get('heartbeat_fresh') is not True):
        raise ValueError('NATIVE_BROKER_SESSION_UNVERIFIED')
    history_bytes=get(FACT/'deriv-6207-native-fullrange-history.json',420,0)
    hist=json.loads(history_bytes)
    if (hist.get('account_suffix')!='6207' or
        hist.get('full_range_cashflow_to_broker_balance_reconciled') is not True or
        hist.get('native_full_range_deals')!=153 or
        hist.get('native_trade_deals')!=152 or
        hist.get('new_order_broker_ack_certified') is not False):
        raise ValueError('FULL_BROKER_HISTORY_DIVERGENCE')
    history_time=datetime.fromisoformat(hist['verified_utc']).timestamp()
    last_deal=datetime.fromisoformat(hist['last_native_deal_utc']).timestamp()
    risk=json.loads(get(FACT/'customer-wide-risk-evidence.json',110,0))
    if (risk.get('native_current_open_exposure_reconciled') is not True or
        risk.get('native_flat_accounts_verified')!=6 or
        risk.get('unknown_connected_position_sets')!=0):
        raise ValueError('CURRENT_BROKER_EXPOSURE_UNVERIFIED')
    c=sqlite3.connect('file:'+str(CRM)+'?mode=ro',uri=True)
    c.execute('pragma query_only=on')
    intents=c.execute('''SELECT signal_id,worker_nonce,revision,request_digest,
                        expires_utc,state,created_utc FROM abutron_v4_6207_direct_intents
                        WHERE account_id=? ORDER BY created_utc''',(CID,)).fetchall()
    pending=c.execute("SELECT signal_id,status FROM abutron_v4_6207_send_lease").fetchall()
    c.close()
    if pending:raise ValueError('SEND_LEASE_PRESENT_BROKER_OUTCOME_UNKNOWN')
    result=[]
    for signal,worker_nonce,rev,req_digest,expiry,state,created in intents:
        if worker_nonce!=nonce:
            continue  # Retired MT5 profile; never reconcile its receipts as current.
        if state!='APPROVED' or rev<1 or expiry>=time.time():
            raise ValueError('DIRECT_INTENT_NOT_EXPIRED_PRECLAIM')
        if history_time<=expiry+20 or last_deal>=created:
            raise ValueError('BROKER_HISTORY_NOT_AFTER_REQUEST')
        receipt=WORK/'terminal/MQL5/Files/ABUTRON/receipts'/ (signal+'.txt')
        raw=get(receipt,2400,WORK.stat().st_uid)
        lines=raw.decode('utf-8-sig').splitlines()
        if (len(lines)!=10 or
            lines[:4]!=['APEX_NATIVE_V2',signal,'BLOCKED','V4_ROOT_ACTIVATION_SUPERVISOR_NOT_ATTESTED'] or
            lines[4:6]!=['0','0'] or lines[7:]!=[nonce,'32456207','Deriv-Demo'] or
            abs(int(lines[6])-created)>20):
            raise ValueError('NATIVE_PRE_SEND_REJECTION_UNVERIFIED')
        archive=WORK/'terminal/MQL5/Files/ABUTRON/execution-audit'/('apex11-v4-'+signal+'.consumed')
        archived=get(archive,2400,WORK.stat().st_uid).decode('utf-8-sig').splitlines()
        if (len(archived)!=13 or archived[2]!=signal or archived[1]!=nonce or
            archived[3:5]!=['32456207','Deriv-Demo'] or
            archived[-1]!='SEND_DEMO_ONLY' or archived[-2]!=str(expiry)):
            raise ValueError('EXACT_CONSUMED_REQUEST_NOT_MATCHING')
        key=hashlib.sha256(json.dumps([CID,signal],separators=(',',':')).encode()).hexdigest()
        with sqlite3.connect('file:'+str(RES)+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT state,volume FROM intents WHERE signal_key=?',(key,)).fetchone()
        if row is None or row[0] not in ('UNKNOWN','REJECTED'):
            raise ValueError('RISK_HELD_IDENTITY_MISMATCH')
        if row[1]!=archived[7]:
            raise ValueError('BROKER_LOT_OR_RESERVATION_MISMATCH')
        record=dict(signal_id=signal,crm_revision=rev,volume=row[1],
                    native_receipt_state='BLOCKED_BEFORE_ORDER_SEND',
                    native_receipt_reason=lines[3],
                    native_receipt_sha256=hashlib.sha256(raw).hexdigest(),
                    authenticated_broker_history_sha256=hashlib.sha256(history_bytes).hexdigest(),
                    broker_history_verified_utc=hist['verified_utc'],
                    last_native_deal_utc=hist['last_native_deal_utc'],
                    no_native_send_lease=True,crm_intent_never_claimed=True,
                    broker_positions_pending_verified_zero=True,
                    risk_state_before=row[0])
        proof=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        record['proof_ref']=proof
        result.append(record)
    if not result:raise ValueError('NO_DIRECT_INTENTS_TO_RECONCILE')
    return result

def run():
    ap=argparse.ArgumentParser()
    ap.add_argument('--reconcile',action='store_true')
    args=ap.parse_args()
    rows=evidence()
    if args.reconcile:
        sys.path.insert(0,'/opt/abutron-apex11-staging/native-v4-guarded-20261108')
        from risk_guard.reservation_store import ReservationStore
        st=ReservationStore(RES)
        for r in rows:
            if r['risk_state_before']=='UNKNOWN':
                st.complete(CID,r['signal_id'],outcome='REJECTED',
                    broker_proof=r['proof_ref'],now=datetime.now(timezone.utc))
    report={'schema':'abutron.apex11.6207.native_preclaim_rejection_reconciled.v1',
            'checked_utc':datetime.now(timezone.utc).isoformat(),
            'mode':'RISK_LEDGER_RECONCILED' if args.reconcile else 'READ_ONLY_PROOF',
            'records':rows,'broker_orders_sent_by_reconciler':0,
            'live_accounts_modified':False,'backups_created':0}
    if args.reconcile:
        path=BASE/'v4-preclaim-native-rejection-reconciliation.json'
        tmp=path.with_suffix('.tmp-'+str(os.getpid()))
        tmp.write_text(json.dumps(report,sort_keys=True,separators=(',',':'))+'\n')
        os.chmod(tmp,0o600);os.replace(tmp,path)
    print(json.dumps({'state':report['mode'],
                      'signals':[r['signal_id'] for r in rows],
                      'previous_risk_states':[r['risk_state_before'] for r in rows],
                      'native_orders_sent':0}))
if __name__=='__main__':run()
