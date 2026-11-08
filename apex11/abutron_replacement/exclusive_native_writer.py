"""Milestone A: fail-closed APEX 1.1.0 -> native writer transaction.

This module shares the existing root order-writer flock inode, consumes only
durably published account-bound APEX M5 decisions, checks authenticated broker
facts, CRM account revision and 0.10/2/3/20 risk reservations, then emits ONE
native request using a privileged transport.

The current V3 native EA is not verified to fence client OFF revisions at the
point of consumption. Until a V4 revision-fenced native adapter is independently
authenticated, the production supervisor MUST fail closed. No LIVE mode, old
signal scanner, TradingAgents or automatic timer switches exist here.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import os
from pathlib import Path
import re
import stat
from typing import Protocol, Any

from abutron_replacement.account_bound_publisher import DecisionJournal
from abutron_replacement.candidate_contract import AccountGate, BrokerNativeRisk
from abutron_replacement.native_risk_preflight import reserve_apex11_demo_candidate
from abutron_replacement.native_receipt_guard import (
    NativeOrderReceipt, NativePositionProof, finalize_fully_reconciled_demo_receipt,
)
from abutron_replacement.transactional_activation import ActivationStore
from abutron_replacement.production_contracts import FeedRefused, HEX32
from risk_guard.abutron_risk_guard import CustomerRisk, Proposal, D
from risk_guard.reservation_store import ReservationStore

PRODUCTION_SHARED_LOCK = Path("/var/lib/apex-client-feed/execution-router/execution-writer.lock")
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_ALLOWED = frozenset({"Volatility 10 Index.0", "Volatility 25 Index.0",
                      "Volatility 50 Index.0", "Volatility 75 Index.0",
                      "Volatility 100 Index.0"})


@dataclass(frozen=True)
class BrokerExecutionEvidence:
    # MUST be produced by a root-owned, independently authenticating broker
    # supervisor, not a user request or a parser trusting its own filename.
    gate: AccountGate
    native: BrokerNativeRisk
    customer: CustomerRisk
    proposal: Proposal
    mt5_login: str
    worker_nonce: str
    attested_at: datetime
    native_ea_protocol: int
    native_ea_heartbeat_fresh: bool
    revision_fenced_by_native_ea: bool
    legacy_writer_same_lock_verified: bool
    outstanding_unknown_orders_reconciled: bool
    effective_activation_revision: int


@dataclass(frozen=True)
class DemoNativeRequest:
    customer_id: str
    account_id: str
    broker: str
    server: str
    mt5_login: str
    worker_nonce: str
    symbol: str
    side: str
    signal_id: str
    activation_revision: int
    volume_lots: str
    expires_at_utc: int


@dataclass(frozen=True)
class Submission:
    status: str
    reason: str
    signal_id: str | None = None
    request_queued: bool = False
    broker_orders_confirmed: int = 0
    broker_order_authorized: bool = False


class VerifiedNativeSupervisor(Protocol):
    def attest(self, *, customer_id: str, account_id: str,
               observed_at: datetime) -> BrokerExecutionEvidence: ...
    def verify_unchanged(self, *, evidence: BrokerExecutionEvidence,
                         observed_at: datetime) -> bool: ...
    def authenticated_receipt_and_position(self, *, account_id: str,
                         signal_id: str, observed_at: datetime
                         ) -> tuple[NativeOrderReceipt, NativePositionProof, bool]: ...


class NativeEARequestPort(Protocol):
    def assert_ready(self, request: DemoNativeRequest,
                     evidence: BrokerExecutionEvidence) -> None: ...
    def queue_once(self, request: DemoNativeRequest,
                   evidence: BrokerExecutionEvidence) -> None: ...


@contextmanager
def existing_native_writer_lock(path: Path = PRODUCTION_SHARED_LOCK):
    """Shares the exact inode/path that the legacy root dispatcher flocks."""
    path = Path(path)
    parent = path.parent
    st = parent.lstat()
    if (not stat.S_ISDIR(st.st_mode) or parent.is_symlink()
            or st.st_mode & 0o022):
        raise FeedRefused("NATIVE_WRITER_LOCK_DIRECTORY_UNSAFE")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        fst = os.fstat(fd)
        if (not stat.S_ISREG(fst.st_mode) or fst.st_nlink != 1 or
                fst.st_mode & 0o077 or fst.st_uid != os.geteuid()):
            raise FeedRefused("NATIVE_WRITER_LOCK_INODE_UNTRUSTED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise FeedRefused("EXCLUSIVE_NATIVE_WRITER_BUSY") from None
        if path.stat().st_ino != fst.st_ino:
            raise FeedRefused("NATIVE_WRITER_LOCK_REPLACED")
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _utc(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise FeedRefused("UNVERIFIED_UTC_CLOCK")
    return now.astimezone(timezone.utc)


def _published(journal: DecisionJournal, publication_id: str,
               customer_id: str, account_id: str) -> dict[str, Any]:
    if not _HEX64.fullmatch(publication_id):
        raise FeedRefused("PUBLICATION_ID_INVALID")
    p = journal.read(publication_id)
    if p is None:
        raise FeedRefused("ACCOUNT_BOUND_PUBLICATION_MISSING")
    if (p.get("publication_schema") != "abutron.apex11.account.shadow.v1" or
            p.get("customer_id") != customer_id or
            p.get("connection_id") != account_id or
            p.get("broker") != "deriv" or
            p.get("engine") != "APEX_1_1_0" or p.get("timeframe") != "M5" or
            p.get("order") is not None or
            p.get("broker_order_authorized") is not False or
            p.get("orders_submitted") != 0 or
            p.get("source_kind") != "deriv_native_mt5_v2" or
            p.get("status") not in ("BUY", "SELL") or
            p.get("symbol") not in _ALLOWED):
        raise FeedRefused("PUBLICATION_NOT_ACCOUNT_BOUND_DEMO_DIRECTIONAL")
    close = p.get("bar_closed_ts")
    if (type(close) not in (int,float) or close != int(close)
            or int(close) % 300):
        raise FeedRefused("PUBLICATION_CLOSED_BAR_INVALID")
    key = "|".join((customer_id,account_id,"deriv",p["symbol"],str(int(close))))
    if sha256(("APEX11_M5_SHADOW|" + key).encode()).hexdigest() != publication_id:
        raise FeedRefused("PUBLICATION_IDENTITY_HASH_MISMATCH")
    return p


def _evidence(e: BrokerExecutionEvidence, *, customer_id: str,
              account_id: str, now: datetime, revision: int) -> None:
    g = e.gate
    if (g.owner != customer_id or g.connection_id != account_id or
            g.broker != "deriv" or g.server != "Deriv-Demo" or
            g.environment != "DEMO"):
        raise FeedRefused("NATIVE_ACCOUNT_OWNER_OR_ENVIRONMENT_MISMATCH")
    if (type(e.mt5_login) is not str or not e.mt5_login.isascii() or
            not e.mt5_login.isdecimal() or not e.mt5_login.endswith("6207")):
        raise FeedRefused("6207_DEMO_ACCOUNT_NOT_ATTESTED")
    if type(e.worker_nonce) is not str or not HEX32.fullmatch(e.worker_nonce):
        raise FeedRefused("NATIVE_EA_NONCE_NOT_ATTESTED")
    if (e.customer.customer_id != customer_id or
            e.proposal.customer_id != customer_id or
            e.proposal.account_id != account_id):
        raise FeedRefused("CUSTOMER_RISK_INVENTORY_MISMATCH")
    if (e.native_ea_protocol < 4 or not e.native_ea_heartbeat_fresh or
            not e.revision_fenced_by_native_ea or
            not e.legacy_writer_same_lock_verified or
            not e.outstanding_unknown_orders_reconciled):
        raise FeedRefused("V4_REVISION_FENCED_EXCLUSIVE_NATIVE_EA_NOT_VERIFIED")
    if (type(e.effective_activation_revision) is not int or
            e.effective_activation_revision != revision):
        raise FeedRefused("NATIVE_ACTIVATION_REVISION_FENCE_MISMATCH")
    stamp = _utc(e.attested_at)
    if not -1 <= (now - stamp).total_seconds() <= 12:
        raise FeedRefused("NATIVE_EVIDENCE_STALE")
    if not (g.account_bound and g.worker_nonce_bound and
            g.fresh_broker_session and g.native_ea_account_match and
            g.single_writer_exclusive and g.broker_trade_allowed and
            g.terminal_trade_allowed and g.crm_entitlement_approved and
            g.customer_switch_desired and g.customer_switch_effective and
            not g.kill_switch_halted and not g.order_history_uncertain and
            g.existing_pending_orders == 0 and
            g.broker_positions_protected and g.broker_exposure_reconciled and
            e.native.broker_calc_profit_verified and
            e.native.broker_order_check_verified):
        raise FeedRefused("NATIVE_OR_PORTFOLIO_MANDATORY_PROOF_MISSING")


class ExclusiveApex11DemoWriter:
    """Source-integrated orchestration: no legacy scanner or LLM dependencies."""

    def __init__(self, *, journal: DecisionJournal, activation: ActivationStore,
                 reservations: ReservationStore, supervisor: VerifiedNativeSupervisor,
                 port: NativeEARequestPort, shared_lock: Path = PRODUCTION_SHARED_LOCK):
        self.journal=journal
        self.activation=activation
        self.reservations=reservations
        self.supervisor=supervisor
        self.port=port
        self.shared_lock=Path(shared_lock)

    def submit_one(self, *, customer_id: str, account_id: str,
                   publication_id: str, now: datetime) -> Submission:
        now=_utc(now)
        if not (isinstance(customer_id,str) and HEX32.fullmatch(customer_id) and
                isinstance(account_id,str) and HEX32.fullmatch(account_id)):
            raise FeedRefused("OWNER_OR_ACCOUNT_ID_INVALID")
        signal=_published(self.journal,publication_id,customer_id,account_id)
        closed=int(signal["bar_closed_ts"])
        if not -2 <= now.timestamp()-closed <= 600:
            raise FeedRefused("APEX_M5_DIRECTIONAL_SIGNAL_NOT_FRESH")
        with existing_native_writer_lock(self.shared_lock):
            a=self.activation.snapshot(account_id=account_id,customer_id=customer_id,now=now)
            if (a.broker!="deriv" or a.environment!="DEMO" or
                    not a.desired_on or not a.effective_on or a.kill_switch):
                raise FeedRefused("CRM_ACCOUNT_EFFECTIVE_ON_NOT_ATTESTED")
            e=self.supervisor.attest(customer_id=customer_id,account_id=account_id,observed_at=now)
            _evidence(e,customer_id=customer_id,account_id=account_id,now=now,revision=a.revision)
            if e.proposal.symbol!=signal["symbol"] or e.proposal.order_side!=signal["status"]:
                raise FeedRefused("BROKER_PROPOSAL_NOT_APEX_SIGNAL")
            reserved=reserve_apex11_demo_candidate(
                signal=signal,gate=e.gate,native=e.native,customer=e.customer,
                proposal=e.proposal,store=self.reservations,now=now)
            if not reserved.risk_reserved:
                return Submission("BLOCKED",reserved.reason)
            signal_id=reserved.signal_id
            if signal_id is None:
                raise FeedRefused("RESERVATION_ID_MISSING")
            request=DemoNativeRequest(
                customer_id=customer_id,account_id=account_id,broker="deriv",
                server="Deriv-Demo",mt5_login=e.mt5_login,worker_nonce=e.worker_nonce,
                symbol=signal["symbol"],side=signal["status"],signal_id=signal_id,
                activation_revision=a.revision,volume_lots=str(reserved.reserved_volume),
                expires_at_utc=int(now.timestamp())+12)
            # Persist UNKNOWN before any native file write; NEVER auto retry.
            self.reservations.mark_unknown(account_id,signal_id)
            try:
                if not self.supervisor.verify_unchanged(evidence=e,observed_at=now):
                    raise FeedRefused("BROKER_OR_SWITCH_CHANGED_BEFORE_NATIVE_QUEUE")
                latest=self.activation.snapshot(account_id=account_id,customer_id=customer_id,now=now)
                if latest != a or not latest.effective_on:
                    raise FeedRefused("CLIENT_SWITCH_OR_WORKER_ACK_CHANGED")
                self.port.assert_ready(request,e)
                self.port.queue_once(request,e)
            except Exception:
                return Submission("UNKNOWN","RISK_HELD_BROKER_OUTCOME_UNCERTAIN_NO_RETRY",
                                  signal_id=signal_id)
            return Submission("NATIVE_REQUEST_QUEUED",
                              "AWAITING_INDEPENDENT_BROKER_RECEIPT_AND_PROTECTION",
                              signal_id=signal_id,request_queued=True)

    def reconcile_fully_protected(self, *, customer_id: str, account_id: str,
                                  signal_id: str, reserved_lots: str,
                                  now: datetime) -> str:
        now=_utc(now)
        if not (isinstance(customer_id,str) and HEX32.fullmatch(customer_id) and
                isinstance(account_id,str) and HEX32.fullmatch(account_id) and
                isinstance(signal_id,str) and _HEX64.fullmatch(signal_id)):
            raise FeedRefused("INVALID_RECONCILIATION_IDENTITY")
        with existing_native_writer_lock(self.shared_lock):
            # Authoritative owner binding applies even after the client turns
            # OFF. Never accept a caller-provided volume to release someone
            # else's risk or an unrelated older broker position.
            account=self.activation.snapshot(
                account_id=account_id,customer_id=customer_id,now=now)
            if account.broker!="deriv" or account.environment!="DEMO":
                raise FeedRefused("RECONCILE_DEMO_ACCOUNT_BINDING_INVALID")
            expected_lots=self.reservations.require_pending_volume(
                customer_id=customer_id,account_id=account_id,signal_id=signal_id)
            if D(reserved_lots)!=expected_lots:
                raise FeedRefused("RECEIPT_RESERVED_LOTS_NOT_MATCHED")
            receipt,position,included=self.supervisor.authenticated_receipt_and_position(
                account_id=account_id,signal_id=signal_id,observed_at=now)
            if (receipt.account_id!=account_id or receipt.environment!="DEMO" or
                    receipt.broker!="deriv" or receipt.signal_id!=signal_id or
                    included is not True):
                raise FeedRefused("AUTHENTICATED_BROKER_EXPOSURE_NOT_RECONCILED")
            if (position.broker_snapshot_time.tzinfo is None or
                    position.broker_snapshot_time.utcoffset() is None or
                    not -2 <= (now-position.broker_snapshot_time).total_seconds() <= 20):
                raise FeedRefused("BROKER_PROTECTED_POSITION_SNAPSHOT_STALE")
            return finalize_fully_reconciled_demo_receipt(
                store=self.reservations,receipt=receipt,position=position,
                reserved_lots=expected_lots,trusted_native_worker_verified=True)
