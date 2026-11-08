"""Mock-only Milestone A exclusive writer integration tests; zero MT5 or broker I/O."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import fcntl
import os
import sqlite3
import pytest

from abutron_replacement.account_bound_publisher import DecisionJournal
from abutron_replacement.exclusive_native_writer import (
    BrokerExecutionEvidence, ExclusiveApex11DemoWriter,
    existing_native_writer_lock,
)
from abutron_replacement.production_contracts import BrokerBoundBars, FeedRefused
from abutron_replacement.transactional_activation import ActivationStore
from abutron_replacement.native_receipt_guard import NativeOrderReceipt, NativePositionProof
from risk_guard.abutron_risk_guard import D
from test_native_risk_preflight import inputs
from test_hardening_4_blockers import OWNER, CID


class Supervisor:
    def __init__(self, evidence):
        self.evidence = evidence
        self.unchanged = True
        self.receipt = None
        self.position = None
        self.included = False
        self.calls = 0
    def attest(self, *, customer_id, account_id, observed_at):
        self.calls += 1
        return self.evidence
    def verify_unchanged(self, *, evidence, observed_at):
        return self.unchanged
    def authenticated_receipt_and_position(self, *, account_id, signal_id, observed_at):
        return self.receipt, self.position, self.included


class Port:
    def __init__(self):
        self.requests = []
        self.error = None
    def assert_ready(self, request, evidence):
        assert request.activation_revision == evidence.effective_activation_revision
        assert request.broker == 'deriv'
        assert request.server == 'Deriv-Demo'
        if self.error == "ready":
            raise FeedRefused("EA_NO_LONGER_READY")
    def queue_once(self, request, evidence):
        if self.error == "queue":
            raise OSError("SIMULATED_NATIVE_QUEUE_OUTCOME_UNCERTAIN")
        self.requests.append(request)


def assemble(tmp_path):
    kw = inputs(tmp_path)
    now = kw["now"]
    activation=ActivationStore(tmp_path/"activation.sqlite")
    activation.provision(account_id=CID,customer_id=OWNER,broker="deriv",now=now)
    s=activation.request(account_id=CID,customer_id=OWNER,
        expected_revision=1,desired_on=True,now=now)
    s=activation.update_attestation(account_id=CID,customer_id=OWNER,
        expected_revision=s.revision,entitlement_ok=True,connected=True,
        writer_verified=True,kill_switch=False,now=now)
    a=activation.acknowledge(account_id=CID,customer_id=OWNER,
                            expected_revision=s.revision,now=now)
    assert a.effective_on
    e=BrokerExecutionEvidence(
        gate=kw["gate"], native=kw["native"],customer=kw["customer"],
        proposal=kw["proposal"], mt5_login="1006207",
        worker_nonce="f"*32,attested_at=now,native_ea_protocol=4,
        native_ea_heartbeat_fresh=True,revision_fenced_by_native_ea=True,
        legacy_writer_same_lock_verified=True,
        outstanding_unknown_orders_reconciled=True,
        effective_activation_revision=a.revision)
    supervisor=Supervisor(e)
    port=Port()
    doc=dict(kw["signal"])
    doc.update(publication_schema="abutron.apex11.account.shadow.v1",
               customer_id=OWNER,connection_id=CID,source_kind="deriv_native_mt5_v2",
               source_sha256="e"*64,order=None,broker_order_authorized=False,
               orders_submitted=0)
    feed=BrokerBoundBars(connection_id=CID,broker="deriv",environment="DEMO",
         server="Deriv-Demo",symbol=doc["symbol"],source_sha256="e"*64,
         source_kind="deriv_native_mt5_v2",bars=(),checked_at=now.timestamp())
    journal=DecisionJournal(tmp_path/"journal.sqlite")
    pub=journal.add(customer_id=OWNER,account_id=CID,feed=feed,
        closed_ts=int(doc["bar_closed_ts"]),bar_sha256="a"*64,
        manifest_sha256="b"*64,proposal=doc,published_at=now)
    writer=ExclusiveApex11DemoWriter(journal=journal,activation=activation,
        reservations=kw["store"],supervisor=supervisor,port=port,
        shared_lock=tmp_path/"execution-writer.lock")
    return dict(writer=writer,activation=activation,supervisor=supervisor,
                port=port,kw=kw,doc=doc,pub=pub,now=now)


def call(x, **overrides):
    params=dict(customer_id=OWNER,account_id=CID,
                publication_id=x["pub"].publication_id,now=x["now"])
    params.update(overrides)
    return x["writer"].submit_one(**params)


def record_state(x):
    with sqlite3.connect(x["kw"]["store"].path) as db:
        return db.execute("SELECT state FROM intents").fetchall()


def test_account_bound_only_single_native_request_risk_stays_unknown(tmp_path):
    x=assemble(tmp_path)
    r=call(x)
    assert r.status=="NATIVE_REQUEST_QUEUED" and r.request_queued
    assert r.broker_orders_confirmed == 0
    assert r.broker_order_authorized is False
    assert r.signal_id == x["kw"]["proposal"].signal_id
    assert len(x["port"].requests) == 1
    cmd=x["port"].requests[0]
    assert cmd.activation_revision == x["supervisor"].evidence.effective_activation_revision
    assert cmd.signal_id == r.signal_id and cmd.volume_lots=="0.43"
    assert record_state(x)==[("UNKNOWN",)]
    r2=call(x)
    assert r2.status=="BLOCKED" and "ALREADY_RESERVED" in r2.reason
    assert len(x["port"].requests)==1


def test_legacy_v3_ea_cannot_authorize_order(tmp_path):
    x=assemble(tmp_path)
    x["supervisor"].evidence=replace(x["supervisor"].evidence,
         native_ea_protocol=3,revision_fenced_by_native_ea=False)
    with pytest.raises(FeedRefused,match="V4_REVISION"):
        call(x)
    assert not record_state(x) and not x["port"].requests


def test_false_ea_revision_fencing_without_protocol_upgrade_rejected(tmp_path):
    x=assemble(tmp_path)
    x["supervisor"].evidence=replace(x["supervisor"].evidence,
         revision_fenced_by_native_ea=False)
    with pytest.raises(FeedRefused,match="V4_REVISION"):
        call(x)


def test_off_switch_revokes_before_native_request(tmp_path):
    x=assemble(tmp_path)
    a=x["activation"].snapshot(account_id=CID,customer_id=OWNER,now=x["now"])
    x["activation"].request(account_id=CID,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=x["now"])
    with pytest.raises(FeedRefused,match="EFFECTIVE_ON"):
        call(x)
    assert not x["port"].requests and not record_state(x)


def test_stale_worker_attestation_refused(tmp_path):
    x=assemble(tmp_path)
    x["supervisor"].evidence=replace(x["supervisor"].evidence,
        attested_at=x["now"]-timedelta(seconds=25))
    with pytest.raises(FeedRefused,match="EVIDENCE_STALE"):
        call(x)
    assert not record_state(x)


def test_wrong_tenant_and_forged_published_id_rejected(tmp_path):
    x=assemble(tmp_path)
    with pytest.raises(FeedRefused,match="ACCOUNT_BOUND_PUBLICATION_MISSING"):
        call(x,publication_id="a"*64)
    with pytest.raises(FeedRefused,match="OWNER_OR_ACCOUNT_ID"):
        call(x,customer_id="invalid")
    assert not record_state(x)


def test_shared_legacy_writer_lock_is_exclusive(tmp_path):
    x=assemble(tmp_path)
    with existing_native_writer_lock(x["writer"].shared_lock):
        with pytest.raises(FeedRefused,match="BUSY"):
            call(x)
    assert not record_state(x)


def test_broker_changed_after_reservation_is_never_retried(tmp_path):
    x=assemble(tmp_path)
    x["supervisor"].unchanged=False
    result=call(x)
    assert result.status=="UNKNOWN"
    assert not x["port"].requests
    assert record_state(x)==[("UNKNOWN",)]
    assert call(x).status=="BLOCKED"


@pytest.mark.parametrize("stage",["ready","queue"])
def test_transport_error_never_releases_risk_or_requeues(tmp_path,stage):
    x=assemble(tmp_path)
    x["port"].error=stage
    r=call(x)
    assert r.status=="UNKNOWN" and not r.request_queued
    assert record_state(x)==[("UNKNOWN",)]
    x["port"].error=None
    assert call(x).status=="BLOCKED"
    assert not x["port"].requests


def test_no_hold_or_old_signal_or_bad_native_identity(tmp_path):
    x=assemble(tmp_path)
    with pytest.raises(FeedRefused,match="NOT_FRESH"):
        call(x,now=x["now"]+timedelta(seconds=1000))
    x["supervisor"].evidence=replace(x["supervisor"].evidence,mt5_login="1000512")
    with pytest.raises(FeedRefused,match="6207"):
        call(x)
    assert not record_state(x)


def test_wrong_session_rejected_and_keeps_worker_idle(tmp_path):
    x=assemble(tmp_path)
    x["supervisor"].evidence=replace(x["supervisor"].evidence,
        gate=replace(x["supervisor"].evidence.gate,server="Deriv-Live"))
    with pytest.raises(FeedRefused,match="ENVIRONMENT"):
        call(x)
    assert not x["port"].requests


def test_realistic_receipt_requires_broker_position_and_stops(tmp_path):
    x=assemble(tmp_path)
    result=call(x)
    lots=D(x["port"].requests[0].volume_lots)
    from datetime import timedelta
    from dataclasses import replace
    from abutron_replacement.native_receipt_guard import NativeOrderReceipt, NativePositionProof
    now=x["now"]
    r=NativeOrderReceipt("deriv","DEMO","Deriv-Demo",CID,result.signal_id,
       x["doc"]["symbol"],x["doc"]["status"],10009,"100101","100102","100103",lots,now)
    p=NativePositionProof(CID,"Deriv-Demo","100103",x["doc"]["symbol"],
       x["doc"]["status"],lots,D("100"),D("90"),D("110"),
       now+timedelta(seconds=1),True,False)
    x["supervisor"].receipt=r
    x["supervisor"].position=p
    with pytest.raises(FeedRefused,match="EXPOSURE_NOT_RECONCILED"):
        x["writer"].reconcile_fully_protected(customer_id=OWNER,account_id=CID,
            signal_id=result.signal_id,reserved_lots=str(lots),now=now)
    x["supervisor"].included=True
    proof=x["writer"].reconcile_fully_protected(customer_id=OWNER,account_id=CID,
        signal_id=result.signal_id,reserved_lots=str(lots),now=now)
    assert len(proof)==64
    assert record_state(x)==[("RECONCILED",)]
    with pytest.raises(ValueError,match="ALREADY_FINALIZED"):
        x["writer"].reconcile_fully_protected(customer_id=OWNER,account_id=CID,
            signal_id=result.signal_id,reserved_lots=str(lots),now=now)


def test_untrusted_writer_lock_and_false_broker_risk_refused(tmp_path):
    x=assemble(tmp_path)
    p=x["writer"].shared_lock
    p.symlink_to(tmp_path/"nonexistent")
    with pytest.raises((OSError,FeedRefused)):
        call(x)
    p.unlink()
    x["supervisor"].evidence=replace(x["supervisor"].evidence,
        native=replace(x["supervisor"].evidence.native,broker_order_check_verified=False))
    with pytest.raises(FeedRefused,match="MANDATORY_PROOF_MISSING"):
        call(x)


def test_receipt_cannot_cross_customer_or_replace_reserved_volume(tmp_path):
    x=assemble(tmp_path)
    result=call(x)
    lots=D(x["port"].requests[0].volume_lots)
    now=x["now"]
    x["supervisor"].receipt=NativeOrderReceipt(
        "deriv","DEMO","Deriv-Demo",CID,result.signal_id,
        x["doc"]["symbol"],"BUY",10009,"200101","200102","200103",
        lots,now)
    x["supervisor"].position=NativePositionProof(
        CID,"Deriv-Demo","200103",x["doc"]["symbol"],"BUY",
        lots,D("100"),D("90"),D("110"),
        now+timedelta(seconds=1),True,False)
    x["supervisor"].included=True
    with pytest.raises(PermissionError,match="OWNED"):
        x["writer"].reconcile_fully_protected(
            customer_id="9"*32, account_id=CID,
            signal_id=result.signal_id,reserved_lots=str(lots),now=now)
    with pytest.raises(FeedRefused,match="RESERVED_LOTS"):
        x["writer"].reconcile_fully_protected(
            customer_id=OWNER,account_id=CID,
            signal_id=result.signal_id,reserved_lots="0.01",now=now)
    x["supervisor"].position=replace(x["supervisor"].position,
        broker_snapshot_time=now-timedelta(seconds=120))
    with pytest.raises(FeedRefused,match="SNAPSHOT_STALE"):
        x["writer"].reconcile_fully_protected(
            customer_id=OWNER,account_id=CID,
            signal_id=result.signal_id,reserved_lots=str(lots),now=now)
    assert record_state(x)==[("UNKNOWN",)]


def test_client_off_does_not_block_broker_reconciliation(tmp_path):
    x=assemble(tmp_path)
    result=call(x)
    lots=D(x["port"].requests[0].volume_lots)
    now=x["now"]
    x["supervisor"].receipt=NativeOrderReceipt(
        "deriv","DEMO","Deriv-Demo",CID,result.signal_id,
        x["doc"]["symbol"],"BUY",10009,"300101","300102","300103",
        lots,now)
    x["supervisor"].position=NativePositionProof(
        CID,"Deriv-Demo","300103",x["doc"]["symbol"],"BUY",
        lots,D("100"),D("90"),D("110"),now+timedelta(seconds=1),True,False)
    x["supervisor"].included=True
    a=x["activation"].snapshot(account_id=CID,customer_id=OWNER,now=now)
    x["activation"].request(account_id=CID,customer_id=OWNER,
        desired_on=False,expected_revision=a.revision,now=now)
    proof=x["writer"].reconcile_fully_protected(
        customer_id=OWNER,account_id=CID,
        signal_id=result.signal_id,reserved_lots=str(lots),now=now)
    assert len(proof)==64
    assert record_state(x)==[("RECONCILED",)]
