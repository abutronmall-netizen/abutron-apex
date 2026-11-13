"""Crash-safe Deriv 6207 DEMO native client-OFF dispatch lease.

This is the SERIALIZED admission ledger, not a complete production CRM/MT5
integration.  Root-owned service must supply a real independent MT5/CRM
attestor and read-only broker reconciliation verifier; there are no bool
shortcuts, no LIVE mode, no background sweeper that clears UNKNOWN.
The existing ActivationStore.request OFF transition uses BEGIN IMMEDIATE
on the SAME SQLite file: it cannot race a claim / transition to SENDING.
OFF requested *after* a send grant MUST be reported STOPPING until independently
broker-reconciled; the UI must NOT report OFF_SETTLED prematurely.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
import secrets
import sqlite3
from typing import Protocol

from .production_contracts import FeedRefused
from .transactional_activation import ActivationStore
from risk_guard.reservation_store import ReservationStore

_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SYMBOLS = frozenset({
    "Volatility 10 Index.0", "Volatility 25 Index.0",
    "Volatility 50 Index.0", "Volatility 75 Index.0",
    "Volatility 100 Index.0",
})


def _now(now: datetime) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise FeedRefused("NATIVE_FENCE_UTC_REQUIRED")
    return now.astimezone(timezone.utc)


def _dec(v: str) -> Decimal:
    try:
        if not isinstance(v, str) or len(v) > 32:
            raise ValueError
        value=Decimal(v)
    except (InvalidOperation, ValueError):
        raise FeedRefused("NATIVE_FENCE_DECIMAL_INVALID") from None
    if not value.is_finite() or value <= 0:
        raise FeedRefused("NATIVE_FENCE_DECIMAL_INVALID")
    return value


@dataclass(frozen=True)
class NativeOrderIdentity:
    customer_id: str
    account_id: str
    signal_id: str
    worker_nonce: str
    login: str
    broker: str
    server: str
    environment: str
    symbol: str
    side: str
    volume: str
    sl: str
    tp: str
    revision: int
    expires_utc: int

    def canonical_digest(self) -> str:
        return sha256(json.dumps(self.__dict__, sort_keys=True,
                                  separators=(",",":")).encode()).hexdigest()

    def validate(self, now: datetime) -> None:
        if (not all(type(x) is str and _ID.fullmatch(x)
                    for x in (self.customer_id,self.account_id,self.worker_nonce))
            or type(self.signal_id) is not str or not _SHA.fullmatch(self.signal_id)
            or type(self.login) is not str or not self.login.isascii()
            or not self.login.isdecimal() or not self.login.endswith("6207")
            or self.broker != "deriv" or self.server != "Deriv-Demo"
            or self.environment != "DEMO" or self.symbol not in _SYMBOLS
            or self.side not in ("BUY","SELL")
            or type(self.revision) is not int or self.revision < 1
            or type(self.expires_utc) is not int
            or not int(now.timestamp()) < self.expires_utc <= int(now.timestamp()) + 15):
            raise FeedRefused("NATIVE_FENCE_DEMO_6207_IDENTITY_OR_EXPIRY")
        _dec(self.volume); _dec(self.sl); _dec(self.tp)


class NativeBrokerAuthority(Protocol):
    """Must perform fresh independent authenticated MT5+CRM+risk checks.

    Never instantiate this from a client HTTP payload or a user-supplied
    boolean; it belongs in the root-only execution service, with tightly
    restricted privileges and real broker/session validation.
    """
    def assert_eligible(self, *, identity: NativeOrderIdentity,
                        phase: str, now: datetime) -> None: ...
    def assert_broker_result(self, *, identity: NativeOrderIdentity,
                             outcome: str, proof_ref: str, now: datetime) -> None: ...


@dataclass(frozen=True)
class NativeLease:
    lease_id: str
    identity_digest: str
    state: str
    expires_utc: int


class NativeV4OffFence:
    """Shared SQLite transaction barrier for native CLAIM/SEND and portal OFF.

    A CLAIM is not permission to send. SEND is granted only after fresh second
    trusted checks and transitions to SENDING in the same ledger the portal
    uses to commit OFF. A grant made *before* OFF is unresolved until broker
    proof; the portal must show STOPPING, not OFF_SETTLED, during that time.
    """

    def __init__(self, *, activation: ActivationStore,
                 reservations: ReservationStore,
                 authority: NativeBrokerAuthority):
        if authority is None or not callable(getattr(authority, "assert_eligible", None)) or (
            not callable(getattr(authority, "assert_broker_result", None))
        ):
            raise TypeError("ROOT_OWNED_NATIVE_BROKER_AUTHORITY_REQUIRED")
        self.activation=activation
        self.reservations=reservations
        self.authority=authority
        with self.activation._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS native_v4_leases (
                  lease_id TEXT PRIMARY KEY,
                  account_id TEXT NOT NULL,
                  customer_id TEXT NOT NULL,
                  signal_id TEXT NOT NULL,
                  payload_digest TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  expires_utc INTEGER NOT NULL,
                  state TEXT NOT NULL CHECK(state IN ('CLAIMED','SENDING','RESOLVED')),
                  claimed_at TEXT NOT NULL,
                  send_at TEXT,
                  resolved_at TEXT,
                  outcome TEXT,
                  proof_ref TEXT,
                  UNIQUE(account_id,signal_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS native_v4_one_unresolved_account
                ON native_v4_leases(account_id)
                WHERE state IN ('CLAIMED','SENDING');
            """)

    def _activation_on(self, db: sqlite3.Connection, *, i: NativeOrderIdentity,
                       now: datetime) -> None:
        raw=self.activation._read(db,i.account_id,i.customer_id)
        a=self.activation._activation(raw,now)
        if (a.broker != "deriv" or a.environment != "DEMO" or
            a.revision != i.revision or not a.desired_on or
            not a.effective_on or a.kill_switch or
            a.ack_revision != i.revision):
            raise FeedRefused("NATIVE_FENCE_ACCOUNT_OFF_OR_STALE_REVISION")

    def _pending_exact_volume(self, i: NativeOrderIdentity) -> None:
        reserved=self.reservations.require_pending_volume(
            customer_id=i.customer_id,account_id=i.account_id,signal_id=i.signal_id)
        if reserved != _dec(i.volume):
            raise FeedRefused("NATIVE_FENCE_RISK_RESERVATION_VOLUME_MISMATCH")

    def claim(self, *, identity: NativeOrderIdentity, now: datetime) -> NativeLease:
        now=_now(now); identity.validate(now)
        with self.activation._db() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                self._activation_on(db,i=identity,now=now)
                self._pending_exact_volume(identity)
                self.authority.assert_eligible(identity=identity,phase="CLAIM",now=now)
                key=secrets.token_hex(32)
                db.execute("""INSERT INTO native_v4_leases
                    (lease_id,account_id,customer_id,signal_id,payload_digest,
                     revision,expires_utc,state,claimed_at)
                    VALUES (?,?,?,?,?,?,?,'CLAIMED',?)""",
                    (key,identity.account_id,identity.customer_id,identity.signal_id,
                     identity.canonical_digest(),identity.revision,
                     identity.expires_utc,now.isoformat()))
                db.execute("COMMIT")
                return NativeLease(key,identity.canonical_digest(),"CLAIMED",identity.expires_utc)
            except Exception:
                db.execute("ROLLBACK")
                raise

    def send(self, *, identity: NativeOrderIdentity, lease_id: str,
             now: datetime) -> NativeLease:
        now=_now(now); identity.validate(now)
        if type(lease_id) is not str or not _SHA.fullmatch(lease_id):
            raise FeedRefused("NATIVE_FENCE_LEASE_ID_INVALID")
        with self.activation._db() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row=db.execute("""SELECT account_id,customer_id,payload_digest,revision,
                       expires_utc,state FROM native_v4_leases WHERE lease_id=?""",
                       (lease_id,)).fetchone()
                if (row is None or row["account_id"] != identity.account_id or
                    row["customer_id"] != identity.customer_id or
                    row["payload_digest"] != identity.canonical_digest() or
                    row["revision"] != identity.revision or
                    row["expires_utc"] != identity.expires_utc or
                    row["state"] != "CLAIMED"):
                    raise FeedRefused("NATIVE_FENCE_CLAIM_MISMATCH_OR_REPLAY")
                self._activation_on(db,i=identity,now=now)
                self._pending_exact_volume(identity)
                self.authority.assert_eligible(identity=identity,phase="SEND",now=now)
                db.execute("""UPDATE native_v4_leases SET state='SENDING',
                           send_at=? WHERE lease_id=? AND state='CLAIMED'""",
                           (now.isoformat(),lease_id))
                db.execute("COMMIT")
                return NativeLease(lease_id,row["payload_digest"],"SENDING",row["expires_utc"])
            except Exception:
                db.execute("ROLLBACK")
                raise

    def off_state(self, *, customer_id: str, account_id: str,
                  now: datetime) -> str:
        now=_now(now)
        with self.activation._db() as db:
            row=self.activation._read(db,account_id,customer_id)
            a=self.activation._activation(row,now)
            if a.desired_on:
                return "ON" if a.effective_on else "NOT_EFFECTIVE"
            count=db.execute("""SELECT COUNT(*) FROM native_v4_leases
                WHERE account_id=? AND customer_id=?
                AND state IN ('CLAIMED','SENDING')""",
                (account_id,customer_id)).fetchone()[0]
            return "STOPPING_BROKER_RECONCILIATION_REQUIRED" if count else "OFF_SETTLED"

    def reconcile(self, *, identity: NativeOrderIdentity, lease_id: str,
                  outcome: str, proof_ref: str, now: datetime) -> None:
        """Only independently authenticated broker proof clears a lease.

        Timeout, connection failure, STOP request and heartbeat expiry do
        not clear it. Never turn an UNKNOWN into a second send.
        """
        now=_now(now)
        if outcome not in ("PROTECTED_POSITION", "BROKER_REJECTED_NO_ORDER"):
            raise FeedRefused("NATIVE_FENCE_VERIFIED_OUTCOME_REQUIRED")
        if (type(proof_ref) is not str or len(proof_ref) < 10 or
                len(proof_ref) > 256 or type(lease_id) is not str):
            raise FeedRefused("NATIVE_FENCE_VERIFIABLE_PROOF_REQUIRED")
        with self.activation._db() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row=db.execute("""SELECT * FROM native_v4_leases WHERE lease_id=?""",
                               (lease_id,)).fetchone()
                if row is None or row["account_id"] != identity.account_id or (
                    row["customer_id"] != identity.customer_id or
                    row["signal_id"] != identity.signal_id or
                    row["payload_digest"] != identity.canonical_digest() or
                    row["state"] not in ("CLAIMED","SENDING")
                ):
                    raise FeedRefused("NATIVE_FENCE_RECONCILE_IDENTITY_OR_STATE")
                self.authority.assert_broker_result(
                    identity=identity,outcome=outcome,proof_ref=proof_ref,now=now)
                try:
                    self.reservations.require_finalized_broker_proof(
                        customer_id=identity.customer_id,account_id=identity.account_id,
                        signal_id=identity.signal_id,outcome=outcome,proof_ref=proof_ref)
                except (ValueError, PermissionError) as exc:
                    raise FeedRefused("NATIVE_FENCE_FINALIZED_RISK_PROOF_REQUIRED") from exc
                db.execute("""UPDATE native_v4_leases SET state='RESOLVED',
                    resolved_at=?, outcome=?, proof_ref=? WHERE lease_id=?""",
                    (now.isoformat(),outcome,proof_ref,lease_id))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
