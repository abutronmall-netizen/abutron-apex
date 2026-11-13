#!/usr/bin/python3
"""Account-scoped FP Markets DEMO 1636 broker-native history publisher.
No order APIs, no MT5 writes, no modification of the first account's file.
"""
from __future__ import annotations
import grp
import importlib.util
import json
import pwd
import sqlite3
from pathlib import Path

BASE=Path('/opt/apex-client-mt5/fpmarkets-history/fp_native_history_collect.py')
CID='80cf848587fcec6311dd93560c1c46c6'
CLIENT=Path('/var/lib/apex-signup/fp-native-history')
OPERATOR=Path('/var/lib/apex/operator-live')/('fp-native-history-account-'+CID+'.json')

def load():
    spec=importlib.util.spec_from_file_location('fp_native_history_original_account_bound',BASE)
    if spec is None or spec.loader is None:raise ValueError('FP_HISTORY_ORIGINAL_NOT_FOUND')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CID=CID
    return module

def build():
    module=load()
    cid,owner,doc=module.snapshot()
    if cid!=CID or not isinstance(owner,str) or len(owner)!=32:
        raise ValueError('FP_NATIVE_HISTORY_OWNER_PROOF_FAILED')
    with sqlite3.connect('file:/var/lib/apex-signup/accounts.sqlite3?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        record=db.execute("""SELECT account_id,account_reference,broker_server,status
          FROM apex_mt5_connections WHERE id=? AND broker='FP Markets'
          AND environment='DEMO'""",(CID,)).fetchone()
    if not record or record!=(owner,record[1],'FPMarketsSC-Demo','CONNECTED'):
        raise ValueError('FP_NATIVE_HISTORY_DB_ACCOUNT_MISMATCH')
    if not isinstance(record[1],str) or not record[1].isdigit():
        raise ValueError('FP_NATIVE_HISTORY_LOGIN_INVALID')
    if doc.get('account_masked')!='••••'+record[1][-4:]:
        raise ValueError('FP_NATIVE_HISTORY_LOGIN_PROOF_MISMATCH')
    if (doc.get('history_verified_from_mt5') is not True or
        doc.get('execution_enabled') is not False or
        doc.get('orders_submitted_by_exporter')!=0 or
        doc.get('environment')!='DEMO' or
        doc.get('history_complete_within_selected_window') is not True):
        raise ValueError('FP_NATIVE_HISTORY_CONTENT_NOT_VERIFIED')
    return module,doc

def run(publish=True):
    module,doc=build()
    if publish:
        uid=pwd.getpwnam('apexsignup').pw_uid
        gid=pwd.getpwnam('apexsignup').pw_gid
        if not CLIENT.is_dir() or CLIENT.is_symlink():
            raise ValueError('FP_NATIVE_HISTORY_TARGET_DIR_UNTRUSTED')
        module.atomic(CLIENT/(CID+'.json'),doc,uid,gid)
        module.atomic(OPERATOR,doc,0,grp.getgrnam('apexagent').gr_gid)
    return {'status':'FP_NATIVE_HISTORY_ACCOUNT_SCOPED_VERIFIED',
        'account_masked':doc['account_masked'],
        'open_positions':doc['open_positions_count'],
        'pending_orders':doc['pending_orders_count'],
        'trade_deals_90d':doc['trade_deals_count'],
        'history_verified_from_mt5':True,
        'orders_submitted':0,'published':bool(publish)}

if __name__=='__main__':
    print(json.dumps(run(),sort_keys=True))
