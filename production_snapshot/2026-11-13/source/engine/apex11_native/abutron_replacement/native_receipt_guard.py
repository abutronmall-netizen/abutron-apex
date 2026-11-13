"""MT5 receipt/protected-position reconciliation contract; NO broker calls.

The actual privileged native MT5 worker MUST independently authenticate and
extract the receipt, deal, position and account snapshot from the broker API.
A caller-provided boolean alone is not cryptographic authentication; this
module is an extra consistency gate, not a replacement for the native worker.

No order is placed here. A pending receipt, partial fill or unknown order keeps
its original ReservationStore risk reserved until authenticated reconciliation.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any

from .production_contracts import FeedRefused, HEX32
from risk_guard.abutron_risk_guard import D
from risk_guard.reservation_store import ReservationStore


@dataclass(frozen=True)
class NativeOrderReceipt:
    broker: str
    environment: str
    server: str
    account_id: str
    signal_id: str
    symbol: str
    side: str
    broker_return_code: int
    order_id: str
    deal_id: str
    position_id: str
    volume_lots: Decimal
    broker_time: datetime


@dataclass(frozen=True)
class NativePositionProof:
    account_id: str
    server: str
    position_id: str
    symbol: str
    side: str
    volume_lots: Decimal
    open_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    broker_snapshot_time: datetime
    in_reconciled_open_exposure: bool
    pending_remainder_or_unknown_order: bool


def verify_demo_broker_position(
    *, receipt: NativeOrderReceipt, position: NativePositionProof,
    expected_account_id: str, expected_signal_id: str,
    expected_symbol: str, expected_side: str, reserved_lots: Decimal,
    trusted_native_worker_verified: bool = False,
) -> str:
    """Return SHA-256 proof reference after strict authenticated-MT5 consistency.

    The proof reference is an audit digest, NOT a digital signature. Only a
    supervisor that independently queries the native MT5 account and verifies
    worker identity/session may set trusted_native_worker_verified=True.
    """
    if trusted_native_worker_verified is not True:
        raise FeedRefused('NATIVE_BROKER_AUTHENTICATION_MISSING')
    if not HEX32.fullmatch(expected_account_id):
        raise FeedRefused('ACCOUNT_BINDING_INVALID')
    if not isinstance(expected_signal_id,str) or len(expected_signal_id)!=64 or any(c not in '0123456789abcdef' for c in expected_signal_id):
        raise FeedRefused('SIGNAL_BINDING_INVALID')
    if expected_side not in ('BUY','SELL') or not expected_symbol:
        raise FeedRefused('ORDER_IDENTITY_INVALID')
    if (receipt.environment != 'DEMO' or receipt.broker not in ('deriv','fp_markets') or
        receipt.server != ('Deriv-Demo' if receipt.broker=='deriv' else 'FPMarketsSC-Demo')):
        raise FeedRefused('LIVE_OR_UNEXPECTED_BROKER')
    if (receipt.account_id != expected_account_id or position.account_id != expected_account_id or
        receipt.signal_id != expected_signal_id or receipt.symbol != expected_symbol or
        position.symbol != expected_symbol or receipt.side != expected_side or
        position.side != expected_side or position.position_id != receipt.position_id or
        position.server != receipt.server):
        raise FeedRefused('BROKER_POSITION_OR_CUSTOMER_MISMATCH')
    # MT5 TRADE_RETCODE_DONE == 10009. PLACED (10008) and DONE_PARTIAL
    # (10010) are not proof of a complete protected position lifecycle.
    if receipt.broker_return_code != 10009:
        raise FeedRefused('ORDER_NOT_FULLY_BROKER_FILLED')
    if any(not isinstance(v,str) or not v.isdigit() or int(v)<=0
           for v in (receipt.order_id,receipt.deal_id,receipt.position_id)):
        raise FeedRefused('NO_BROKER_ORDER_DEAL_POSITION_TICKETS')
    try:
        lots=D(reserved_lots)
        if lots<=0 or D(receipt.volume_lots)!=lots or D(position.volume_lots)!=lots:
            raise FeedRefused('FILLED_VOLUME_NOT_RECONCILED')
        if any(D(v)<=0 for v in (position.open_price, position.stop_loss,position.take_profit)):
            raise FeedRefused('NATIVE_PROTECTIVE_STOPS_MISSING')
        if expected_side=='BUY' and not(D(position.stop_loss)<D(position.open_price)<D(position.take_profit)):
            raise FeedRefused('BROKER_BUY_SL_TP_GEOMETRY_INVALID')
        if expected_side=='SELL' and not(D(position.take_profit)<D(position.open_price)<D(position.stop_loss)):
            raise FeedRefused('BROKER_SELL_SL_TP_GEOMETRY_INVALID')
    except (TypeError,ValueError) as e:
        if isinstance(e,FeedRefused):
            raise
        raise FeedRefused('BROKER_NUMERIC_PROOF_UNVERIFIED') from None
    if position.pending_remainder_or_unknown_order or not position.in_reconciled_open_exposure:
        raise FeedRefused('POSITION_NOT_IN_RECONCILED_EXPOSURE')
    if (receipt.broker_time.tzinfo is None or position.broker_snapshot_time.tzinfo is None or
        receipt.broker_time.utcoffset() is None or position.broker_snapshot_time.utcoffset() is None or
        receipt.broker_time > position.broker_snapshot_time):
        raise FeedRefused('BROKER_RECEIPT_POSITION_CLOCK_UNVERIFIED')
    if (position.broker_snapshot_time-receipt.broker_time).total_seconds()>300:
        raise FeedRefused('BROKER_POSITION_EVIDENCE_TOO_OLD')
    sanitized={
        'broker':receipt.broker,'environment':receipt.environment,
        'account_id':receipt.account_id,'signal_id':receipt.signal_id,
        'order_id':receipt.order_id,'deal_id':receipt.deal_id,
        'position_id':receipt.position_id,'symbol':receipt.symbol,'side':receipt.side,
        'filled_volume':str(lots),'stop_price':str(D(position.stop_loss)),
        'take_price':str(D(position.take_profit)),
        'broker_time':receipt.broker_time.astimezone(timezone.utc).isoformat(),
        'snapshot_time':position.broker_snapshot_time.astimezone(timezone.utc).isoformat(),
    }
    return sha256(json.dumps(sanitized,sort_keys=True,separators=(',', ':')).encode()).hexdigest()


def finalize_fully_reconciled_demo_receipt(
    *, store: ReservationStore, receipt: NativeOrderReceipt,
    position: NativePositionProof, reserved_lots: Decimal,
    trusted_native_worker_verified: bool = False,
) -> str:
    """Mark only an authenticated, fully protected and reconciled DEMO fill.

    Caller must have already updated account/customer position exposure from
    the exact authenticated broker snapshot used in the proof. It is unsafe to
    release risk while any accepted order outcome is still ambiguous.
    """
    proof=verify_demo_broker_position(
        receipt=receipt,position=position,expected_account_id=receipt.account_id,
        expected_signal_id=receipt.signal_id,expected_symbol=receipt.symbol,
        expected_side=receipt.side,reserved_lots=reserved_lots,
        trusted_native_worker_verified=trusted_native_worker_verified)
    store.complete(receipt.account_id,receipt.signal_id,outcome='RECONCILED',
                   broker_proof=proof,now=position.broker_snapshot_time,
                   reconciled_snapshot_includes_position=True)
    return proof