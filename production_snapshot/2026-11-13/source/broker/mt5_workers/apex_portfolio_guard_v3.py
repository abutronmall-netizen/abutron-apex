#!/usr/bin/python3
"""APEX V3 Deriv DEMO per-symbol capacity check (read-only).
Independent from MT5 order sending. Fail closed on all unknown exposure.
"""
from __future__ import annotations
import math
import sqlite3
import time
from pathlib import Path

UNRESOLVED = ('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED','UNPROTECTED')
ALL_ACTIVE = UNRESOLVED+('OPEN_PROTECTED',)

class UnsafeExposure(ValueError):
    pass

def capacity(cid, account, ea, login, server, expected, ledger_path, *, max_positions=13):
    if not ea or ea.get('protocol_version') != 3 or not ea.get('exposure_verified'):
        raise UnsafeExposure('V3_NATIVE_BRIDGE_REQUIRED')
    if ea.get('pending_orders') != 0:
        raise UnsafeExposure('BROKER_PENDING_ORDERS_EXIST')
    if not isinstance(account,dict) or account.get('all_positions_protected') is not True:
        raise UnsafeExposure('BROKER_EXPOSURE_PROTECTION_INVALID')
    positions=account.get('positions')
    if not isinstance(positions,list) or type(account.get('open_positions')) is not int:
        raise UnsafeExposure('BROKER_EXPOSURE_SCHEMA_INVALID')
    if account['open_positions']!=len(positions) or ea.get('positions')!=len(positions):
        raise UnsafeExposure('BROKER_NATIVE_AND_FEED_POSITION_COUNT_MISMATCH')
    if len(positions)>max_positions:
        raise UnsafeExposure('BROKER_ACCOUNT_ABOVE_POSITION_LIMIT')
    expected=set(expected)
    if len(expected)!=13 or max_positions!=13:
        raise UnsafeExposure('INVALID_SYMBOL_UNIVERSE_OR_LIMIT')
    if not Path(ledger_path).is_file():
        raise UnsafeExposure('DURABLE_LEDGER_MISSING')
    try:
        with sqlite3.connect('file:'+str(ledger_path)+'?mode=ro',uri=True,timeout=3) as c:
            existing=c.execute("""SELECT symbol,side,broker_position,signal_key,volume,
                                          stop_loss,take_profit,state
                                    FROM attempts WHERE connection_id=?
                                    AND state IN ('RESERVED','SUBMISSION_UNKNOWN',
                                     'BROKER_ACK_UNRECONCILED','OPEN_PROTECTED','UNPROTECTED')""",
                               (cid,)).fetchall()
    except sqlite3.Error as ex:
        raise UnsafeExposure('EXECUTION_LEDGER_UNREADABLE') from ex
    if any(x[-1]!='OPEN_PROTECTED' for x in existing):
        raise UnsafeExposure('BROKER_OUTCOME_UNRESOLVED')
    if len(existing)!=len(positions):
        raise UnsafeExposure('LEDGER_BROKER_POSITION_COUNT_MISMATCH')
    ledger={}
    for sym,side,ticket,key,volume,sl,tp,state in existing:
        if not (sym in expected and side in ('BUY','SELL') and
                type(ticket) is int and ticket>0 and
                isinstance(key,str) and len(key)==64 and
                isinstance(volume,(int,float)) and volume>0):
            raise UnsafeExposure('LEDGER_OPEN_POSITION_INVALID')
        if sym in ledger:
            raise UnsafeExposure('DUPLICATE_LEDGER_SYMBOL')
        ledger[sym]=(side,ticket,key,volume,sl,tp)
    occupied=set()
    for p in positions:
        if not isinstance(p,dict) or p.get('protected') is not True:
            raise UnsafeExposure('UNPROTECTED_BROKER_POSITION')
        sym=p.get('symbol')
        if sym not in expected or sym in occupied or sym not in ledger:
            raise UnsafeExposure('FOREIGN_OR_DUPLICATE_BROKER_POSITION')
        side,ticket,key,vol,sl,tp=ledger[sym]
        try:
            if (p.get('side')!=side or int(p.get('ticket'))!=ticket or
                abs(float(p.get('volume'))-float(vol))>1e-6 or
                abs(float(p.get('sl'))-float(sl))>1e-6 or
                abs(float(p.get('tp'))-float(tp))>1e-6):
                raise UnsafeExposure('BROKER_LEDGER_PRICE_OR_POSITION_MISMATCH')
            path=ea['files']/'ABUTRON'/'evidence'/(key+'.txt')
            if path.is_symlink():
                raise UnsafeExposure('BROKER_NATIVE_POSITION_PROOF_MISSING')
            if not path.is_file():
                # Restore continuity for root-allowlisted positions that were
                # broker-verified BEFORE this MT5 session recreated its folder.
                # A fresh MT5-native position snapshot is mandatory; this never
                # fabricates a broker ACK or an EA-native evidence file.
                from apex_native_reconnect_continuity_v1 import verify_prior_native_position
                recovered = verify_prior_native_position(
                    cid, account, ea, login, server, key, sym, side, ticket,
                    vol, sl, tp, ledger_path)
                if not recovered:
                    raise UnsafeExposure('BROKER_NATIVE_POSITION_PROOF_MISSING')
                occupied.add(sym)
                continue
            if path.stat().st_size>5000:
                raise UnsafeExposure('BROKER_NATIVE_POSITION_PROOF_MISSING')
            r=path.read_text(encoding='utf-8-sig').splitlines()
            if (len(r)!=19 or r[:5]!=['APEX_BROKER_POSITION_V2',key,ea['nonce'],login,server]
                or r[5]!=sym or r[6]!=side or int(r[9])!=ticket
                or r[16]!='OPEN_PROTECTED' or not -5<=time.time()-int(r[17])<=130):
                raise UnsafeExposure('BROKER_NATIVE_POSITION_PROOF_STALE_OR_INVALID')
            values=[float(v) for v in r[10:16]]
            basic=(all(math.isfinite(v) for v in values) and
                abs(values[0]-float(vol))<=1e-6 and
                abs(values[2]-float(sl))<=1e-6 and
                abs(values[3]-float(tp))<=1e-6)
            if not basic:
                raise UnsafeExposure('BROKER_NATIVE_PRICE_OR_VOLUME_MISMATCH')
            fixed=((abs(values[4]-50.0)<=2.0 and abs(values[5]-100.0)<=2.0)
                   or (abs(values[4]-10.0)<=2.0 and abs(values[5]-20.0)<=2.0))
            if not fixed:
                from optionc_native_v2_intent_contract import parse_native_intent,native_position_risk
                intent=parse_native_intent(
                    ea['files']/'ABUTRON'/'optionc_v2'/(key+'.txt'),
                    key,ea['nonce'],login,server,sym,side)
                native_position_risk(intent,
                    broker_position_volume=values[0],
                    broker_entry=values[1],broker_stop=values[2],
                    broker_target=values[3],broker_cash_loss=values[4],
                    broker_cash_reward=values[5])

        except (ValueError,TypeError,KeyError,OSError,IndexError) as ex:
            if isinstance(ex,UnsafeExposure):raise
            raise UnsafeExposure('BROKER_POSITION_PROOF_PARSE_FAILED') from ex
        occupied.add(sym)
    return occupied
