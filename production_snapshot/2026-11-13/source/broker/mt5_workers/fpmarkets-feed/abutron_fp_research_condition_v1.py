#!/usr/bin/env python3
"""ABUTRON FP Markets read-only freshness condition for research consumers.
Exit 1 means defer this unit until broker-native authenticated data is fresh.
Never synthesizes quotes, changes a trading switch, or hides a failed trade.
"""
from __future__ import annotations
import argparse,datetime as dt,json,sqlite3,stat,time
from pathlib import Path

DB=Path('/var/lib/apex-signup/accounts.sqlite3')
BASE=Path('/var/lib/abutron-fpmarkets-feed')
PRIMARY='35b81a287b6a030f2f46ff426b135e6c'
AGE_MAX=125
def read(p,maxsize=2500000):
    st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or not 1<=st.st_size<=maxsize:
        raise ValueError('DATA_FILE_UNTRUSTED')
    with p.open('rb') as f: return json.loads(f.read())
def freshness(doc,now):
    t=dt.datetime.fromisoformat(str(doc['checked_at_utc']).replace('Z','+00:00'))
    if t.tzinfo is None or not -20<=now-t.timestamp()<=AGE_MAX:
        raise ValueError('BROKER_PROOF_STALE')
def active():
    with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=5) as c:
        c.execute('PRAGMA query_only=ON')
        return [r[0] for r in c.execute("""
            SELECT id FROM apex_mt5_connections
            WHERE broker='FP Markets' AND environment='DEMO'
            AND broker_server='FPMarketsSC-Demo' AND status='CONNECTED'
            ORDER BY id""")]
def readiness(mode,now=None,root=BASE):
    now=now or time.time()
    if mode not in ('primary-partial','secondary-partial','all-active-partial','all-active-complete','primary-scanner-ready','dual-report-fresh'):
        raise ValueError('MODE_NOT_ALLOWLISTED')
    active_ids=active()
    if mode=='primary-scanner-ready':
        readiness('primary-partial',now,root)
        p=read(Path('/var/lib/abutron-fp-scanner/partial-latest.json'))
        freshness(p,now)
        if p.get('orders_enabled') is not False or p.get('execution_authorized') is not False:raise ValueError('SCANNER_READONLY_PROOF_MISSING')
        return 1
    if mode=='dual-report-fresh':
        readiness('all-active-complete',now,root)
        p=read(Path('/var/lib/abutron-quant-first/dual-broker/latest.json'))
        freshness(p,now)
        if p.get('schema')!='abutron.apex.dualbroker.history_research.readonly.v1' or p.get('orders_enabled') is not False or p.get('execution_authorized') is not False:
            raise ValueError('DUAL_REPORT_NOT_ATTESTED')
        return 2
    if mode=='primary-partial':
        required=[PRIMARY] if PRIMARY in active_ids else []
    elif mode=='secondary-partial':
        required=[x for x in active_ids if x!=PRIMARY]
    else:
        required=active_ids
    if not required:
        raise ValueError('NO_MATCHING_CONNECTED_FP_DEMO_ACCOUNT')
    summary=read(root/'summary.json',350000)
    freshness(summary,now)
    if summary.get('schema')!='abutron.fpmarkets.feed.readonly.v1' or summary.get('execution_enabled') is not False or summary.get('orders_submitted')!=0:
        raise ValueError('FEED_SUMMARY_IDENTITY_UNTRUSTED')
    summaries={row.get('connection_id'):row for row in summary.get('connections',[]) if isinstance(row,dict)}
    for cid in required:
        s=summaries.get(cid)
        if not isinstance(s,dict) or s.get('mode')!='DEMO' or s.get('execution_enabled') is not False or s.get('orders_submitted')!=0:
            raise ValueError('ACCOUNT_ATTESTATION_UNVERIFIED')
        want_complete=mode=='all-active-complete'
        if s.get('status') not in ({'BROKER_NATIVE_DATA_COMPLETE'} if want_complete else {'BROKER_NATIVE_DATA_PARTIAL','BROKER_NATIVE_DATA_COMPLETE'}):
            raise ValueError('BROKER_NATIVE_SESSION_NOT_FRESH')
        fp=root/('market' if want_complete else 'partial')/(cid+'.json')
        data=read(fp)
        freshness(data,now)
        expected_schema=('abutron.fpmarkets.native.candles.v1' if want_complete
                         else 'abutron.fpmarkets.native.partial.readonly.v1')
        if data.get('schema')!=expected_schema or data.get('connection_id')!=cid or data.get('account_mode')!='DEMO' or data.get('execution_enabled') is not False or data.get('orders_submitted')!=0:
            raise ValueError('ACCOUNT_SNAPSHOT_IDENTITY_UNVERIFIED')
        if not data.get('quotes') or not data.get('bars'):
            raise ValueError('NO_VERIFIED_BROKER_CANDLES')
    return len(required)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode',required=True,
        choices=('primary-partial','secondary-partial','all-active-partial','all-active-complete','primary-scanner-ready','dual-report-fresh'))
    args=ap.parse_args()
    try:
        n=readiness(args.mode)
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error) as e:
        print('FP_RESEARCH_DEFERRED_MISSING_AUTHENTICATED_FRESH_MARKET_DATA',
              args.mode,type(e).__name__,str(e)[:85])
        return 1
    print('FP_RESEARCH_READY',args.mode,'verified_accounts',n)
    return 0
if __name__=='__main__':
    raise SystemExit(main())
