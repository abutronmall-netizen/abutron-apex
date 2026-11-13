"""Contract tests for serialized Deriv 6207 DEMO claim/send/OFF barrier.

All broker authorities are FAKE. No production terminal, order or network.
"""
from datetime import datetime,timezone,timedelta
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import pytest

from abutron_replacement.native_v4_off_fence import (
    NativeV4OffFence, NativeOrderIdentity,
)
from abutron_replacement.transactional_activation import ActivationStore
from abutron_replacement.production_contracts import FeedRefused
from risk_guard.reservation_store import ReservationStore,_signal_key

OWNER="a"*32
ACCOUNT="b"*32
NONCE="c"*32
SIGNAL="d"*64
START=datetime(2026,11,8,6,40,tzinfo=timezone.utc)


class StubAuthenticatedBroker:
    def __init__(self):
        self.attempts=[]
        self.pass_preflight=True
        self.pass_proof=False
    def assert_eligible(self, *, identity, phase, now):
        self.attempts.append(phase)
        if not self.pass_preflight:
            raise FeedRefused("TEST_BROKER_DENY")
    def assert_broker_result(self, *, identity, outcome, proof_ref, now):
        if not self.pass_proof:
            raise FeedRefused("TEST_NO_AUTHENTIC_BROKER_CONFIRMATION")


def initialize(tmp_path):
    act=ActivationStore(tmp_path/"activation.sqlite")
    risk=ReservationStore(tmp_path/"risk.sqlite")
    act.provision(account_id=ACCOUNT,customer_id=OWNER,broker="deriv",now=START)
    a=act.request(account_id=ACCOUNT,customer_id=OWNER,
                  desired_on=True,expected_revision=1,now=START)
    a=act.update_attestation(account_id=ACCOUNT,customer_id=OWNER,
                  expected_revision=a.revision,entitlement_ok=True,
                  connected=True,writer_verified=True,kill_switch=False,now=START)
    a=act.acknowledge(account_id=ACCOUNT,customer_id=OWNER,
                      expected_revision=a.revision,now=START)
    assert a.effective_on
    identity=NativeOrderIdentity(
        customer_id=OWNER,account_id=ACCOUNT,signal_id=SIGNAL,worker_nonce=NONCE,
        login="1006207",broker="deriv",server="Deriv-Demo",environment="DEMO",
        symbol="Volatility 50 Index.0",side="BUY",volume="0.43",
        sl="98",tp="105",revision=a.revision,
        expires_utc=int(START.timestamp())+12)
    with risk._db() as db:
        db.execute("""INSERT INTO intents
            (signal_key,intent_sha,customer_id,account_id,risk_usd,
             risk_account_ccy,state,volume,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (_signal_key(ACCOUNT,SIGNAL),"e"*64,OWNER,ACCOUNT,
             "7","7","UNKNOWN","0.43",START.isoformat()))
    broker=StubAuthenticatedBroker()
    guard=NativeV4OffFence(activation=act,reservations=risk,authority=broker)
    return act,risk,identity,broker,guard


def test_two_stage_claim_send_is_single_use(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    lease=g.claim(identity=i,now=START)
    assert len(lease.lease_id)==64 and lease.state=="CLAIMED"
    assert g.send(identity=i,lease_id=lease.lease_id,now=START).state=="SENDING"
    assert b.attempts==["CLAIM","SEND"]
    with pytest.raises(FeedRefused,match="REPLAY"):
        g.send(identity=i,lease_id=lease.lease_id,now=START)
    with pytest.raises((sqlite3.IntegrityError,FeedRefused)):
        g.claim(identity=i,now=START)


def test_off_after_claim_does_not_permit_send_or_false_settlement(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    lease=g.claim(identity=i,now=START)
    a=act.snapshot(account_id=ACCOUNT,customer_id=OWNER,now=START)
    off=act.request(account_id=ACCOUNT,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=START)
    assert not off.effective_on
    assert g.off_state(customer_id=OWNER,account_id=ACCOUNT,now=START)=="STOPPING_BROKER_RECONCILIATION_REQUIRED"
    with pytest.raises(FeedRefused,match="ACCOUNT_OFF"):
        g.send(identity=i,lease_id=lease.lease_id,now=START)
    assert b.attempts==["CLAIM"]


def test_off_after_send_stays_stopping_without_verified_outcome(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    lease=g.claim(identity=i,now=START)
    g.send(identity=i,lease_id=lease.lease_id,now=START)
    a=act.snapshot(account_id=ACCOUNT,customer_id=OWNER,now=START)
    act.request(account_id=ACCOUNT,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=START)
    assert g.off_state(customer_id=OWNER,account_id=ACCOUNT,now=START)=="STOPPING_BROKER_RECONCILIATION_REQUIRED"
    with pytest.raises(FeedRefused,match="TEST_NO_AUTHENTIC_BROKER_CONFIRMATION"):
        g.reconcile(identity=i,lease_id=lease.lease_id,
                   outcome="PROTECTED_POSITION",proof_ref="native-proof-100",
                   now=START+timedelta(seconds=45))
    assert g.off_state(customer_id=OWNER,account_id=ACCOUNT,
        now=START+timedelta(seconds=45))=="STOPPING_BROKER_RECONCILIATION_REQUIRED"


def test_verified_broker_result_after_risk_finalization_settles_off(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    lease=g.claim(identity=i,now=START)
    g.send(identity=i,lease_id=lease.lease_id,now=START)
    a=act.snapshot(account_id=ACCOUNT,customer_id=OWNER,now=START)
    act.request(account_id=ACCOUNT,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=START)
    b.pass_proof=True
    proof="broker-authenticated-position-snapshot-100"
    risk.complete(ACCOUNT,SIGNAL,outcome="RECONCILED",broker_proof=proof,
        now=START+timedelta(seconds=40),reconciled_snapshot_includes_position=True)
    g.reconcile(identity=i,lease_id=lease.lease_id,
                outcome="PROTECTED_POSITION",proof_ref=proof,
                now=START+timedelta(seconds=40))
    assert g.off_state(customer_id=OWNER,account_id=ACCOUNT,
                now=START+timedelta(seconds=40))=="OFF_SETTLED"
    with pytest.raises(FeedRefused,match="RECONCILE_IDENTITY_OR_STATE"):
        g.reconcile(identity=i,lease_id=lease.lease_id,
                    outcome="PROTECTED_POSITION",proof_ref=proof,
                    now=START+timedelta(seconds=40))


def test_no_auto_expiry_or_replay_of_unknown_send(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    lease=g.claim(identity=i,now=START)
    after=START+timedelta(seconds=200)
    with pytest.raises(FeedRefused,match="DEMO_6207_IDENTITY_OR_EXPIRY"):
        g.send(identity=i,lease_id=lease.lease_id,now=after)
    a=act.snapshot(account_id=ACCOUNT,customer_id=OWNER,now=START)
    act.request(account_id=ACCOUNT,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=START)
    assert g.off_state(customer_id=OWNER,account_id=ACCOUNT,now=after)=="STOPPING_BROKER_RECONCILIATION_REQUIRED"


def test_wrong_revision_identity_account_environment_or_lot_denied(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    changes=[
        dict(revision=i.revision+1),
        dict(login="1000512"),
        dict(environment="LIVE"),
        dict(server="Deriv-Live"),
        dict(account_id="f"*32),
        dict(volume="2.0"),
        dict(signal_id="0"*64),
    ]
    for edit in changes:
        with pytest.raises((FeedRefused,PermissionError,ValueError)):
            g.claim(identity=replace(i,**edit),now=START)
    assert not b.attempts or "SEND" not in b.attempts


def test_off_before_claim_and_untrusted_broker_denied(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    b.pass_preflight=False
    with pytest.raises(FeedRefused,match="TEST_BROKER_DENY"):
        g.claim(identity=i,now=START)
    a=act.snapshot(account_id=ACCOUNT,customer_id=OWNER,now=START)
    act.request(account_id=ACCOUNT,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=START)
    with pytest.raises(FeedRefused,match="ACCOUNT_OFF"):
        g.claim(identity=i,now=START)


def test_two_contending_claims_only_one_wins(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:claim_result(g,i),range(2)))
    assert results.count("CLAIMED")==1
    assert results.count("BLOCKED")==1


def claim_result(g,i):
    try:return g.claim(identity=i,now=START).state
    except (FeedRefused,sqlite3.IntegrityError):return "BLOCKED"


def test_source_requires_real_trusted_authority(tmp_path):
    act=ActivationStore(tmp_path/"activation.sqlite")
    risk=ReservationStore(tmp_path/"risk.sqlite")
    with pytest.raises(TypeError,match="AUTHORITY_REQUIRED"):
        NativeV4OffFence(activation=act,reservations=risk,authority=None)


def test_no_settled_off_for_unknown_broker_proof(tmp_path):
    act,risk,i,b,g=initialize(tmp_path)
    lease=g.claim(identity=i,now=START)
    b.pass_proof=True
    with pytest.raises(FeedRefused,match="FINALIZED_RISK"):
        g.reconcile(identity=i,lease_id=lease.lease_id,
                    outcome="BROKER_REJECTED_NO_ORDER",
                    proof_ref="authenticated-history-empty-100",
                    now=START+timedelta(seconds=50))
    a=act.snapshot(account_id=ACCOUNT,customer_id=OWNER,now=START)
    act.request(account_id=ACCOUNT,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=START)
    assert g.off_state(customer_id=OWNER,account_id=ACCOUNT,now=START)=="STOPPING_BROKER_RECONCILIATION_REQUIRED"
