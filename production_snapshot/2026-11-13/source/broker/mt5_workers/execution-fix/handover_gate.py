#!/usr/bin/env python3
"""APEX DEMO cutover gate. Replaces hard-coded denial, never places orders.

A root-owned operator authorization is necessary but not sufficient. Actual
customer execution is separately checked by activation_ack and the APEX router.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

ROOT = Path('/var/lib/apex-client-feed')
DB = Path('/var/lib/apex-signup/accounts.sqlite3')
POLICY = Path('/etc/apex/trading-policy.json')
APPROVAL = Path('/etc/abutron/apex-demo-execution-approval.json')
SCHEMA = 'abutron.apex.demo.execution.operator.v1'


def load(path: Path) -> dict:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def active(unit: str) -> bool:
    try:
        p = subprocess.run(['systemctl', 'is-active', '--quiet', unit], timeout=4, check=False)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def approval_valid(doc: dict, stat_result=None) -> bool:
    if not isinstance(doc, dict) or set(doc) != {
        'schema', 'approved', 'environment', 'source_single_writer_disabled',
        'operator_confirmation'
    }:
        return False
    return (doc['schema'] == SCHEMA and doc['approved'] is True and
            doc['environment'] == 'DERIV_DEMO' and
            doc['source_single_writer_disabled'] is True and
            doc['operator_confirmation'] == 'SOURCE_EXECUTOR_FENCED_AND_DEMO_ONLY' and
            (stat_result is None or
             (stat_result.st_uid == 0 and stat_result.st_mode & 0o077 == 0)))


def atomic_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.handover-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def inspect(write: bool = True) -> dict:
    reasons = []
    def fail(code: str):
        if code not in reasons:
            reasons.append(code)

    try:
        s = APPROVAL.stat() if not APPROVAL.is_symlink() else None
    except OSError:
        s = None
    if not approval_valid(load(APPROVAL), s) or s is None:
        fail('ROOT_DEMO_OPERATOR_CUTOVER_NOT_APPROVED')

    policy = load(POLICY)
    if (policy.get('environment') != 'DERIV_DEMO' or
            policy.get('live_trading') is not False or
            policy.get('max_concurrent_positions') != 13 or
            policy.get('max_positions_per_symbol') != 1):
        fail('APEX_DERIV_DEMO_RISK_POLICY_INVALID')

    if not active('abutron-client-mt5-manager.service'):
        fail('CUSTOMER_MT5_MANAGER_NOT_ACTIVE')
    if not active('abutron-client-native-feed.timer'):
        fail('CUSTOMER_NATIVE_FEED_NOT_ACTIVE')
    if not active('abutron-client-shadow-fanout.timer'):
        fail('APEX_SIGNAL_FANOUT_NOT_ACTIVE')
    if not active('abutron-apex-native-orders.timer'):
        fail('APEX_NATIVE_DISPATCH_TIMER_NOT_ACTIVE')

    database_ok = False
    try:
        with sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=4) as c:
            database_ok = c.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    except (OSError, sqlite3.Error):
        pass
    if not database_ok:
        fail('CUSTOMER_DATABASE_INTEGRITY_UNVERIFIED')

    # This file never claims a completed broker order or that source shutdown
    # has been independently validated. Those claims need separate proof.
    doc = {
        'schema': 'abutron.apex.production.handover.readiness.v2',
        'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'platform': 'ABUTRONFX.ONLINE',
        'environment': 'DERIV_DEMO',
        'status': ('APPROVED_FOR_TRADING_CUTOVER' if not reasons else
                   'NOT_APPROVED_FOR_TRADING_CUTOVER'),
        'operator_source_fence_attested_not_remotely_verified': not
            ('ROOT_DEMO_OPERATOR_CUTOVER_NOT_APPROVED' in reasons),
        'database_integrity_ok': database_ok,
        'actual_orders_sent_by_this_check': 0,
        'blockers': reasons,
    }
    if write:
        atomic_json(ROOT / 'handover-readiness.json', doc)
    print('APEX_DEMO_CUTOVER', doc['status'], 'BLOCKERS', ','.join(reasons) or 'NONE', flush=True)
    return doc


if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    inspect(write=True)
