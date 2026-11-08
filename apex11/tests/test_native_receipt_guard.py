"""Mock-only broker receipt proof tests (no MT5 session)."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
from decimal import Decimal
import pytest
from abutron_replacement.production_contracts import FeedRefused
from abutron_replacement.native_receipt_guard import (
    NativeOrderReceipt, NativePositionProof, verify_demo_broker_position,
    finalize_fully_reconciled_demo_receipt,
)
from risk_guard.abutron_risk_guard import D
from risk_guard.reservation_store import ReservationStore
from test_native_risk_preflight import inputs

NOW=datetime(2026,11,8,3,30,tzinfo=timezone.utc)
C='1'*32
S='2'*64
M='Volatility 75 Index.0'


def make():
    r=NativeOrderReceipt('deriv','DEMO','Deriv-Demo',C,S,M,'BUY',10009,
                         '100101','100102','100103',D('0.50'),NOW)
    p=NativePositionProof(C,'Deriv-Demo','100103',M,'BUY',D('0.50'),
                         D('100'),D('90'),D('110'),NOW+timedelta(seconds=1),True,False)
    return r,p


def valid(r,p):
    return verify_demo_broker_position(receipt=r,position=p,
        expected_account_id=C,expected_signal_id=S,expected_symbol=M,expected_side='BUY',
        reserved_lots=D('0.50'),trusted_native_worker_verified=True)


def test_verified_demo_receipt_has_stable_sanitized_digest():
    r,p=make()
    assert len(valid(r,p))==64
    assert valid(r,p)==valid(r,p)


def test_unverified_worker_or_live_denied():
    r,p=make()
    with pytest.raises(FeedRefused,match='AUTHENTICATION'):
        verify_demo_broker_position(receipt=r,position=p,
            expected_account_id=C,expected_signal_id=S,expected_symbol=M,
            expected_side='BUY',reserved_lots=D('0.50'))
    with pytest.raises(FeedRefused,match='LIVE'):
        valid(replace(r,environment='LIVE'),p)


def test_wrong_account_or_position_rejected():
    r,p=make()
    with pytest.raises(FeedRefused,match='MISMATCH'):
        valid(r,replace(p,account_id='3'*32))
    with pytest.raises(FeedRefused,match='MISMATCH'):
        valid(r,replace(p,position_id='100104'))
    with pytest.raises(FeedRefused,match='MISMATCH'):
        valid(replace(r,signal_id='3'*64),p)


def test_placed_partial_unknown_not_reconciled():
    r,p=make()
    for ret in (10008,10010,10012):
        with pytest.raises(FeedRefused,match='NOT_FULLY'):
            valid(replace(r,broker_return_code=ret),p)
    with pytest.raises(FeedRefused,match='EXPOSURE'):
        valid(r,replace(p,pending_remainder_or_unknown_order=True))


def test_protective_sl_tp_and_filled_volume_required():
    r,p=make()
    with pytest.raises(FeedRefused,match='STOPS'):
        valid(r,replace(p,stop_loss=D('0')))
    with pytest.raises(FeedRefused,match='GEOMETRY'):
        valid(r,replace(p,stop_loss=D('120')))
    with pytest.raises(FeedRefused,match='VOLUME'):
        valid(r,replace(p,volume_lots=D('0.25')))


def test_unauthenticated_account_timestamp_does_not_count():
    r,p=make()
    with pytest.raises(FeedRefused,match='CLOCK'):
        valid(r,replace(p,broker_snapshot_time=NOW-timedelta(seconds=1)))
    with pytest.raises(FeedRefused,match='CLOCK'):
        valid(replace(r,broker_time=NOW.replace(tzinfo=None)),p)


def test_cannot_release_reservation_without_native_worker_attestation(tmp_path):
    kw=inputs(tmp_path)
    from abutron_replacement.native_risk_preflight import reserve_apex11_demo_candidate
    result=reserve_apex11_demo_candidate(**kw)
    assert result.risk_reserved
    r,p=make()
    r=replace(r,account_id=kw['proposal'].account_id,
        signal_id=kw['proposal'].signal_id,symbol=kw['proposal'].symbol,
        volume_lots=result.reserved_volume)
    p=replace(p,account_id=kw['proposal'].account_id,symbol=kw['proposal'].symbol,
        volume_lots=result.reserved_volume)
    with pytest.raises(FeedRefused,match='AUTHENTICATION'):
        finalize_fully_reconciled_demo_receipt(store=kw['store'],receipt=r,
            position=p,reserved_lots=result.reserved_volume)
    kw['store'].mark_unknown(kw['proposal'].account_id,kw['proposal'].signal_id)
    proof=finalize_fully_reconciled_demo_receipt(store=kw['store'],receipt=r,
        position=p,reserved_lots=result.reserved_volume,
        trusted_native_worker_verified=True)
    assert len(proof)==64
    with pytest.raises(ValueError):
        finalize_fully_reconciled_demo_receipt(store=kw['store'],receipt=r,
            position=p,reserved_lots=result.reserved_volume,
            trusted_native_worker_verified=True)