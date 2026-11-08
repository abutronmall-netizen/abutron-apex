"""Offline-only FP Markets native clock regression tests. No broker or MT5."""
from datetime import datetime, timezone
import pytest

from abutron_replacement.fp_history_window import (
    inspect_native_fp_history_window, require_fresh_fp_history_window,
)
from abutron_replacement.production_contracts import FeedRefused

SUNDAY = int(datetime(2026, 11, 8, 4, 11, 41, tzinfo=timezone.utc).timestamp())
FRIDAY_END_AS_SERVER_EPOCH = int(
    datetime(2026, 11, 7, 0, 0, 59, tzinfo=timezone.utc).timestamp()
)


def header(*, at=SUNDAY, end_server=None, offset=7200, tag="BROKER_NATIVE_NO_ORDER_FUNCTIONS"):
    if end_server is None:
        end_server = at + offset + 60
    lines = [""] * 20
    lines[0] = "ABUTRON_FP_ACCOUNT_HISTORY_V1"
    lines[6] = str(at)
    lines[7] = str(offset)
    lines[17] = str(end_server - 90 * 86400)
    lines[18] = str(end_server)
    lines[19] = tag
    return lines


def test_real_sunday_observation_is_stale_and_stays_blocked():
    doc = header(end_server=FRIDAY_END_AS_SERVER_EPOCH)
    d = inspect_native_fp_history_window(doc, observed_utc=SUNDAY)
    assert d.status == "MARKET_CLOSED_OR_QUOTES_STALE"
    assert d.history_end_utc == FRIDAY_END_AS_SERVER_EPOCH - 7200
    assert d.last_quote_utc == FRIDAY_END_AS_SERVER_EPOCH - 7200 - 60
    assert d.history_end_age_seconds == SUNDAY - d.history_end_utc
    assert d.last_quote_age_seconds > 86400
    assert d.possible_weekend_closure
    assert not d.history_window_fresh
    assert d.broker_order_authorized is False
    assert d.orders_submitted == 0
    with pytest.raises(FeedRefused, match="LAST_QUOTE_STALE"):
        require_fresh_fp_history_window(doc, observed_utc=SUNDAY)


def test_fresh_broker_local_history_converts_to_utc_without_granting_orders():
    d = require_fresh_fp_history_window(header(), observed_utc=SUNDAY)
    assert d.history_end_utc == SUNDAY + 60
    assert d.last_quote_utc == SUNDAY
    assert d.status == "HISTORY_WINDOW_RECENT_NOT_EXECUTION_AUTHORITY"
    assert d.history_window_fresh
    assert not d.broker_order_authorized
    assert d.orders_submitted == 0


def test_raw_server_time_does_not_hide_utc_last_quote_staleness():
    # Without offset conversion, end appears 2h more recent; +60s must not
    # make a quote older than 24h appear current either.
    h = header(end_server=SUNDAY + 7200 - 86400 + 90)
    d = inspect_native_fp_history_window(h, observed_utc=SUNDAY)
    assert d.history_end_age_seconds == 86400 - 90
    assert d.last_quote_age_seconds == 86400 - 30
    assert d.history_window_fresh
    h = header(end_server=SUNDAY + 7200 - 86400 + 40)
    d = inspect_native_fp_history_window(h, observed_utc=SUNDAY)
    assert d.history_end_age_seconds == 86400 - 40
    assert d.last_quote_age_seconds == 86400 + 20
    assert not d.history_window_fresh


@pytest.mark.parametrize("change, reason", [
    ({"offset": 0}, "BROKER_OFFSET"),
    ({"tag": "DISPATCH_ENABLED"}, "TAG"),
    ({"at": SUNDAY - 180}, "EXPORT_STALE"),
    ({"end_server": SUNDAY + 7200 + 300}, "FUTURE_END"),
    ({"end_server": 1}, "BEGIN_MALFORMED"),
])
def test_invalid_or_untrusted_header_is_rejected(change, reason):
    with pytest.raises(FeedRefused, match=reason):
        inspect_native_fp_history_window(header(**change), observed_utc=SUNDAY)


def test_overlong_window_and_invalid_policy_fail_closed():
    h = header()
    h[17] = str(int(h[18]) - 92 * 86400)
    with pytest.raises(FeedRefused, match="INVALID_SERVER_WINDOW"):
        inspect_native_fp_history_window(h, observed_utc=SUNDAY)
    with pytest.raises(FeedRefused, match="UNSAFE_QUOTE_AGE_POLICY"):
        inspect_native_fp_history_window(
            header(), observed_utc=SUNDAY, max_last_quote_age_seconds=86401
        )
    with pytest.raises(FeedRefused, match="UNVERIFIED_UTC_CLOCK"):
        inspect_native_fp_history_window(header(), observed_utc=True)


def test_weekend_is_a_hint_not_a_broker_market_certification():
    monday = int(datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc).timestamp())
    h = header(at=monday, end_server=monday + 7200 - 90000)
    d = inspect_native_fp_history_window(h, observed_utc=monday)
    assert d.status == "BROKER_QUOTES_STALE"
    assert not d.possible_weekend_closure
    assert not d.history_window_fresh
