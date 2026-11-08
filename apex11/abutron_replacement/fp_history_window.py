"""FP Markets DEMO native-history broker-clock validation (no MT5 or order I/O).

The native MQL5 V100 indicator uses TimeCurrent() in OnTimer(), then writes
HistorySelect(from=TimeCurrent()-90d, end=TimeCurrent()+60s) server-time
epochs to header positions 17/18. The collector must normalize them using
the separately checked broker offset, NOT compare raw server epochs to UTC.

When the forex market is closed, TimeCurrent() may remain at the last quote.
Do not synthesize new market timestamps or present old quotes as live.
This module only examines already-validated header metadata. A trustworthy
native worker, broker identity, orders and actual history are verified elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from .production_contracts import FeedRefused

_MAGIC = "ABUTRON_FP_ACCOUNT_HISTORY_V1"
_NO_ORDER_TAG = "BROKER_NATIVE_NO_ORDER_FUNCTIONS"
_MAX_WINDOW_SECONDS = 91 * 86400
_DEFAULT_MAX_AGE_SECONDS = 86400
_MAX_FUTURE_SECONDS = 120


@dataclass(frozen=True)
class FPHistoryWindow:
    status: str
    exported_at_utc: int
    server_offset_seconds: int
    history_begin_utc: int
    history_end_utc: int
    last_quote_utc: int
    history_end_age_seconds: int
    last_quote_age_seconds: int
    possible_weekend_closure: bool
    history_window_fresh: bool
    # This function cannot attest a real broker, authorize execution or place orders.
    broker_order_authorized: bool = False
    orders_submitted: int = 0


def _integer(value: str, name: str) -> int:
    if type(value) is not str or not value.isascii() or not value.isdecimal():
        raise FeedRefused("FP_HISTORY_" + name + "_MALFORMED")
    number = int(value)
    if number < 0:
        raise FeedRefused("FP_HISTORY_" + name + "_MALFORMED")
    return number


def inspect_native_fp_history_window(
    header: Sequence[str], *,
    observed_utc: int,
    expected_server_offset_seconds: int = 7200,
    max_last_quote_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS,
) -> FPHistoryWindow:
    """Parse the first twenty lines of a verified *DEMO* FP history export.

    The reader MUST first validate the complete native account/server/nonce
    binding, file ownership and source-integrity checks. Calling this function
    on arbitrary file contents does not establish broker authentication.

    Returns a non-authoritative stale/fresh diagnosis, not a trading decision.
    Any malformed, inconsistent or unjustifiably future-dated input fails closed.
    """
    if type(observed_utc) is not int or observed_utc <= 0:
        raise FeedRefused("FP_UNVERIFIED_UTC_CLOCK")
    if (type(expected_server_offset_seconds) is not int or
            abs(expected_server_offset_seconds) > 14 * 3600 or
            expected_server_offset_seconds % 900):
        raise FeedRefused("FP_UNSAFE_BROKER_OFFSET_POLICY")
    if (type(max_last_quote_age_seconds) is not int or
            not 0 < max_last_quote_age_seconds <= _DEFAULT_MAX_AGE_SECONDS):
        raise FeedRefused("FP_UNSAFE_QUOTE_AGE_POLICY")
    if (not isinstance(header, (list, tuple)) or len(header) < 20 or
            any(type(line) is not str for line in header[:20])):
        raise FeedRefused("FP_HISTORY_HEADER_MISSING")
    if header[0] != _MAGIC or header[19] != _NO_ORDER_TAG:
        raise FeedRefused("FP_HISTORY_EXPORT_TAG_UNTRUSTED")

    emitted_utc = _integer(header[6], "EXPORT_UTC")
    # The producer writes TimeGMT() in header field 6.
    if not -30 <= observed_utc - emitted_utc <= 140:
        raise FeedRefused("FP_HISTORY_EXPORT_STALE")
    offset = _integer(header[7], "SERVER_OFFSET")
    if offset != expected_server_offset_seconds:
        raise FeedRefused("FP_HISTORY_BROKER_OFFSET_UNVERIFIED")

    begin_server = _integer(header[17], "BEGIN")
    end_server = _integer(header[18], "END")
    if not 0 < end_server - begin_server <= _MAX_WINDOW_SECONDS:
        raise FeedRefused("FP_HISTORY_INVALID_SERVER_WINDOW")

    begin_utc = begin_server - offset
    end_utc = end_server - offset
    if begin_utc <= 0 or end_utc <= begin_utc:
        raise FeedRefused("FP_HISTORY_UTC_WINDOW_INVALID")
    if end_utc > observed_utc + _MAX_FUTURE_SECONDS:
        raise FeedRefused("FP_HISTORY_FUTURE_END_UNVERIFIED")

    # V100 appends sixty seconds to the last TimeCurrent() quote time.
    last_quote_utc = end_utc - 60
    end_age = observed_utc - end_utc
    quote_age = observed_utc - last_quote_utc

    weekend = datetime.fromtimestamp(observed_utc, timezone.utc).weekday() >= 5
    fresh = end_age <= max_last_quote_age_seconds and quote_age <= max_last_quote_age_seconds
    if fresh:
        status = "HISTORY_WINDOW_RECENT_NOT_EXECUTION_AUTHORITY"
    elif weekend:
        status = "MARKET_CLOSED_OR_QUOTES_STALE"
    else:
        status = "BROKER_QUOTES_STALE"

    return FPHistoryWindow(
        status=status,
        exported_at_utc=emitted_utc,
        server_offset_seconds=offset,
        history_begin_utc=begin_utc,
        history_end_utc=end_utc,
        last_quote_utc=last_quote_utc,
        history_end_age_seconds=end_age,
        last_quote_age_seconds=quote_age,
        possible_weekend_closure=weekend,
        history_window_fresh=fresh,
    )


def require_fresh_fp_history_window(
    header: Sequence[str], *,
    observed_utc: int,
    expected_server_offset_seconds: int | None = None,
) -> FPHistoryWindow:
    """Strict execution-data freshness gate, NOT an order authorization.

    Unlike historical research, a prospective execution snapshot requires a
    last native quote no older than two minutes AND an independently attested
    broker-to-UTC offset. A hardcoded default (+02:00) is insufficient because
    FP Markets server time can change. The caller must derive its offset from
    current authenticated same-worker evidence, not from this header alone.
    Even a passing window does not attest account, broker, entitlement,
    300-bar M5 warm-up, protected risk, or the order/ledger lifecycle.
    """
    if expected_server_offset_seconds is None:
        raise FeedRefused("FP_HISTORY_INDEPENDENT_OFFSET_REQUIRED")
    decision = inspect_native_fp_history_window(
        header,
        observed_utc=observed_utc,
        expected_server_offset_seconds=expected_server_offset_seconds,
        max_last_quote_age_seconds=120,
    )
    if not decision.history_window_fresh:
        raise FeedRefused("FP_HISTORY_LAST_QUOTE_STALE")
    return decision
