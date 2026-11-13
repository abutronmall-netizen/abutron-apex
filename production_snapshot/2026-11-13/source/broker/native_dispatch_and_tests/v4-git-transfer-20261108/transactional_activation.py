"""Isolated DEMO-only transactional account ON/OFF authority for ABUTRON APEX 1.1.

No broker orders, actual MT5 connection, CRM authentication, or production migration.
Trusted calling services MUST authenticate customer ownership and independently
validate the broker session, writer lock and entitlement claims they provide.
The DB must be on a locally durable encrypted volume with restrictive access.
"""
from __future__ import annotations

import sqlite3
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Activation:
    account_id: str
    customer_id: str
    broker: str
    environment: str
    revision: int
    desired_on: bool
    effective_on: bool
    entitlement_ok: bool
    connected: bool
    writer_verified: bool
    kill_switch: bool
    ack_revision: int | None
    ack_valid_until: datetime | None


class ActivationStore:
    """Serialized activation transactions; account OFF and revision changes revoke entry.

    Every account owns its revision. An old worker ACK cannot reactivate a newer
    OFF state. Effective ON is never inferred from a desired ON without matching
    broker/entitlement/writer acknowledgments. LIVE is excluded by construction.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        try:
            fd = os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        if os.stat(self.db_path).st_mode & 0o077:
            raise PermissionError('ACTIVATION_LEDGER_PERMISSIONS_TOO_OPEN')
        with self._db() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS account_activation (
                account_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                broker TEXT NOT NULL CHECK(broker IN ('deriv','fp_markets')),
                environment TEXT NOT NULL CHECK(environment='DEMO'),
                revision INTEGER NOT NULL CHECK(revision>=1),
                desired_on INTEGER NOT NULL DEFAULT 0,
                effective_on INTEGER NOT NULL DEFAULT 0,
                entitlement_ok INTEGER NOT NULL DEFAULT 0,
                connected INTEGER NOT NULL DEFAULT 0,
                writer_verified INTEGER NOT NULL DEFAULT 0,
                kill_switch INTEGER NOT NULL DEFAULT 1,
                ack_revision INTEGER,
                ack_valid_until TEXT,
                updated_at TEXT NOT NULL)''')

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=10000')
        con.execute('PRAGMA synchronous=FULL')
        try:
            yield con
        finally:
            con.close()

    @staticmethod
    def _utc(now: datetime) -> str:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('timezone-aware timestamp required')
        return now.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _read(con: sqlite3.Connection, account_id: str, customer_id: str) -> sqlite3.Row:
        row = con.execute('SELECT * FROM account_activation WHERE account_id=? AND customer_id=?',
                          (account_id, customer_id)).fetchone()
        if row is None:
            raise PermissionError('ACCOUNT_NOT_FOUND_OR_OWNED')
        return row

    @staticmethod
    def _activation(row: sqlite3.Row, now: datetime) -> Activation:
        expiry = datetime.fromisoformat(row['ack_valid_until']) if row['ack_valid_until'] else None
        lease_ok = expiry is not None and now.astimezone(timezone.utc) < expiry
        currently_effective = (bool(row['effective_on']) and row['ack_revision'] == row['revision'] and
            bool(row['desired_on']) and bool(row['entitlement_ok']) and bool(row['connected']) and
            bool(row['writer_verified']) and not bool(row['kill_switch']) and lease_ok)
        return Activation(
            row['account_id'],row['customer_id'],row['broker'],row['environment'],row['revision'],
            bool(row['desired_on']),currently_effective,bool(row['entitlement_ok']),
            bool(row['connected']),bool(row['writer_verified']),bool(row['kill_switch']),row['ack_revision'],expiry)

    def provision(self, *, account_id: str, customer_id: str, broker: str, now: datetime) -> Activation:
        stamp = self._utc(now)
        if not account_id or not customer_id or broker not in ('deriv','fp_markets'):
            raise ValueError('invalid DEMO account identity')
        with self._db() as con:
            try:
                con.execute('BEGIN IMMEDIATE')
                con.execute('''INSERT OR IGNORE INTO account_activation
                  (account_id,customer_id,broker,environment,revision,updated_at)
                  VALUES (?, ?, ?, 'DEMO', 1, ?)''', (account_id,customer_id,broker,stamp))
                row = self._read(con,account_id,customer_id)
                if row['broker'] != broker or row['environment'] != 'DEMO':
                    raise PermissionError('CROSS_BROKER_OR_ENVIRONMENT_MISMATCH')
                con.execute('COMMIT')
                return self._activation(row, now)
            except Exception:
                con.execute('ROLLBACK')
                raise

    def snapshot(self, *, account_id: str, customer_id: str, now: datetime) -> Activation:
        self._utc(now)
        with self._db() as con:
            return self._activation(self._read(con,account_id,customer_id), now)

    def request(self, *, account_id: str, customer_id: str, desired_on: bool,
                expected_revision: int, now: datetime) -> Activation:
        """Authenticated portal requests ON/OFF with optimistic concurrency control.

        The owner account cannot be changed by a request. Desired OFF revokes
        effective ON in the same transaction, even if a previous ACK arrives late.
        """
        stamp = self._utc(now)
        if type(desired_on) is not bool:
            raise ValueError('desired_on must be bool')
        with self._db() as con:
            try:
                con.execute('BEGIN IMMEDIATE')
                row = self._read(con,account_id,customer_id)
                if row['revision'] != expected_revision:
                    raise ValueError('STALE_ACTIVATION_REVISION')
                con.execute('''UPDATE account_activation
                    SET revision=revision+1, desired_on=?, effective_on=0,
                        ack_revision=NULL, ack_valid_until=NULL, updated_at=? WHERE account_id=?''',
                    (int(desired_on),stamp,account_id))
                out=self._activation(self._read(con,account_id,customer_id), now)
                con.execute('COMMIT')
                return out
            except Exception:
                con.execute('ROLLBACK')
                raise

    def update_attestation(self, *, account_id: str, customer_id: str,
                           expected_revision: int, entitlement_ok: bool,
                           connected: bool, writer_verified: bool,
                           kill_switch: bool, now: datetime) -> Activation:
        """Trusted supervisor refresh: any change fences older ACKs.

        Inputs are assertions, not evidence. Actual CRM, MT5 and lease
        verification MUST happen outside this module before calling it.
        """
        stamp=self._utc(now)
        flags=(entitlement_ok,connected,writer_verified,kill_switch)
        if any(type(x) is not bool for x in flags):
            raise ValueError('attestations must be boolean')
        with self._db() as con:
            try:
                con.execute('BEGIN IMMEDIATE')
                row=self._read(con,account_id,customer_id)
                if row['revision'] != expected_revision:
                    raise ValueError('STALE_ACTIVATION_REVISION')
                if tuple(bool(row[k]) for k in ('entitlement_ok','connected','writer_verified','kill_switch')) == flags:
                    con.execute('COMMIT')
                    return self._activation(row, now)
                con.execute('''UPDATE account_activation SET
                    revision=revision+1, entitlement_ok=?,connected=?,writer_verified=?,
                    kill_switch=?,effective_on=0,ack_revision=NULL,ack_valid_until=NULL,updated_at=?
                    WHERE account_id=?''',
                    (*(int(v) for v in flags),stamp,account_id))
                out=self._activation(self._read(con,account_id,customer_id), now)
                con.execute('COMMIT')
                return out
            except Exception:
                con.execute('ROLLBACK')
                raise

    def acknowledge(self, *, account_id: str, customer_id: str,
                    expected_revision: int, now: datetime) -> Activation:
        """Trusted worker ACK; cannot override client OFF, kill switch, stale revision."""
        stamp=self._utc(now)
        with self._db() as con:
            try:
                con.execute('BEGIN IMMEDIATE')
                row=self._read(con,account_id,customer_id)
                if row['revision'] != expected_revision:
                    raise ValueError('STALE_ACTIVATION_REVISION')
                if not (row['desired_on'] and row['entitlement_ok'] and row['connected']
                        and row['writer_verified'] and not row['kill_switch']):
                    raise PermissionError('ACCOUNT_NOT_AUTHORIZED_FOR_EFFECTIVE_ON')
                valid_until = (now.astimezone(timezone.utc) + timedelta(seconds=15)).isoformat()
                con.execute('''UPDATE account_activation SET effective_on=1, ack_revision=?,
                    ack_valid_until=?, updated_at=? WHERE account_id=?''',
                    (expected_revision,valid_until,stamp,account_id))
                out=self._activation(self._read(con,account_id,customer_id), now)
                con.execute('COMMIT')
                return out
            except Exception:
                con.execute('ROLLBACK')
                raise