"""Broker-account-bound FP Markets native M5 ingestion, including genuine partial feeds.

The existing privileged FP collector may export a correctly broker-bound *partial*
set of symbols; requiring all 13 before APEX can even compute a signal is not
necessary. This module does not infer publisher trust from a JSON label, grant
MT5 rights, or create an order. Only approved FP Markets DEMO schemas are read.
No Qwen, TradingAgents, Qlib, SMC or ICT dependency.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import time
from pathlib import Path
from typing import Any
from .production_contracts import (
    BrokerBoundBars, FeedRefused, HEX32, _regular_read, _closed, _sha,
)
from .candidate_contract import FP_SUPPORTED

_PARTIAL = 'abutron.fpmarkets.native.partial.readonly.v1'
_COMPLETE = 'abutron.fpmarkets.native.candles.v1'


def _time_iso(value: Any) -> float:
    if not isinstance(value, str):
        raise FeedRefused('FP_PUBLISHER_TIMESTAMP_MISSING')
    try:
        t = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if t.tzinfo is None:
            raise ValueError('naive')
        return t.timestamp()
    except (ValueError, OverflowError):
        raise FeedRefused('FP_PUBLISHER_TIMESTAMP_INVALID') from None


def read_fp_partial_or_complete_m5(*, path: Path, connection_id: str,
                                    server: str = 'FPMarketsSC-Demo',
                                    now: float | None = None,
                                    historical: bool = False):
    """Read partial/complete M5 observations from a trusted publisher path.

    Partial data remains partial. It allows APEX research/signal calculation
    only on actually present and mapped symbols. It does not mean the FP MT5
    execution EA, customer switch, risk or order writer is ready. Trusting
    the native publisher and the source-file owner requires external checks.
    """
    clock = time.time() if now is None else float(now)
    if not math.isfinite(clock) or not HEX32.fullmatch(connection_id) or server != 'FPMarketsSC-Demo':
        raise FeedRefused('FP_DEMO_CONNECTION_INVALID')
    source, mtime = _regular_read(Path(path))
    try:
        d = json.loads(source)
    except (ValueError, UnicodeError):
        raise FeedRefused('FP_SOURCE_JSON_INVALID') from None
    if not isinstance(d, dict):
        raise FeedRefused('FP_SOURCE_OBJECT_INVALID')
    schema = d.get('schema')
    if schema not in {_PARTIAL, _COMPLETE}:
        raise FeedRefused('FP_PUBLISHER_SCHEMA_NOT_APPROVED')
    expected_source = ('FP Markets DEMO MT5 native' if schema == _PARTIAL
                       else 'FP Markets DEMO MT5')
    if (d.get('source') != expected_source or
        d.get('connection_id') != connection_id or
        d.get('account_mode') != 'DEMO' or
        d.get('broker_server') != server or
        d.get('execution_enabled') is not False or
        d.get('orders_submitted') != 0):
        raise FeedRefused('FP_SOURCE_ACCOUNT_OR_AUTHORITY_MISMATCH')
    if schema == _PARTIAL and d.get('status') != 'PARTIAL_NOT_CERTIFIED':
        raise FeedRefused('FP_PARTIAL_STATUS_MISMATCH')
    checked = _time_iso(d.get('checked_at_utc'))
    if not historical and (not -10 <= clock - checked <= 240 or
                           not -10 <= clock - mtime <= 240):
        raise FeedRefused('FP_PUBLISHER_STALE')
    mapping, frames, quotes = d.get('mapping'), d.get('bars'), d.get('quotes')
    if not all(isinstance(v, dict) for v in (mapping, frames, quotes)):
        raise FeedRefused('FP_SOURCE_MAPPING_OR_BARS_MISSING')
    out = {}
    for canonical, data in frames.items():
        if canonical not in FP_SUPPORTED or not isinstance(data, dict):
            raise FeedRefused('FP_UNAPPROVED_CANONICAL_SYMBOL')
        m, q = mapping.get(canonical), quotes.get(canonical)
        if not isinstance(m, dict) or not isinstance(q, dict):
            raise FeedRefused('FP_BROKER_SYMBOL_MAPPING_OR_QUOTE_MISSING')
        actual = m.get('actual')
        if (m.get('status') != 'MAPPED' or m.get('trade_mode') != 4 or
            not isinstance(actual, str) or not actual or len(actual) > 100 or
            q.get('symbol') != actual):
            raise FeedRefused('FP_NATIVE_SYMBOL_MAPPING_NOT_VERIFIED')
        for k in ('bid', 'ask'):
            v = q.get(k)
            if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
                raise FeedRefused('FP_QUOTE_PRICE_INVALID')
        if q['ask'] < q['bid']:
            raise FeedRefused('FP_BID_ASK_INVERTED')
        # Weekend/closed markets are not bypassed for new orders. Historical
        # replay, however, can inspect authentic older data without pretending
        # the market is currently open.
        if not historical:
            qt = q.get('time')
            if type(qt) not in (float, int) or not -15 <= clock - qt <= 300:
                raise FeedRefused('FP_QUOTE_STALE')
        rows = data.get('M5')
        if not isinstance(rows, list):
            raise FeedRefused('FP_M5_NOT_PUBLISHED')
        previous = 0
        validated=[]
        for item in rows:
            if not isinstance(item, dict):
                raise FeedRefused('FP_M5_ROW_INVALID')
            row = _closed(canonical, item.get('time'), item.get('open'),
                          item.get('high'), item.get('low'),item.get('close'),
                          captured_at=clock, historical=historical)
            ts = int(row['ts'])
            if ts <= previous:
                raise FeedRefused('FP_M5_UNSORTED_OR_DUPLICATED')
            previous=ts
            validated.append(row)
        if validated:
            out[canonical]=BrokerBoundBars(
                connection_id=connection_id, broker='fp_markets',
                environment='DEMO', server=server, symbol=canonical,
                source_sha256=_sha(source),
                source_kind='fp_collector_partial_v1' if schema==_PARTIAL else 'fp_collector_complete_v1',
                bars=tuple(validated),checked_at=checked,
            )
    if not out:
        raise FeedRefused('FP_NO_AUTHENTIC_NATIVE_M5_BARS')
    return out
