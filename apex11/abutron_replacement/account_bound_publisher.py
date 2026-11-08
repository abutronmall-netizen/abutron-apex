"""Account-scoped, replay-safe APEX M5 decision publication (SHADOW ONLY).

This file deliberately has NO broker order adapter, MT5 transport, activation
side effects, or authority to dispatch. The native file parser cannot prove
broker authenticity. Caller must supply a separately verified, short-lived
supervisor attestation; False is the safe default and causes rejection.

Original broker worker ownership, identity, feed freshness and entitlements must
be established externally. Neither the candidate nor its journal record grants
an MT5 order. Journal output can be consumed by an audit dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from .bridge import AbutronApex11SignalBridge, Instrument
from .production_contracts import BrokerBoundBars, FeedRefused, HEX32, M5_SECONDS

_HASH = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Publication:
    status: str
    publication_id: str | None = None
    proposal: dict[str, Any] | None = None
    # No downstream caller may mistake this for an MT5 writer admission.
    broker_order_authorized: bool = False
    orders_submitted: int = 0


class DecisionJournal:
    """Durable audit-only decisions with account and bar idempotency.

    This journal is not the order ledger. Its presence cannot release or
    modify any native order-risk reservation.
    """
    def __init__(self, path: str | Path):
        self.path = str(path)
        p = Path(self.path)
        if not p.parent.is_dir():
            raise FileNotFoundError("JOURNAL_DIRECTORY_NOT_PROVISIONED")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        stat = p.lstat()
        if not p.is_file() or p.is_symlink() or stat.st_mode & 0o077:
            raise PermissionError("DECISION_JOURNAL_FILE_PERMISSIONS")
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS decisions (
                publication_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL, account_id TEXT NOT NULL,
                broker TEXT NOT NULL, symbol TEXT NOT NULL,
                closed_ts INTEGER NOT NULL, bar_sha256 TEXT NOT NULL,
                manifest_sha256 TEXT NOT NULL, proposal_sha256 TEXT NOT NULL,
                payload TEXT NOT NULL, published_at TEXT NOT NULL,
                UNIQUE(customer_id,account_id,broker,symbol,closed_ts)
            )''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, isolation_level=None, timeout=15)
        try:
            db.execute('PRAGMA busy_timeout=15000')
            db.execute('PRAGMA synchronous=FULL')
        except Exception:
            db.close()
            raise
        try:
            yield db
        finally:
            db.close()

    def add(self, *, customer_id: str, account_id: str, feed: BrokerBoundBars,
            closed_ts: int, bar_sha256: str, manifest_sha256: str,
            proposal: Mapping[str, Any], published_at: datetime) -> Publication:
        key = f'{customer_id}|{account_id}|{feed.broker}|{feed.symbol}|{closed_ts}'
        publication_id = sha256(('APEX11_M5_SHADOW|'+key).encode()).hexdigest()
        canonical = json.dumps(proposal, sort_keys=True, separators=(',', ':'), allow_nan=False)
        # Whole native export checksums change as other symbols or older bars
        # roll forward. Dedupe this account's immutable final candle/decision,
        # not the external file checksum (still retained in first audit payload).
        semantic = dict(proposal)
        semantic.pop('source_sha256', None)
        proposal_hash = sha256(json.dumps(semantic, sort_keys=True,
                 separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        with self._db() as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('''SELECT bar_sha256,manifest_sha256,proposal_sha256
                  FROM decisions WHERE publication_id=?''', (publication_id,)).fetchone()
                if row is not None:
                    if row != (bar_sha256, manifest_sha256, proposal_hash):
                        db.execute('ROLLBACK')
                        raise FeedRefused('PUBLISHED_BAR_OR_MANIFEST_CHANGED')
                    db.execute('COMMIT')
                    return Publication('ALREADY_PUBLISHED_SHADOW_ONLY', publication_id)
                db.execute('''INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (publication_id,customer_id,account_id,feed.broker,feed.symbol,closed_ts,
                     bar_sha256,manifest_sha256,proposal_hash,canonical,published_at.isoformat()))
                db.execute('COMMIT')
                return Publication('PUBLISHED_SHADOW_ONLY',publication_id,dict(proposal))
            except Exception:
                try:
                    db.execute('ROLLBACK')
                except sqlite3.Error:
                    pass
                raise

    def read(self, publication_id: str) -> dict[str, Any] | None:
        if not _HASH.fullmatch(publication_id):
            raise ValueError('INVALID_PUBLICATION_ID')
        with self._db() as db:
            row = db.execute('SELECT payload FROM decisions WHERE publication_id=?', (publication_id,)).fetchone()
            return json.loads(row[0]) if row else None


def _stamp_closed_bar_time(value: Any, close_ts: int) -> Any:
    """Replace APEX agent wall-clock stamps with their actual closed M5 event time.

    Current APEX 1.1.0 agents stamp regime/signal ``ts`` with wall-clock time
    even when replaying the same closed bar. Do not let those diagnostic clocks
    change a broker-bound decision's idempotency hash across restarts.
    """
    if isinstance(value, dict):
        return {k: (close_ts if k == 'ts' else _stamp_closed_bar_time(v, close_ts))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_stamp_closed_bar_time(x, close_ts) for x in value]
    return value


def publish_native_m5(
    *, feed: BrokerBoundBars, instrument: Mapping[str, Any],
    customer_id: str, account_id: str, journal: DecisionJournal,
    now: datetime, supervisor_attested: bool = False,
    last_close_max_age_seconds: int = 600,
) -> Publication:
    """Calculate APEX from closed bars and journal only the latest decision.

    The externally verified supervisor MUST bind actual native-worker UID,
    broker login/account, owner/connection, nonce, fresh session and source
    permissions; merely setting supervisor_attested=True is not proof.
    Must never be called from an untrusted HTTP request with this flag exposed.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise FeedRefused('UNTRUSTED_CLOCK')
    if supervisor_attested is not True:
        raise FeedRefused('INDEPENDENT_NATIVE_SUPERVISOR_ATTESTATION_MISSING')
    if not isinstance(customer_id,str) or not HEX32.fullmatch(customer_id):
        raise FeedRefused('OWNER_ID_INVALID')
    if not isinstance(account_id,str) or not HEX32.fullmatch(account_id):
        raise FeedRefused('ACCOUNT_ID_INVALID')
    if feed.connection_id != account_id or feed.environment != 'DEMO':
        raise FeedRefused('BROKER_ACCOUNT_OR_LIVE_MISMATCH')
    if feed.broker not in {'deriv','fp_markets'}:
        raise FeedRefused('UNSUPPORTED_BROKER')
    if (feed.broker == 'deriv' and feed.source_kind != 'deriv_native_mt5_v2') or (
        feed.broker == 'fp_markets' and feed.source_kind != 'fp_native_collector_complete_v1'):
        raise FeedRefused('UNVERIFIED_NATIVE_FEED_KIND')
    if feed.broker == 'deriv' and feed.server != 'Deriv-Demo':
        raise FeedRefused('DERIV_NOT_DEMO')
    if feed.broker == 'fp_markets' and feed.server != 'FPMarketsSC-Demo':
        raise FeedRefused('FP_NOT_DEMO')
    m = Instrument.parse(instrument)
    if m.broker != feed.broker or m.symbol != feed.symbol:
        raise FeedRefused('INSTRUMENT_FEED_MISMATCH')
    if not isinstance(feed.source_sha256,str) or not _HASH.fullmatch(feed.source_sha256):
        raise FeedRefused('NATIVE_SOURCE_HASH_MISSING')
    utc_now = now.astimezone(timezone.utc)
    now_epoch = utc_now.timestamp()
    if not math.isfinite(feed.checked_at) or not -2 <= now_epoch-feed.checked_at <= 20:
        raise FeedRefused('NATIVE_FEED_VERIFICATION_STALE')
    if not 0 < last_close_max_age_seconds <= 2*M5_SECONDS:
        raise ValueError('UNSAFE_LAST_CLOSE_AGE_POLICY')
    if not feed.bars:
        raise FeedRefused('NO_CLOSED_M5_BARS')
    last = feed.bars[-1]
    if last.get('symbol') != feed.symbol or last.get('provenance') != 'authenticated_mt5' or last.get('is_closed') is not True:
        raise FeedRefused('NATIVE_FINAL_BAR_INVALID')
    try:
        close_ts = float(last['ts'])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise FeedRefused('NATIVE_FINAL_TIMESTAMP_INVALID') from None
    if not math.isfinite(close_ts) or close_ts != int(close_ts) or int(close_ts)%M5_SECONDS:
        raise FeedRefused('NATIVE_FINAL_M5_CLOSE_INVALID')
    if not -2 <= now_epoch-close_ts <= last_close_max_age_seconds:
        raise FeedRefused('NATIVE_FINAL_BAR_NOT_FRESH')
    for i, b in enumerate(feed.bars):
        if b.get('symbol') != feed.symbol or b.get('is_closed') is not True or b.get('provenance') != 'authenticated_mt5':
            raise FeedRefused('NATIVE_BAR_IDENTITY_INVALID')
        if not isinstance(b.get('ts'),(int,float)) or b['ts'] != int(b['ts']) or int(b['ts'])%M5_SECONDS:
            raise FeedRefused('NATIVE_BAR_TIMESTAMP_INVALID')
        if i and b['ts'] <= feed.bars[i-1]['ts']:
            raise FeedRefused('NATIVE_BAR_NOT_MONOTONIC')
    # Each call/connection has a fresh engine. No cross-customer state sharing.
    engine = AbutronApex11SignalBridge([dict(instrument)])
    result = None
    for bar in feed.bars:
        result=engine.on_closed_candle(bar,observed_at=now_epoch)
    if result is None or result['order'] is not None or result.get('status') not in ('BUY','SELL','HOLD','WARMUP'):
        raise FeedRefused('APEX_OUTPUT_CONTRACT_VIOLATION')
    # APEX bar decision is NOT an order proposal and can be HOLD.
    result = _stamp_closed_bar_time(dict(result), int(close_ts))
    result.update({'publication_schema':'abutron.apex11.account.shadow.v1',
                   'customer_id':customer_id,'connection_id':account_id,
                   'source_kind':feed.source_kind,'source_sha256':feed.source_sha256,
                   'order':None,'broker_order_authorized':False,'orders_submitted':0})
    bar_bytes = json.dumps(last,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()
    manifest_bytes = json.dumps(instrument,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()
    return journal.add(customer_id=customer_id,account_id=account_id,feed=feed,
        closed_ts=int(close_ts),bar_sha256=sha256(bar_bytes).hexdigest(),
        manifest_sha256=sha256(manifest_bytes).hexdigest(),proposal=result,
        published_at=utc_now)