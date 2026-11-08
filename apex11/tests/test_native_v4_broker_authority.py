"""Offline contract tests for guarded broker authority and native OFF handoff."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import pytest

from abutron_replacement.native_v4_broker_authority import Verified6207NativeAuthority
from abutron_replacement.native_v4_off_fence import NativeOrderIdentity,NativeV4OffFence
from abutron_replacement.native_receipt_guard import (
    NativeOrderReceipt, NativePositionProof, verify_demo_broker_position
)
from abutron_replacement.production_contracts import FeedRefused
from test_exclusive_native_writer import assemble,call,OWNER,CID


def build(tmp_path):
    x=assemble(tmp_path)
    s=call(x)
    assert s.request_queued
    req=x["port"].requests[0]
    evidence=x["supervisor"].evidence
    now=x["now"]
    identity=NativeOrderIdentity(
        customer_id=OWNER,account_id=CID,signal_id=req.signal_id,
        worker_nonce=req.worker_nonce,login=req.mt5_login,broker="deriv",
        server="Deriv-Demo",environment="DEMO",symbol=req.symbol,side=req.side,
        volume=req.volume_lots,sl=req.stop_price,tp=req.take_price,
        revision=req.activation_revision,expires_utc=req.expires_at_utc)
    authority=Verified6207NativeAuthority(
        supervisor=x["supervisor"],activation=x["activation"],
        reservations=x["kw"]["store"])
    fence=NativeV4OffFence(
        activation=x["activation"],reservations=x["kw"]["store"],authority=authority)
    return x,identity,authority,fence,now


def test_broker_authority_double_attests_actual_snapshot_and_order_fields(tmp_path):
    x,i,authority,fence,now=build(tmp_path)
    authority.assert_eligible(identity=i,phase="CLAIM",now=now)
    authority.assert_eligible(identity=i,phase="SEND",now=now)
    x["supervisor"].unchanged=False
    with pytest.raises(FeedRefused,match="BROKER_OR_CRM_REVISED"):
        authority.assert_eligible(identity=i,phase="SEND",now=now)
    x["supervisor"].unchanged=True
    with pytest.raises(FeedRefused,match="STOP_GEOMETRY_CHANGED"):
        authority.assert_eligible(identity=replace(i,sl="20"),phase="CLAIM",now=now)
    with pytest.raises(FeedRefused,match="UNSUPPORTED_PHASE"):
        authority.assert_eligible(identity=i,phase="LIVE",now=now)


def test_full_native_claim_send_off_and_independent_protected_broker_reconcile(tmp_path):
    x,i,authority,fence,now=build(tmp_path)
    lease=fence.claim(identity=i,now=now)
    assert fence.send(identity=i,lease_id=lease.lease_id,now=now).state=="SENDING"
    a=x["activation"].snapshot(account_id=CID,customer_id=OWNER,now=now)
    x["activation"].request(account_id=CID,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=now)
    assert fence.off_state(customer_id=OWNER,account_id=CID,
        now=now)=="STOPPING_BROKER_RECONCILIATION_REQUIRED"
    lots=Decimal(i.volume)
    receipt=NativeOrderReceipt(
        "deriv","DEMO","Deriv-Demo",CID,i.signal_id,i.symbol,i.side,
        10009,"61001","61002","61003",lots,now)
    position=NativePositionProof(
        CID,"Deriv-Demo","61003",i.symbol,i.side,lots,
        Decimal("100"),Decimal("90"),Decimal("110"),
        now+timedelta(seconds=1),True,False)
    x["supervisor"].receipt=receipt
    x["supervisor"].position=position
    x["supervisor"].included=True
    proof=verify_demo_broker_position(
        receipt=receipt,position=position,expected_account_id=CID,
        expected_signal_id=i.signal_id,expected_symbol=i.symbol,
        expected_side=i.side,reserved_lots=lots,
        trusted_native_worker_verified=True)
    with pytest.raises(FeedRefused,match="BROKER_PROOF_MISMATCH"):
        fence.reconcile(identity=i,lease_id=lease.lease_id,
            outcome="PROTECTED_POSITION",proof_ref="wrong-broker-proof",
            now=now+timedelta(seconds=1))
    assert fence.off_state(customer_id=OWNER,account_id=CID,
        now=now+timedelta(seconds=1))=="STOPPING_BROKER_RECONCILIATION_REQUIRED"
    fence.reconcile(identity=i,lease_id=lease.lease_id,
        outcome="PROTECTED_POSITION",proof_ref=proof,
        now=now+timedelta(seconds=1))
    assert fence.off_state(customer_id=OWNER,account_id=CID,
        now=now+timedelta(seconds=1))=="OFF_SETTLED"


def test_no_order_result_never_faked_by_broker_authority(tmp_path):
    x,i,authority,fence,now=build(tmp_path)
    lease=fence.claim(identity=i,now=now)
    with pytest.raises(FeedRefused,match="NO_ORDER_NOT_YET_CERTIFIED"):
        fence.reconcile(identity=i,lease_id=lease.lease_id,
            outcome="BROKER_REJECTED_NO_ORDER",proof_ref="claimed-no-broker-order",
            now=now)
    a=x["activation"].snapshot(account_id=CID,customer_id=OWNER,now=now)
    x["activation"].request(account_id=CID,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=now)
    assert fence.off_state(customer_id=OWNER,account_id=CID,
        now=now)=="STOPPING_BROKER_RECONCILIATION_REQUIRED"
