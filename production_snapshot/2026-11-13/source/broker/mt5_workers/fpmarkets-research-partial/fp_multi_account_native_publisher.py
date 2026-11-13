#!/usr/bin/python3
"""FP DEMO account-isolated native research publisher; no order or MT5 writes."""
from __future__ import annotations
import hashlib, importlib.util, json, re, sqlite3, time
from pathlib import Path

DB=Path('/var/lib/apex-signup/accounts.sqlite3')
ROOT=Path('/opt/apex-client-mt5/fpmarkets-research-partial')
NATIVE=Path('/var/lib/abutron-fpmarkets-feed/partial')
CUSTOMER=Path('/var/lib/apex-signup/fp-market-ui')
OPERATOR=Path('/var/lib/apex/operator-live')
PRIMARY='35b81a287b6a030f2f46ff426b135e6c'
CID=re.compile(r'^[0-9a-f]{32}$')

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path))
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def connected(db=DB):
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=7) as con:
        con.execute('PRAGMA query_only=ON')
        rows=con.execute("""SELECT a.id,a.account_id,a.account_reference
         FROM apex_mt5_connections a WHERE a.broker='FP Markets'
           AND a.environment='DEMO' AND a.broker_server='FPMarketsSC-Demo'
           AND a.status='CONNECTED' ORDER BY a.id""").fetchall()
    if not (1<=len(rows)<=6):raise ValueError('FP_ACCOUNT_COUNT_UNSAFE')
    if any(not isinstance(cid,str) or not CID.fullmatch(cid)
           or not isinstance(owner,str) or not CID.fullmatch(owner)
           or not isinstance(login,str) or not login.isdigit()
           for cid,owner,login in rows):
        raise ValueError('FP_ACCOUNT_IDENTITY_INVALID')
    if len({x[0] for x in rows})!=len(rows):raise ValueError('FP_DUPLICATE_ACCOUNT')
    return rows

def build_one(cid,owner,login):
    if cid==PRIMARY:raise ValueError('PRIMARY_OWNED_BY_EXISTING_PIPELINE')
    scanner=load('fp_isolated_scanner_'+cid,ROOT/'fp_partial_scanner.py')
    scanner.CID=cid
    scanner.SOURCE=NATIVE/(cid+'.json')
    row=scanner.build() # broker-native account attestation + heartbeat + closed bars
    if row.get('account_fingerprint')!=hashlib.sha256(cid.encode()).hexdigest()[:24]:
        raise ValueError('FP_SCANNER_BINDING_MISMATCH')
    ui=load('fp_isolated_ui_'+cid,ROOT/'fp_partial_ui.py')
    ui.CID=cid
    ui.NATIVE=NATIVE/(cid+'.json')
    # Global FP AI/history files may belong to a different account: reject reuse.
    ui.AI=Path('/var/lib/abutron-fp-scanner/ai/per-account')/(cid+'.json')
    ui.HISTORY=Path('/var/lib/apex/operator-live/fp-native-history-per-account')/(cid+'.json')
    got_id,got_owner,doc=ui.create(row)
    if got_id!=cid or got_owner!=owner or doc.get('account_masked')!='••••'+login[-4:]:
        raise ValueError('FP_OWNER_OR_LOGIN_BINDING_MISMATCH')
    if (doc.get('source_quality')!=("BROKER_NATIVE_13X6_VERIFIED" if doc.get('fresh_quotes')==13 else "PARTIAL_NOT_CERTIFIED")
        or doc.get('coverage_complete') is not (doc.get('fresh_quotes')==13)
        or doc.get('execution_enabled') is not False
        or doc.get('orders_submitted_by_collector')!=0
        or doc.get('verified_trade_history_available') is not False
        or not 1<=doc.get('fresh_quotes',0)<=13
        or doc.get('timeframe_series')!=6*doc['fresh_quotes']
        or len(doc.get('unavailable_symbols',[]))!=13-doc['fresh_quotes']):
        raise ValueError('FP_PARTIAL_PUBLICATION_SAFETY_DENIED')
    return ui,row,doc

def run(publish=True):
    rows=connected()
    reports=[]
    for cid,owner,login in rows:
        if cid==PRIMARY:continue
        ui,scanner,doc=build_one(cid,owner,login)
        if publish:
            # Existing helper atomically writes owner-scoped client + protected operator.
            result=ui.publish(scanner,operator=OPERATOR/('fp-market-account-'+cid+'.json'),
                              customer=CUSTOMER)
            if result.get('orders_enabled') is not False:
                raise ValueError('FP_PUBLISHER_ORDER_AUTHORITY_INVALID')
        reports.append({'account_masked':doc['account_masked'],
           'verified_symbols':doc['fresh_quotes'],
           'unavailable_symbols':doc['unavailable_symbols'],
           'orders_enabled':False,'published':bool(publish)})
    if not reports:return {'status':'NO_SECOND_CONNECTED_FP_ACCOUNT',
             'secondary_accounts':[],'execution_authorized':False,'orders_enabled':False}
    return {'schema':'abutron.fpmarkets.multi_owner.readonly.v1',
      'status':'PARTIAL_ACCOUNT_SCOPED_RESEARCH','secondary_accounts':reports,
      'execution_authorized':False,'orders_enabled':False}
if __name__=='__main__':
    print(json.dumps(run(),sort_keys=True))
