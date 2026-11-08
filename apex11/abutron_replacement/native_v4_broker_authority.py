"""Bind native OFF lease to the EXISTING independently trusted broker supervisor.

Do not instantiate with mock facts in production. The supplied supervisor must
authenticate Deriv MT5 broker session, live CRM owner/entitlements, native
EA identity/nonce/lock, customer-wide durable equity/exposure and risk status.
This adapter does not dial broker APIs itself; it **cannot** be used without
a real trusted supervisor and protected credentials. LIVE unsupported.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hmac

from .exclusive_native_writer import VerifiedNativeSupervisor, _evidence
from .native_v4_off_fence import NativeOrderIdentity, _dec
from .native_receipt_guard import verify_demo_broker_position
from .production_contracts import FeedRefused
from .transactional_activation import ActivationStore
from risk_guard.reservation_store import ReservationStore


class Verified6207NativeAuthority:
    """Strict bridge: attestation + original risk ledger + broker native proof."""

    def __init__(self, *, supervisor: VerifiedNativeSupervisor,
                 activation: ActivationStore, reservations: ReservationStore):
        if (supervisor is None or
                not callable(getattr(supervisor, "attest", None)) or
                not callable(getattr(supervisor, "verify_unchanged", None)) or
                not callable(getattr(supervisor, "authenticated_receipt_and_position", None))):
            raise TypeError("REAL_NATIVE_SUPERVISOR_ADAPTER_REQUIRED")
        self.supervisor=supervisor
        self.activation=activation
        self.reservations=reservations

    def attest_session(self, *, customer_id: str, account_id: str,
                       worker_nonce: str, mt5_login: str, now: datetime) -> int:
        """Read-only active V4 EA/CRM session proof for native capability.

        The status heartbeat is NOT execution authorization. It must be
        independently matched to a truly attached V4 EA and checked again
        for exact proposal+reservation before CLAIM/SEND.
        """
        a=self.activation.snapshot(account_id=account_id,
                                   customer_id=customer_id,now=now)
        if (a.broker!="deriv" or a.environment!="DEMO" or not a.desired_on or
                not a.effective_on or a.kill_switch):
            raise FeedRefused("NATIVE_SESSION_ACCOUNT_NOT_EFFECTIVE")
        e=self.supervisor.attest(customer_id=customer_id,
                    account_id=account_id,observed_at=now)
        _evidence(e,customer_id=customer_id,account_id=account_id,
                  now=now,revision=a.revision)
        if (e.mt5_login!=mt5_login or e.worker_nonce!=worker_nonce or
                not self.supervisor.verify_unchanged(evidence=e,observed_at=now)):
            raise FeedRefused("NATIVE_SESSION_WORKER_MISMATCH")
        return a.revision

    def assert_eligible(self, *, identity: NativeOrderIdentity,
                        phase: str, now: datetime) -> None:
        if phase not in ("CLAIM","SEND"):
            raise FeedRefused("NATIVE_AUTHORITY_UNSUPPORTED_PHASE")
        identity.validate(now)
        a=self.activation.snapshot(account_id=identity.account_id,
                                   customer_id=identity.customer_id,now=now)
        if (not a.desired_on or not a.effective_on or a.kill_switch or
                a.revision!=identity.revision):
            raise FeedRefused("NATIVE_AUTHORITY_CLIENT_OFF_OR_REVISED")
        e=self.supervisor.attest(customer_id=identity.customer_id,
                    account_id=identity.account_id,observed_at=now)
        _evidence(e,customer_id=identity.customer_id,
                  account_id=identity.account_id,now=now,
                  revision=identity.revision)
        if (e.mt5_login!=identity.login or e.worker_nonce!=identity.worker_nonce
                or e.proposal.signal_id!=identity.signal_id or
                e.proposal.symbol!=identity.symbol or
                e.proposal.order_side!=identity.side or
                e.native.stop_price is None or e.native.take_price is None):
            raise FeedRefused("NATIVE_AUTHORITY_BROKER_ORDER_IDENTITY_MISMATCH")
        if (_dec(str(e.native.stop_price))!=_dec(identity.sl) or
                _dec(str(e.native.take_price))!=_dec(identity.tp)):
            raise FeedRefused("NATIVE_AUTHORITY_STOP_GEOMETRY_CHANGED")
        volume=self.reservations.require_pending_volume(
            customer_id=identity.customer_id,account_id=identity.account_id,
            signal_id=identity.signal_id)
        if volume!=_dec(identity.volume):
            raise FeedRefused("NATIVE_AUTHORITY_RESERVED_VOLUME_CHANGED")
        if not self.supervisor.verify_unchanged(evidence=e,observed_at=now):
            raise FeedRefused("NATIVE_AUTHORITY_BROKER_OR_CRM_REVISED")

    def assert_broker_result(self, *, identity: NativeOrderIdentity,
                             outcome: str, proof_ref: str, now: datetime) -> None:
        # An absent/rejected order requires an *independent authenticated
        # complete broker-history search*; existing supervisor interface
        # does not provide it. Leave claim unresolved until it does.
        if outcome!="PROTECTED_POSITION":
            raise FeedRefused("NATIVE_AUTHORITY_NO_ORDER_NOT_YET_CERTIFIED")
        receipt,position,included=self.supervisor.authenticated_receipt_and_position(
            account_id=identity.account_id,
            signal_id=identity.signal_id,observed_at=now)
        if (included is not True or receipt.broker!="deriv" or
            receipt.environment!="DEMO" or receipt.server!="Deriv-Demo" or
            receipt.account_id!=identity.account_id or
            position.account_id!=identity.account_id or
            receipt.signal_id!=identity.signal_id or
            receipt.symbol!=identity.symbol or receipt.side!=identity.side):
            raise FeedRefused("NATIVE_AUTHORITY_BROKER_RECEIPT_IDENTITY_MISMATCH")
        if (position.broker_snapshot_time.tzinfo is None or
                position.broker_snapshot_time.utcoffset() is None or
                not -2 <= (now-position.broker_snapshot_time).total_seconds() <= 20):
            raise FeedRefused("NATIVE_AUTHORITY_BROKER_SNAPSHOT_NOT_FRESH")
        reserved=self.reservations.require_pending_volume(
            customer_id=identity.customer_id,account_id=identity.account_id,
            signal_id=identity.signal_id)
        native_proof=verify_demo_broker_position(
            receipt=receipt,position=position,
            expected_account_id=identity.account_id,
            expected_signal_id=identity.signal_id,
            expected_symbol=identity.symbol,expected_side=identity.side,
            reserved_lots=reserved,trusted_native_worker_verified=True)
        if not hmac.compare_digest(native_proof,proof_ref):
            raise FeedRefused("NATIVE_AUTHORITY_BROKER_PROOF_MISMATCH")
        # The exact protected native broker snapshot has already been
        # included in customer risk inventory; ONLY THEN finalize.
        self.reservations.complete(
            identity.account_id,identity.signal_id,
            outcome="RECONCILED",broker_proof=native_proof,
            now=position.broker_snapshot_time,
            reconciled_snapshot_includes_position=True)
