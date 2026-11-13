"""Pure APEX11 broker-native DEMO request protocol formatter (NO SUBMISSION).

Source-contracts, not source code of an MT5 Expert Advisor:
- Deriv: apex_native_order_runtime.send_once, APEX_NATIVE_ADAPTIVE_ORDER_V3
- FP Markets: fp_signal_order_router_v1.transactionally_create_request,
  APEX_FP_NATIVE_ADAPTIVE_ORDER_V2

A formatted request is NOT permission to publish it. The production broker
writers must own the account-specific lock, durable UNKNOWN ledger, broker
position reconciliation, CRM/client switch checks, native EA ability and
receipt matching at the exact instant the file becomes visible. Those pieces
are not controlled by this module and are not bypassed here.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from .production_contracts import DERIV_ALLOWED
from .candidate_contract import FP_SUPPORTED

HEX32 = re.compile(r'[0-9a-f]{32}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
LOGIN = re.compile(r'[0-9]{4,20}\Z')

class NativeRequestRefused(ValueError):
    pass


@dataclass(frozen=True)
class NativeTarget:
    broker: str
    environment: str
    connection_id: str
    owner: str
    login: str
    broker_server: str
    worker_nonce: str
    canonical_symbol: str
    native_symbol: str


def _checked_text(x, label):
    if not isinstance(x, str) or not x or '\r' in x or '\n' in x or '\x00' in x or len(x)>120:
        raise NativeRequestRefused('INVALID_'+label)
    return x


def render_native_demo_intent(*, target: NativeTarget, signal: Mapping,
                              review: Mapping, now: int,
                              fp_legacy_m5_bar_time: int | None = None):
    """Return an inspectable, never-published 12-line V3/V2 payload.

    All this can prove is canonical schema equality. It cannot verify that the
    *live* MT5 EA is loaded, customer switches are on or current exposure is
    reconciled; it cannot place orders, move files or create ledger entries.
    """
    if target.broker not in {'deriv','fp_markets'} or target.environment != 'DEMO':
        raise NativeRequestRefused('DEMO_ONLY')
    expected_server = 'Deriv-Demo' if target.broker=='deriv' else 'FPMarketsSC-Demo'
    if target.broker_server != expected_server:
        raise NativeRequestRefused('DEMO_SERVER_IDENTITY_MISMATCH')
    if not all(isinstance(v,str) and HEX32.fullmatch(v) for v in (
            target.owner,target.connection_id,target.worker_nonce)):
        raise NativeRequestRefused('OWNER_CONNECTION_OR_WORKER_NONCE_INVALID')
    if not isinstance(target.login,str) or not LOGIN.fullmatch(target.login):
        raise NativeRequestRefused('NATIVE_LOGIN_INVALID')
    canonical = _checked_text(target.canonical_symbol,'CANONICAL_SYMBOL')
    actual = _checked_text(target.native_symbol,'BROKER_SYMBOL')
    if (target.broker=='deriv' and canonical not in DERIV_ALLOWED) or (
            target.broker=='fp_markets' and canonical not in FP_SUPPORTED):
        raise NativeRequestRefused('UNAPPROVED_BROKER_SYMBOL')
    if target.broker=='deriv' and actual!=canonical:
        raise NativeRequestRefused('DERIV_NATIVE_SYMBOL_MISMATCH')
    if not isinstance(signal,Mapping) or not isinstance(review,Mapping):
        raise NativeRequestRefused('REVIEW_OR_SIGNAL_INVALID')
    if (signal.get('engine')!='APEX_1_1_0' or
        signal.get('broker')!=target.broker or
        signal.get('symbol')!=canonical or
        signal.get('timeframe')!='M5' or
        signal.get('order') is not None or
        signal.get('status') not in ('BUY','SELL')):
        raise NativeRequestRefused('APEX11_DIRECTIONAL_SIGNAL_REQUIRED')
    if (review.get('schema')!='abutron.apex11.broker.candidate.review.v1' or
        review.get('broker')!=target.broker or
        review.get('environment')!='DEMO' or
        review.get('engineering_gates_passed') is not True or
        review.get('blockers')!=[] or
        review.get('orders_submitted')!=0):
        raise NativeRequestRefused('BROKER_RISK_REVIEW_NOT_PASSED')
    oc = review.get('order_candidate')
    if (not isinstance(oc,Mapping) or oc.get('connection_id')!=target.connection_id or
        oc.get('symbol')!=canonical or oc.get('side')!=signal['status'] or
        review.get('source_decision_id')!=signal.get('decision_id')):
        raise NativeRequestRefused('REVIEW_ACCOUNT_OR_DECISION_MISMATCH')
    if type(now)!=int or now<1_700_000_000:
        raise NativeRequestRefused('INVALID_PUBLICATION_CLOCK')
    closing=signal.get('bar_closed_ts')
    if type(closing) not in (int,float) or not math.isfinite(closing) or closing!=int(closing) or int(closing)%300:
        raise NativeRequestRefused('CLOSED_M5_IDENTITY_INVALID')
    if closing>now:
        raise NativeRequestRefused('FUTURE_M5_BAR')
    if target.broker=='deriv':
        # Exact identity consumed by existing Deriv customer_order_ledger.
        expected=hashlib.sha256(
            f'{target.owner}|{target.connection_id}|{canonical}|M5|{int(closing)-300}|{signal["status"]}'.encode()
        ).hexdigest()
        if review.get('signal_id_for_separate_ledger') != expected or oc.get('signal_id') != expected:
            raise NativeRequestRefused('DERIV_LEDGER_IDENTITY_MISMATCH')
        protocol='APEX_NATIVE_ADAPTIVE_ORDER_V3'
        native_key=expected
    else:
        # FP native ledger identity intentionally differs from APEX candidate
        # identity. Keep BOTH in the journal, never pretend they are the same.
        if (not isinstance(review.get('signal_id_for_separate_ledger'),str) or
            not HEX64.fullmatch(review['signal_id_for_separate_ledger']) or
            oc.get('signal_id')!=review['signal_id_for_separate_ledger']):
            raise NativeRequestRefused('FP_APEX_LEDGER_IDENTITY_INVALID')
        # The exported FP router hashes `c["closed_bar"]` from its legacy
        # scanner. That scanner was NOT among the 12 exported source files.
        # We cannot prove whether the field is the M5 opening or closing UNIX
        # time. Require that exact adapter mapping to be established rather
        # than fabricate an allegedly matching FP native receipt identity.
        if type(fp_legacy_m5_bar_time) is not int or fp_legacy_m5_bar_time not in (
                int(closing)-300, int(closing)):
            raise NativeRequestRefused('FP_NATIVE_LEDGER_BAR_TIME_CONVENTION_UNVERIFIED')
        native_key=hashlib.sha256(
            f'{target.connection_id}|{canonical}|{fp_legacy_m5_bar_time}'.encode()
        ).hexdigest()
        protocol='APEX_FP_NATIVE_ADAPTIVE_ORDER_V2'
    rows=[protocol,target.worker_nonce,native_key,target.login,target.broker_server,
          actual,signal['status'],'AUTO','0.10','STRUCTURE_M5',str(now+12),'SEND_DEMO_ONLY']
    if len(rows)!=12 or any('\n' in x or '\r' in x for x in rows):
        raise NativeRequestRefused('NATIVE_PACKET_FORMAT_INVALID')
    return {
        'schema':'abutron.apex11.mt5.native.intent.preview.v1',
        'broker':target.broker,'environment':'DEMO',
        'connection_id':target.connection_id,
        'apex_decision_id':signal['decision_id'],
        'apex_candidate_id':review['signal_id_for_separate_ledger'],
        'native_receipt_key':native_key,
        'fp_legacy_m5_bar_time':fp_legacy_m5_bar_time if target.broker=='fp_markets' else None,
        'command_file':'APEX_NATIVE_ORDER_V1.req' if target.broker=='deriv' else 'APEX_FP_NATIVE_ORDER_V1.req',
        'packet_bytes': ('\r\n'.join(rows)+'\r\n').encode('utf-8'),
        'orders_submitted':0,
        'native_order_request_published':False,
        'must_use_original_writer_and_durable_ledger':True,
        'native_broker_ack_received':False,
    }
