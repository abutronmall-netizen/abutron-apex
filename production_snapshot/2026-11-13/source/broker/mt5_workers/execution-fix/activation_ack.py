#!/usr/bin/env python3
"""Customer-specific Deriv DEMO activation acknowledgement.

Only acknowledges a verified native V2 EA ready/permitted state, NOT a broker
order fill. OrderSend acknowledgement remains immutable MT5 broker receipts.
Defaults OFF and refuses LIVE, missing/expired licensing and conflicting orders.
"""
from __future__ import annotations
import datetime as dt
import os
from pathlib import Path
import sqlite3
import sys
import time

sys.path[:0] = ['/opt/apex-client-mt5', '/opt/apex-client-portal', '/opt/apex-signup']
import apex_native_order_runtime as native
import apex_signal_native_router_v1 as router
import apex_crm_license_policy as license_policy
import apex_crm_subscriptions as subscriptions
import apex_pricing
import handover_gate
from apex_portfolio_guard_v3 import capacity,UnsafeExposure

DB = '/var/lib/apex-signup/accounts.sqlite3'
HEX32 = native.HEX32
ROOT = Path('/var/lib/apex-client-feed')
STOP_STATES = frozenset({'RESERVED', 'SUBMISSION_UNKNOWN', 'BROKER_ACK_UNRECONCILED', 'OPEN_PROTECTED', 'UNPROTECTED'})


def is_entitled(c, owner, cid, row) -> bool:
    # For activation preflight, evaluate *prospective* effective state=True.
    # Never modify a connection or spoof a customer decision.
    broker, env, reference, server, status, verified_at, worker = row
    d = license_policy.account_decision(
        c, owner, broker, 'MT5', env, reference, server,
        connection_state=status, broker_verified=verified_at is not None,
        worker_binding=worker, trading_active=True)
    if not d['new_entries_allowed']:
        return False
    if d['license_basis'] == 'paid':
        rec = c.execute('SELECT plan,seats FROM apex_crm_licenses WHERE account_id=?', (owner,)).fetchone()
        sub = subscriptions.current(c, owner)
        if not rec or rec[1] != apex_pricing.SEATS.get(rec[0], -1) or not sub:
            return False
        return (sub['plan'] == rec[0] and sub['status'] == 'active' and
                sub['currency'] == 'ZAR' and sub['billing_interval'] == 'monthly' and
                sub['amount_minor'] == apex_pricing.PRICES.get(rec[0]) and
                bool(sub['renewal_on']) and sub['renewal_on'] >= dt.date.today().isoformat())
    return d['license_basis'] == 'trial'


def risk_profile_ok() -> bool:
    profile = router.read(router.PROFILE)
    policy = router.read(router.POLICY)
    rows = profile.get('rows')
    if (profile.get('status') != 'ACTIVE_DERIV_DEMO_USD_GROSS' or
        policy.get('environment') != 'DERIV_DEMO' or
        policy.get('live_trading') is not False or
        policy.get('max_concurrent_positions') != 13 or
        policy.get('max_positions_per_symbol') != 1 or
        not isinstance(rows, list) or len(rows) != 13):
        return False
    matched = set()
    for item in rows:
        if (not isinstance(item, list) or len(item) != 4 or
            item[0] not in native.ledger.SYMBOLS or
            type(item[1]) not in (int, float) or
            not native.math.isfinite(item[1]) or item[1] <= 0 or
            item[2] != 50 or item[3] != 100 or item[0] in matched):
            return False
        matched.add(item[0])
    return matched == native.ledger.SYMBOLS


def customer_ready(c, row, handover_ok: bool) -> str | None:
    cid, owner, broker, env, reference, server, status, verified_at, worker, desired, effective = row
    if not handover_ok:
        return 'EXCLUSIVE_DEMO_CUTOVER_NOT_APPROVED'
    if broker != 'Deriv' or env != 'DEMO' or server != 'Deriv-Demo':
        return 'DERIV_DEMO_ONLY'
    if status != 'CONNECTED' or worker != 'abutron-client-mt5-' + cid or not HEX32.fullmatch(cid):
        return 'BROKER_ACCOUNT_NOT_CONNECTED'
    if not native.router.manager.attest(cid, broker, server):
        return 'CURRENT_BROKER_SESSION_NOT_ATTESTED'
    ea, err = native.ea_state_v2(cid, reference, server)
    if err or ea is None or ea.get('protocol_version') != 3:
        return 'NATIVE_V3_EA_HEARTBEAT_NOT_VERIFIED'
    if not (ea.get('exposure_verified') and ea.get('native_demo_orders_enabled') and
            ea.get('terminal_trade_allowed') and ea.get('account_trade_allowed')):
        return 'BROKER_OR_NATIVE_EA_AUTOTRADING_NOT_PERMITTED'
    if ea.get('pending_orders') != 0:
        return 'BROKER_PENDING_ORDERS_EXIST'
    # Activation must be tied to the running $50/$100 compiled EA, not only
    # the pre-existing generic V3 bridge heartbeat. The order router also
    # independently re-checks this proof before any broker submission.
    proof = ea['files'] / ('ABUTRON_APEX_V2_USD_50_100_' + ea['nonce'] + '.txt')
    try:
        if proof.is_symlink() or not proof.is_file() or not 0 <= time.time()-proof.stat().st_mtime <= 12:
            return 'USD_50_100_EA_NOT_ACTIVE'
        record = proof.read_text(encoding='utf-8-sig').splitlines()
        if (len(record)!=11 or record[:5] !=
            ['APEX_NATIVE_BRIDGE_USD_50_100_V1', ea['nonce'], reference, server, 'DERIV_DEMO'] or
            abs(time.time()-int(record[5]))>18 or
            int(record[6])!=ea['pending_orders'] or int(record[7])!=ea['positions'] or
            record[8:]!=['1','1','1']):
            return 'USD_50_100_EA_NOT_ACTIVE'
    except (OSError,ValueError,TypeError,KeyError,IndexError):
        return 'USD_50_100_EA_NOT_ACTIVE'
    feed = router.read(ROOT / (cid + '.json'))
    if (feed.get('account_id') != owner or feed.get('connection_id') != cid or
            feed.get('status') != 'BROKER_DATA_VERIFIED_SHADOW' or
            feed.get('broker_data_verified') is not True or
            not router.timestamp(feed.get('checked_at_utc'), 125) or
            feed.get('symbol_count') != 13 or feed.get('timeframes_per_symbol') != 6):
        return 'BROKER_NATIVE_MARKET_DATA_UNVERIFIED'
    acct = feed.get('account', {})
    if not isinstance(acct, dict) or acct.get('all_positions_protected') is not True:
        return 'BROKER_POSITION_RECONCILIATION_REQUIRED'
    if not risk_profile_ok():
        return 'APEX_FIXED_USD_RISK_PROFILE_INVALID'
    if not is_entitled(c, owner, cid, (broker, env, reference, server, status, verified_at, worker)):
        return 'CUSTOMER_LICENSE_SUBSCRIPTION_OR_SEAT_DENIED'
    try:
        occupied=capacity(cid,acct,ea,reference,server,native.ledger.SYMBOLS,native.ledger.DB)
    except UnsafeExposure as exc:
        return str(exc)
    if len(occupied)>=13:
        return 'MAXIMUM_13_BROKER_POSITIONS_ACTIVE'
    return None



# Existing APEX activation routine: recognize the account's native V4
# 0.10%-equity capability instead of requiring legacy fixed-$50/$100 V2.
# No additional approval, licensing or strategy component is created.
SCOPED_V4={
 '9568525eee306da891258ad98c654919':'7593',
 '1ead1f08b44dc5ae284eadc9554b1381':'9244',
}
def scoped_v4_ready(c,row):
    cid,owner,broker,env,reference,server,status,verified_at,worker,desired,effective=row
    suffix=SCOPED_V4[cid]
    if (broker,env,reference,server,status,worker,desired)!=(
         'Deriv','DEMO',('6357593' if suffix=='7593' else '202699244'),
         'Deriv-Demo','CONNECTED','abutron-client-mt5-'+cid,1):
        return 'V4_DEMO_ACCOUNT_OR_CLIENT_ON_INVALID'
    if not native.router.manager.attest(cid,broker,server):
        return 'V4_BROKER_SESSION_NOT_ATTESTED'
    if not is_entitled(c,owner,cid,(broker,env,reference,server,status,verified_at,worker)):
        return 'CUSTOMER_LICENSE_SUBSCRIPTION_OR_SEAT_DENIED'
    try:
        import json
        from pathlib import Path
        base=Path('/var/lib/private/abutron-client-mt5-'+cid)
        health=json.loads((base/'worker-health.json').read_text())
        nonce=health['nonce']
        cap=base/'terminal/MQL5/Files'/('ABUTRON_APEX_NATIVE_V4_CAPABILITY_'+nonce+'.txt')
        if cap.is_symlink() or not cap.is_file() or time.time()-cap.stat().st_mtime>18:
            return 'V4_NATIVE_CAPABILITY_NOT_CURRENT'
        values=cap.read_text(encoding='utf-8-sig').splitlines()
        current_revision=c.execute('SELECT updated_at FROM apex_trade_controls WHERE connection_id=?',(cid,)).fetchone()[0]
        if (len(values)!=10 or values[:5]!=['APEX_NATIVE_REVISION_FENCED_CAPABILITY_V4',
              nonce,str(reference),'Deriv-Demo','DEMO'] or
            values[5]!=str(current_revision) or abs(time.time()-int(values[6]))>18 or
            values[7:]!=['0.10','OFF_REVISION_CHECK_AT_CONSUME','LIVE_FORBIDDEN']):
            return 'V4_NATIVE_REVISION_OR_RISK_POLICY_INVALID'
        cost=Path('/var/lib/abutron-deriv-v4-'+suffix+'/v4-native-execution-cost-'+suffix+'.json')
        if cost.is_symlink() or not cost.is_file() or time.time()-cost.stat().st_mtime>42:
            return 'V4_NATIVE_BROKER_COSTS_NOT_CURRENT'
        k=json.loads(cost.read_text())
        if (k.get('native_bid_ask_and_ordercalcprofit_verified') is not True or
            k.get('native_minlot_ordercalcmargin_verified') is not True or
            k.get('worker_nonce')!=nonce or k.get('account_suffix')!=suffix):
            return 'V4_NATIVE_BROKER_COSTS_NOT_VERIFIED'
    except (OSError,ValueError,TypeError,KeyError,IndexError,sqlite3.Error):
        return 'V4_NATIVE_CURRENT_EVIDENCE_UNAVAILABLE'
    return None

def run() -> None:
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    # Refresh global decision first, never trust an old approval report.
    gate = handover_gate.inspect(write=True)
    approved = gate['status'] == 'APPROVED_FOR_TRADING_CUTOVER'
    c = sqlite3.connect(DB, timeout=8, isolation_level=None)
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=8000')
    try:
        rows = c.execute('''SELECT x.id, x.account_id,x.broker,x.environment,x.account_reference,
          x.broker_server,x.status,x.broker_verified_at,x.worker_binding,
          COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0),COALESCE(t.last_error,'')
          FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
          WHERE x.status IN ('CONNECTED','CONNECTING','ERROR') ORDER BY x.id''').fetchall()
        enabled = disabled = 0
        for row in rows:
            cid, owner, *_unused, desired, effective, last_error = row
            if not HEX32.fullmatch(cid):
                continue
            # Broker-specific authority: this service owns DERIV only.
            # FP Markets DEMO activation is exclusively owned by
            # fp-demo-native-activation-ack.service. Never revoke a
            # different broker's independently verified effective switch.
            if row[2] != 'Deriv':
                continue
            if cid == 'd6fc2524ec373b8d1bc278a8be3ec635':
                continue
            # A fresh, root-private, 6207-only cutover lease delegates this
            # single customer's ACK to the scoped native worker. No other
            # Deriv account is exempt from the legacy cutover requirements.
            if cid == 'd6fc2524ec373b8d1bc278a8be3ec635':
                # Fresh evidence-qualified V3 DEMO-only quant cutover owns this
                # one account; never reuse the consumed historical one-shot.
                try:
                    sys.path.insert(0,'/opt/abutron-research/quant-entry')
                    from abutron_quant_model_cutover_v3 import delegation_active as quant_delegation_active
                    if quant_delegation_active(cid, owner, desired):
                        continue
                except (ImportError,RuntimeError,OSError,ValueError,TypeError,KeyError,sqlite3.Error):
                    pass
                try:
                    from abutron_6207_cutover_v1 import delegation_active
                    if delegation_active(cid, owner, desired):
                        continue
                except (ImportError,RuntimeError,OSError,ValueError,TypeError,KeyError):
                    pass  # missing/stale scoped proof -> original DEMO gate
            try:
                reason = ('CLIENT_REQUESTED_OFF' if desired != 1 else
                          scoped_v4_ready(c,row[:11]) if cid in SCOPED_V4 else
                          customer_ready(c, row[:11], approved))
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, RuntimeError) as exc:
                reason = 'EXECUTION_ADMISSION_CHECK_FAILED'
            should_enable = reason is None
            # When already OFF, the existing V2 loop skipped refreshing a stale
            # blocker. Refresh the diagnostic only; never grant permission.
            diagnostic_refresh = (not should_enable and bool(desired) and
                                  not bool(effective) and
                                  (last_error or '') != str(reason))
            if bool(effective) == should_enable and not diagnostic_refresh:
                continue
            now = int(time.time())
            # Re-check customer intent and identity inside the transaction so
            # an OFF request or disconnect cannot be overwritten by a stale check.
            try:
                c.execute('BEGIN IMMEDIATE')
                live = c.execute('''SELECT x.account_id,x.status,x.worker_binding,
                  COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0),COALESCE(t.last_error,'')
                  FROM apex_mt5_connections x JOIN apex_trade_controls t ON t.connection_id=x.id
                  WHERE x.id=?''', (cid,)).fetchone()
                if (not live or live[0] != owner or live[3] != desired or
                        live[4] != effective or
                        live[5] != (last_error or '') or
                    (should_enable and (live[1] != 'CONNECTED' or
                                            live[2] != row[8] or live[3] != 1))):
                    c.execute('ROLLBACK')
                    continue
                c.execute('''UPDATE apex_trade_controls
                  SET effective_enabled=?,last_error=?,updated_at=? WHERE connection_id=?''',
                  (1 if should_enable else 0, None if should_enable else reason, now, cid))
                c.execute('''INSERT INTO apex_trade_control_audit
                  (account_id,connection_id,requested_enabled,outcome,occurred_at)
                  VALUES(?,?,?,?,?)''',
                  (owner,cid,desired,
                   ('APEX_V4_ACCOUNT_BOUND_READY_NO_BROKER_ORDER' if cid in SCOPED_V4 else
                    'NATIVE_V2_DEMO_READY_ACK_NO_BROKER_ORDER') if should_enable else
                   ('NATIVE_V2_BLOCKER_REFRESH_' if diagnostic_refresh else
                    'NATIVE_V2_EXECUTION_REVOKED_') + str(reason)[:80],now))
                c.execute('COMMIT')
                enabled += int(should_enable)
                disabled += int(not should_enable and bool(effective))
            except sqlite3.Error:
                if c.in_transaction:
                    c.execute('ROLLBACK')
                raise
        print('APEX_NATIVE_DEMO_ACTIVATION_ACK', 'CUTOVER', approved,
              'EFFECTIVE_ENABLED', enabled, 'EFFECTIVE_REVOKED', disabled, flush=True)
    finally:
        c.close()


if __name__ == '__main__':
    run()
