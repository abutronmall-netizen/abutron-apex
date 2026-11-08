"""Read-only contracts for the *inspected* ABUTRON native MT5 file interfaces.

These parsers NEVER connect to MT5, write files, import a production router,
create an order request, or grant order authority. Account authentication is
stronger than simply accepting an arbitrary ``provenance`` label, but a native
file alone is NOT independent proof of broker origin: trusted worker ownership,
filesystem protection, customer entitlements and current account linkage remain
responsibilities of the existing production supervisor.

Source interfaces inspected read-only on 2026-11-08 SAST:
  /opt/apex-client-mt5/native_apex_feed.py
  /opt/apex-client-mt5/fpmarkets-feed/fp_feed_collect.py
  /opt/apex-client-mt5/apex_signal_native_router_v1.py
  /opt/apex-client-mt5/customer_order_ledger.py
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Mapping


class FeedRefused(ValueError):
    """Input rejected: never fall back to synthetic candles or guessed account."""


HEX32 = re.compile(r"^[a-f0-9]{32}$")
DERIV_ALLOWED = frozenset({
    'Volatility 10 Index.0', 'Volatility 25 Index.0', 'Volatility 50 Index.0',
    'Volatility 75 Index.0', 'Volatility 100 Index.0',
})
M5_SECONDS = 300


@dataclass(frozen=True)
class BrokerBoundBars:
    connection_id: str
    broker: str
    environment: str
    server: str
    symbol: str
    source_sha256: str
    source_kind: str
    bars: tuple[dict[str, Any], ...]
    checked_at: float
    broker_authenticated_by_this_code: bool = False  # cannot infer broker origin from a file


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _valid_price(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        raise FeedRefused('INVALID_BAR_PRICE') from None
    if not math.isfinite(f) or f <= 0:
        raise FeedRefused('INVALID_BAR_PRICE')
    return f


def _closed(symbol: str, open_ts: Any, o: Any, h: Any, l: Any, c: Any,
            *, captured_at: float, historical: bool) -> dict[str, Any]:
    try:
        ts = int(open_ts)
    except (TypeError, ValueError, OverflowError):
        raise FeedRefused('INVALID_BAR_TIME') from None
    if isinstance(open_ts, bool) or ts <= 0 or ts % M5_SECONDS:
        raise FeedRefused('BAR_TIME_NOT_M5_ALIGNED')
    p = [_valid_price(v) for v in (o, h, l, c)]
    if p[1] < max(p[0], p[3]) or p[2] > min(p[0], p[3]) or p[2] > p[1]:
        raise FeedRefused('INVALID_BAR_GEOMETRY')
    close_ts = ts + M5_SECONDS
    if close_ts > captured_at + 2:
        raise FeedRefused('CANDLE_NOT_CLOSED')
    return {'symbol': symbol, 'ts': close_ts, 'open': p[0], 'high': p[1],
            'low': p[2], 'close': p[3], 'volume': 0.0,
            'is_closed': True, 'provenance': 'authenticated_mt5',
            'native_open_ts': ts}


def _regular_read(path: Path, limit: int = 5_000_000) -> tuple[bytes, float]:
    """Read bounded file without symlinks, race changes or side effects."""
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit or before.st_size < 1:
        raise FeedRefused('UNSAFE_NATIVE_FILE')
    fd = os.open(str(path), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        start = os.fstat(fd)
        raw = os.read(fd, limit + 1)
        end = os.fstat(fd)
    finally:
        os.close(fd)
    if (start.st_dev, start.st_ino, start.st_size, start.st_mtime_ns) != (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
        raise FeedRefused('NATIVE_FILE_CHANGED')
    if (start.st_dev, start.st_ino, start.st_size, start.st_mtime_ns) != (
        end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns):
        raise FeedRefused('NATIVE_FILE_RACED')
    if len(raw) != start.st_size:
        raise FeedRefused('NATIVE_FILE_INCOMPLETE')
    return raw, before.st_mtime


def read_deriv_native_m5(*, connection_id: str, health_path: Path,
                         bars_path: Path, account_path: Path, login: str,
                         server: str = 'Deriv-Demo', now: float | None = None,
                         historical: bool = False,
                         freshness_seconds: int = 170) -> dict[str, BrokerBoundBars]:
    """Validate Deriv worker/account/nonce binding and native M5 export.

    Source *file* origin remains contingent upon privileged worker controls;
    this implementation does not claim independent broker authentication.
    No credentials are read. `account_path` is account *snapshot*, not auth.ini.
    """
    clock = time.time() if now is None else float(now)
    if not math.isfinite(clock) or not HEX32.fullmatch(connection_id) or server != 'Deriv-Demo':
        raise FeedRefused('DERIV_DEMO_BINDING_INVALID')
    if not str(login).isdigit():
        raise FeedRefused('DERIV_LOGIN_INVALID')
    hb, hb_mtime = _regular_read(health_path, limit=8000)
    try:
        health = json.loads(hb)
    except (ValueError, UnicodeError):
        raise FeedRefused('WORKER_HEALTH_NOT_JSON') from None
    if (health.get('id') != connection_id or health.get('broker') != 'Deriv' or
        health.get('mode') != 'DEMO' or health.get('server') != server or
        health.get('status') != 'CONNECTED' or health.get('heartbeat_fresh') is not True):
        raise FeedRefused('WORKER_NOT_ATTESTED')
    nonce = health.get('nonce')
    if not isinstance(nonce, str) or not HEX32.fullmatch(nonce):
        raise FeedRefused('WORKER_NONCE_INVALID')
    if not historical and not (-10 <= clock - hb_mtime <= 20):
        raise FeedRefused('WORKER_HEALTH_STALE')
    if Path(bars_path).name != 'ABUTRON_NATIVE_BARS_V2_'+nonce+'.txt':
        raise FeedRefused('DERIV_BAR_FILE_NONCE_MISMATCH')
    if Path(account_path).name != 'ABUTRON_NATIVE_ACCOUNT_V2_'+nonce+'.txt':
        raise FeedRefused('DERIV_ACCOUNT_FILE_NONCE_MISMATCH')
    bar_bytes, bar_mtime = _regular_read(bars_path)
    account_bytes, acc_mtime = _regular_read(account_path)
    if not historical and any(not -10 <= clock - t <= freshness_seconds for t in (bar_mtime, acc_mtime)):
        raise FeedRefused('NATIVE_EXPORT_STALE')
    try:
        info = account_bytes.decode('utf-8-sig').splitlines()
        lines = bar_bytes.decode('utf-8-sig').splitlines()
    except UnicodeError:
        raise FeedRefused('NATIVE_EXPORT_INVALID_ENCODING') from None
    if (len(info) < 7 or info[:3] != ['ABUTRON_NATIVE_ACCOUNT_V2',nonce,str(login)]
        or info[5] != 'USD' or lines[:2] != ['ABUTRON_NATIVE_BARS_V2',nonce]):
        raise FeedRefused('NATIVE_ACCOUNT_OR_NONCE_MISMATCH')
    if len(lines) > 9000:
        raise FeedRefused('NATIVE_BARS_EXCESSIVE')
    result: dict[str, list[dict[str,Any]]] = {s:[] for s in DERIV_ALLOWED}
    previous = {}
    seen = set()
    for record in lines[2:]:
        x = record.split('\t')
        if len(x) != 7:
            raise FeedRefused('NATIVE_BAR_FIELDS_INVALID')
        symbol, tf = x[:2]
        if tf != 'M5' or symbol not in DERIV_ALLOWED:
            # The official 13-symbol/6-timeframe native export includes other
            # frames and other symbols: ignore them, rather than rejecting it.
            continue
        row = _closed(symbol, *x[2:],captured_at=clock,historical=historical)
        ts = row['ts']
        if ts <= previous.get(symbol, 0) or (symbol,ts) in seen:
            raise FeedRefused('DUPLICATE_OR_UNSORTED_NATIVE_CANDLES')
        previous[symbol] = ts
        seen.add((symbol,ts))
        result[symbol].append(row)
    if not historical:
        for rows in result.values():
            if rows and (clock-rows[-1]['ts'] > 2*M5_SECONDS):
                raise FeedRefused('STALE_LIVE_CANDLE')
    return {symbol:BrokerBoundBars(
        connection_id=connection_id,broker='deriv',environment='DEMO',server=server,
        symbol=symbol,source_sha256=_sha(bar_bytes),source_kind='deriv_native_mt5_v2',
        bars=tuple(rows),checked_at=clock)
        for symbol,rows in result.items() if rows}


def read_fp_published_m5(*, path: Path, connection_id: str,
                         server: str = 'FPMarketsSC-Demo', now: float | None = None,
                         historical: bool = False) -> dict[str, BrokerBoundBars]:
    """Consume verified FP publisher schema, never accept self-labeled raw OHLC.

    This consumes output of the privileged existing FP native publisher, NOT
    direct MT5 attestation. Caller must establish publisher file ownership,
    broker-account authorization and exact FP worker bind separately.
    Incomplete output remains SHADOW-ONLY, never execution ready.
    """
    clock = time.time() if now is None else float(now)
    if not math.isfinite(clock) or not HEX32.fullmatch(connection_id):
        raise FeedRefused('FP_CONNECTION_ID_INVALID')
    source, mtime = _regular_read(path)
    try:
        d = json.loads(source)
    except (ValueError, UnicodeError):
        raise FeedRefused('FP_SNAPSHOT_NOT_JSON') from None
    if d.get('schema') != 'abutron.fpmarkets.native.candles.v1':
        raise FeedRefused('FP_NOT_COMPLETE_BROKER_NATIVE_SNAPSHOT')
    if (d.get('connection_id') != connection_id or d.get('source') != 'FP Markets DEMO MT5'
        or d.get('account_mode') != 'DEMO' or d.get('broker_server') != server
        or d.get('execution_enabled') is not False or d.get('orders_submitted') != 0):
        raise FeedRefused('FP_PUBLISHER_ACCOUNT_OR_AUTHORITY_INVALID')
    if not historical and not -10 <= clock - mtime <= 240:
        raise FeedRefused('FP_NATIVE_PUBLISHER_STALE')
    frames = d.get('bars')
    if not isinstance(frames,dict) or not frames:
        raise FeedRefused('FP_M5_MISSING')
    out = {}
    for symbol, tfmap in frames.items():
        if not isinstance(symbol,str) or len(symbol)>80 or not isinstance(tfmap,dict):
            raise FeedRefused('FP_SYMBOL_INVALID')
        rows = tfmap.get('M5')
        if not isinstance(rows,list):
            raise FeedRefused('FP_M5_UNAVAILABLE')
        previous = 0
        converted = []
        for item in rows:
            if not isinstance(item,dict):
                raise FeedRefused('FP_BAR_INVALID')
            row = _closed(symbol,item.get('time'),item.get('open'),item.get('high'),
                          item.get('low'),item.get('close'),captured_at=clock,historical=historical)
            if row['ts']<=previous:
                raise FeedRefused('FP_BARS_DUPLICATE_OR_OUT_OF_ORDER')
            previous=row['ts']
            converted.append(row)
        if not historical and converted and clock-converted[-1]['ts'] > 2*M5_SECONDS:
            raise FeedRefused('STALE_LIVE_CANDLE')
        if converted:
            out[symbol]=BrokerBoundBars(connection_id=connection_id,broker='fp_markets',
                environment='DEMO',server=server,symbol=symbol,
                source_sha256=_sha(source),source_kind='fp_native_collector_complete_v1',
                bars=tuple(converted),checked_at=clock)
    return out


def inert_native_compatibility_proposal(*, owner: str, connection_id: str,
                                          signal: Mapping[str,Any]) -> dict[str,Any]:
    """Calculate production ledger identity without requesting an order.

    The existing router rejects this proposal, since its legacy scanner and
    TradingAgents gates have NOT been replaced. No order activation flags.
    """
    if not HEX32.fullmatch(owner) or not HEX32.fullmatch(connection_id):
        raise FeedRefused('INVALID_OWNER_OR_CONNECTION')
    if signal.get('broker') != 'deriv' or signal.get('status') not in {'BUY','SELL','HOLD','WARMUP'}:
        raise FeedRefused('NO_APPROVED_ORDER_ROUTE')
    symbol = signal.get('symbol')
    side = signal.get('status')
    if symbol not in DERIV_ALLOWED:
        raise FeedRefused('UNSUPPORTED_DERIV_SYMBOL')
    try:
        close_time = int(signal['bar_closed_ts'])
    except (ValueError,KeyError,TypeError):
        raise FeedRefused('BAR_CLOSE_TIME_INVALID') from None
    if close_time % M5_SECONDS:
        raise FeedRefused('BAR_NOT_M5_CLOSED')
    opened_at = close_time-M5_SECONDS
    key = None if side not in {'BUY','SELL'} else sha256(
        (owner+'|'+connection_id+'|'+symbol+'|M5|'+str(opened_at)+'|'+side).encode()
    ).hexdigest()
    return {'schema':'abutron.apex11.native.compatibility.v1','symbol':symbol,
            'connection_id':connection_id,'m5_bar_time':opened_at,
            'side':side,'signal_key':key,'source_decision_id':signal.get('decision_id'),
            'orders_submitted':0,'order_request':None,
            'compatible_with_current_router':False,
            'blocker':'CURRENT_ROUTER_REQUIRES_LEGACY_SCANNER_AND_TRADINGAGENTS'}
