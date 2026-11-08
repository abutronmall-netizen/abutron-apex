"""Single-host SQLite reservation boundary; not a substitute for native MT5 writer locks.

One DB shared by all account writers belonging to a customer. BEGIN IMMEDIATE
serializes competing reservations. Broker receipt reconciliation is mandatory.
"""
from __future__ import annotations
import hashlib
from contextlib import contextmanager
import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

try:
    from .abutron_risk_guard import CustomerRisk, Proposal, RiskPolicy, Decision, D, evaluate
except ImportError:  # standalone Python use from within risk_guard/
    from abutron_risk_guard import CustomerRisk, Proposal, RiskPolicy, Decision, D, evaluate


def _signal_key(account_id: str, signal_id: str) -> str:
    """Signal identifiers are unique PER ACCOUNT, not across every customer's account."""
    return hashlib.sha256(json.dumps([account_id, signal_id], separators=(",", ":")).encode()).hexdigest()


def _intent_hash(order: Proposal) -> str:
    data = asdict(order)
    canonical = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class ReservationStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        # Runtime must own a locked-down directory; newly created ledger is mode 0600.
        if not Path(self.path).exists():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        with self._db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS intents (
                signal_key TEXT PRIMARY KEY, intent_sha TEXT NOT NULL,
                customer_id TEXT NOT NULL, account_id TEXT NOT NULL,
                risk_usd TEXT NOT NULL, risk_account_ccy TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('RESERVED','UNKNOWN','RECONCILED','REJECTED')),
                volume TEXT NOT NULL, created_at TEXT NOT NULL,
                completed_at TEXT, broker_proof_ref TEXT
              );
              CREATE INDEX IF NOT EXISTS idx_active_customer ON intents(customer_id, state);
              CREATE TABLE IF NOT EXISTS risk_locks (
                scope TEXT NOT NULL CHECK(scope IN ('CUSTOMER','ACCOUNT')),
                scope_id TEXT NOT NULL,
                lock_type TEXT NOT NULL CHECK(lock_type IN ('DAILY_LOSS','MAX_DRAWDOWN')),
                reason TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(scope, scope_id, lock_type)
              );
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    def reserve(self, customer: CustomerRisk, proposal: Proposal, *, now: datetime,
                policy: RiskPolicy = RiskPolicy()) -> Decision:
        # Never turn a repeated signal into a second order or a new budget claim.
        if not proposal.signal_id or not proposal.account_id or not proposal.customer_id:
            return Decision(False, "INVALID_RESERVATION_IDENTITY")
        intent_sha = _intent_hash(proposal)
        key = _signal_key(proposal.account_id, proposal.signal_id)
        with self._db() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute("SELECT intent_sha, state FROM intents WHERE signal_key=?",
                                      (key,)).fetchone()
                if previous:
                    db.execute("ROLLBACK")
                    reason = "SIGNAL_ALREADY_RESERVED_OR_PROCESSED" if previous[0] == intent_sha else "SIGNAL_ID_COLLISION"
                    return Decision(False, reason)
                locked = db.execute("SELECT lock_type FROM risk_locks "
                    "WHERE (scope='CUSTOMER' AND scope_id=?) OR (scope='ACCOUNT' AND scope_id=?)",
                    (customer.customer_id, proposal.account_id)).fetchall()
                if locked:
                    db.execute("ROLLBACK")
                    return Decision(False, "PERSISTENT_" + locked[0][0] + "_LOCK")
                active = db.execute("SELECT account_id, risk_usd, risk_account_ccy FROM intents "
                    "WHERE customer_id=? AND state IN ('RESERVED','UNKNOWN')", (customer.customer_id,)).fetchall()
                customer_pending = sum((D(x[1]) for x in active), D("0"))
                account_pending = sum((D(x[2]) for x in active if x[0] == proposal.account_id), D("0"))
                result = evaluate(customer, proposal, now=now, policy=policy,
                                  pending_customer_risk_usd=customer_pending,
                                  pending_account_risk_ccy=account_pending)
                if not result.allowed:
                    if result.latch_daily_loss or result.latch_drawdown:
                        scope = "CUSTOMER" if result.reason.startswith("CUSTOMER_") else "ACCOUNT"
                        scope_id = customer.customer_id if scope == "CUSTOMER" else proposal.account_id
                        lock_type = "DAILY_LOSS" if result.latch_daily_loss else "MAX_DRAWDOWN"
                        db.execute("INSERT OR IGNORE INTO risk_locks "
                            "(scope,scope_id,lock_type,reason,created_at) VALUES(?,?,?,?,?)",
                            (scope, scope_id, lock_type, result.reason, now.isoformat()))
                        db.execute("COMMIT")
                    else:
                        db.execute("ROLLBACK")
                    return result
                db.execute("INSERT INTO intents(signal_key, intent_sha, customer_id, account_id, "
                    "risk_usd, risk_account_ccy, state, volume, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (key, intent_sha, customer.customer_id, proposal.account_id,
                     str(result.reserved_risk_usd), str(result.max_loss_ccy), "RESERVED",
                     str(result.volume), now.isoformat()))
                db.execute("COMMIT")
                return result
            except Exception:
                try:
                    db.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise

    def observe(self, customer: CustomerRisk, *, now: datetime,
                policy: RiskPolicy = RiskPolicy()) -> tuple[str, ...]:
        """Persist threshold crossings even if no trading signal or account is OFF.

        Caller runs this on each fresh broker-equity update. It MUST separately
        persist UTC-day baselines and adjusted high-water marks before calling.
        """
        if now.tzinfo is None or not customer.account_inventory_complete or not customer.exposure_complete:
            raise ValueError("No authoritative timestamp or complete customer inventory")
        if not customer.accounts or any(a.customer_id != customer.customer_id for a in customer.accounts):
            raise ValueError("Invalid customer account inventory")
        if len(set(a.account_id for a in customer.accounts)) != len(customer.accounts):
            raise ValueError("Duplicate account in inventory")
        if D(customer.day_start_equity_usd) <= 0 or D(customer.peak_equity_usd) <= 0:
            raise ValueError("No durable customer baseline")
        for a in customer.accounts:
            if (a.broker_asof is None or a.broker_asof.tzinfo is None or
                (now - a.broker_asof).total_seconds() < -1 or
                (now - a.broker_asof).total_seconds() > policy.freshness_seconds or
                any(D(v) <= 0 for v in (a.equity_ccy, a.usd_per_ccy,
                       a.day_start_equity_ccy, a.peak_equity_ccy))):
                raise ValueError("Stale or invalid broker equity evidence")
        crossed = []
        for a in customer.accounts:
            if D(a.equity_ccy) <= D(a.day_start_equity_ccy) * (1 - policy.daily_loss):
                crossed.append(("ACCOUNT", a.account_id, "DAILY_LOSS", "ACCOUNT_DAILY_LOSS_THRESHOLD"))
            if D(a.equity_ccy) <= D(a.peak_equity_ccy) * (1 - policy.peak_drawdown):
                crossed.append(("ACCOUNT", a.account_id, "MAX_DRAWDOWN", "ACCOUNT_MAX_DRAWDOWN_THRESHOLD"))
        current = sum((D(a.equity_ccy) * D(a.usd_per_ccy) for a in customer.accounts), D("0"))
        if current <= D(customer.day_start_equity_usd) * (1 - policy.daily_loss):
            crossed.append(("CUSTOMER", customer.customer_id, "DAILY_LOSS", "CUSTOMER_DAILY_LOSS_THRESHOLD"))
        if current <= D(customer.peak_equity_usd) * (1 - policy.peak_drawdown):
            crossed.append(("CUSTOMER", customer.customer_id, "MAX_DRAWDOWN", "CUSTOMER_MAX_DRAWDOWN_THRESHOLD"))
        if not crossed:
            return ()
        with self._db() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                for scope, scope_id, lock_type, reason in crossed:
                    db.execute("INSERT OR IGNORE INTO risk_locks "
                        "(scope, scope_id, lock_type, reason, created_at) VALUES(?,?,?,?,?)",
                        (scope, scope_id, lock_type, reason, now.isoformat()))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return tuple(x[3] for x in crossed)

    def require_pending_volume(self, *, customer_id: str, account_id: str,
                               signal_id: str):
        """Read the immutable reserved volume before broker reconciliation.

        This is owner-bound. A caller-supplied volume or native receipt cannot
        substitute for the original customer-risk reservation. Account OFF must
        never prevent reconciliations needed to clear an UNKNOWN order.
        """
        if not customer_id or not account_id or not signal_id:
            raise ValueError("INVALID_PENDING_RESERVATION_IDENTITY")
        with self._db() as db:
            row = db.execute(
                "SELECT customer_id, state, volume FROM intents WHERE signal_key=?",
                (_signal_key(account_id, signal_id),)
            ).fetchone()
        if row is None or row[0] != customer_id:
            raise PermissionError("NO_OWNED_PENDING_RISK_RESERVATION")
        if row[1] not in ("RESERVED", "UNKNOWN"):
            raise ValueError("RISK_RESERVATION_ALREADY_FINALIZED")
        volume = D(row[2])
        if volume <= 0:
            raise ValueError("INVALID_PERSISTED_RESERVED_VOLUME")
        return volume

    def require_finalized_broker_proof(self, *, customer_id: str,
                                      account_id: str, signal_id: str,
                                      outcome: str, proof_ref: str) -> None:
        """Finalized risk ledger must match the independently proven broker outcome.

        An ACK alone is not reconciliation. An OFF transition may only be
        considered settled when the authenticated broker history and the
        protected position (or verified no-order) are represented in the
        original customer-owned risk ledger.
        """
        expected = {"PROTECTED_POSITION": "RECONCILED",
                    "BROKER_REJECTED_NO_ORDER": "REJECTED"}.get(outcome)
        if expected is None or not proof_ref:
            raise ValueError("NATIVE_FENCE_FINALIZED_RISK_PROOF_REQUIRED")
        with self._db() as db:
            row = db.execute(
                "SELECT customer_id, account_id, state, broker_proof_ref "
                "FROM intents WHERE signal_key=?",
                (_signal_key(account_id, signal_id),)
            ).fetchone()
        if row is None or row[0] != customer_id or row[1] != account_id:
            raise PermissionError("NATIVE_FENCE_FINALIZED_RISK_OWNER_MISMATCH")
        if row[2] != expected or row[3] != proof_ref:
            raise ValueError("NATIVE_FENCE_FINALIZED_RISK_PROOF_REQUIRED")

    def mark_unknown(self, account_id: str, signal_id: str):
        """For timeout, crash or missing receipt. Risk stays reserved."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE intents SET state='UNKNOWN' WHERE signal_key=? AND state='RESERVED'", (_signal_key(account_id, signal_id),))
            db.execute("COMMIT")

    def complete(self, account_id: str, signal_id: str, *, outcome: str, broker_proof: str, now: datetime,
                 reconciled_snapshot_includes_position: bool = False):
        """Release only after authoritative broker rejection or reconciled position.

        Caller must independently verify broker_proof against authenticated MT5
        history. This module cannot validate a receipt without MT5 access.
        """
        if outcome == "RECONCILED" and not reconciled_snapshot_includes_position:
            raise ValueError("Do not release reservation before broker position is in exposure snapshot")
        if outcome not in ("RECONCILED", "REJECTED") or not broker_proof.strip():
            raise ValueError("Verified terminal result and broker proof required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM intents WHERE signal_key=?", (_signal_key(account_id, signal_id),)).fetchone()
            if not row or row[0] not in ("RESERVED", "UNKNOWN"):
                db.execute("ROLLBACK")
                raise ValueError("Reservation unavailable or already finalized")
            db.execute("UPDATE intents SET state=?, completed_at=?, broker_proof_ref=? WHERE signal_key=?",
                (outcome, now.isoformat(), broker_proof, _signal_key(account_id, signal_id)))
            db.execute("COMMIT")
