"""Strict public Deriv synthetic tick snapshots. NEVER an account feed or Kronos signal.

13 symbols pinned from Deriv's independently observed active_symbols catalog
of 2026-10-22. No auth tokens, order requests, account balances, subscriptions,
or browser-to-broker access. Only a short lived server-side quote cache.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math
import time

from fastapi import APIRouter, Depends, HTTPException
import websockets

from app.models import Customer
from app.security import get_current_customer

WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public"
SYMBOLS = (
    ("R_10", "Volatility 10 Index"),
    ("R_25", "Volatility 25 Index"),
    ("R_50", "Volatility 50 Index"),
    ("R_75", "Volatility 75 Index"),
    ("R_100", "Volatility 100 Index"),
    ("CRASH150N", "Crash 150 Index"),
    ("CRASH300N", "Crash 300 Index"),
    ("CRASH600", "Crash 600 Index"),
    ("CRASH1000", "Crash 1000 Index"),
    ("BOOM150N", "Boom 150 Index"),
    ("BOOM300N", "Boom 300 Index"),
    ("BOOM600", "Boom 600 Index"),
    ("BOOM1000", "Boom 1000 Index"),
)
CODES = frozenset(symbol for symbol, _ in SYMBOLS)
assert len(CODES) == len(SYMBOLS) == 13

router = APIRouter(prefix="/api/v1", tags=["deriv-public-market"])
_cache: dict | None = None
_cached_at_monotonic: float = -1
_cache_lock = asyncio.Lock()


def _validate_tick(item: object, expected_symbol: str, now_epoch: float) -> dict:
    if not isinstance(item, dict) or item.get("symbol") != expected_symbol:
        raise ValueError("SYMBOL_IDENTITY_MISMATCH")
    stamp = item.get("epoch")
    if isinstance(stamp, bool) or not isinstance(stamp, (float, int)):
        raise ValueError("TICK_TIMESTAMP_INVALID")
    age = now_epoch - float(stamp)
    if not math.isfinite(age) or not -2 <= age <= 10:
        raise ValueError("TICK_STALE_OR_FUTURE")
    try:
        value = Decimal(str(item["quote"]))
    except (TypeError, KeyError, ValueError, InvalidOperation) as exc:
        raise ValueError("QUOTE_INVALID") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("QUOTE_NOT_POSITIVE_FINITE")
    return {
        "symbol": expected_symbol,
        "quote": str(value),
        "tick_utc": datetime.fromtimestamp(float(stamp), tz=timezone.utc).isoformat(),
        "age_seconds": round(max(0, age), 2),
    }


async def fetch_public_snapshot(*, connector=None, current_time=None) -> dict:
    """Allowlisted one-shot Deriv public ticks; all 13 required or entire result fails."""
    import json
    connector = connector or websockets.connect
    current_time = current_time or (lambda: datetime.now(timezone.utc).timestamp())
    found: dict[str, dict] = {}
    async with connector(
        WS_URL, open_timeout=8, close_timeout=3,
        max_size=500_000, ping_interval=None,
    ) as ws:
        for i, symbol in enumerate(sorted(CODES), 100):
            await ws.send(json.dumps({"ticks": symbol, "req_id": i}))
        deadline = time.monotonic() + 12
        while len(found) < len(CODES):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("PUBLIC_TICKS_TIMEOUT")
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            message = json.loads(raw)
            if not isinstance(message, dict) or "error" in message or message.get("msg_type") != "tick":
                raise RuntimeError("PUBLIC_TICK_RESPONSE_UNEXPECTED")
            item = message.get("tick")
            if not isinstance(item, dict) or item.get("symbol") not in CODES:
                raise RuntimeError("PUBLIC_TICK_SYMBOL_NOT_APPROVED")
            symbol = item["symbol"]
            if symbol in found:
                raise RuntimeError("DUPLICATE_PUBLIC_SYMBOL")
            found[symbol] = _validate_tick(item, symbol, current_time())
    checked_epoch = current_time()
    return {
        "status": "FRESH_PUBLIC_QUOTES",
        "source": "DERIV_PUBLIC_UNAUTHENTICATED",
        "checked_utc": datetime.fromtimestamp(checked_epoch, tz=timezone.utc).isoformat(),
        "quotes": [{**found[code], "name": label} for code, label in SYMBOLS],
        "broker_account_authenticated": False,
        "real_balance_verified": False,
        "real_positions_verified": False,
        "kronos_signals_verified": False,
        "orders_allowed": False,
    }


async def cached_snapshot() -> dict:
    global _cache, _cached_at_monotonic
    async with _cache_lock:
        if _cache is not None and (time.monotonic() - _cached_at_monotonic) < 8:
            # Never serve stale source ticks even when cache has not expired.
            checked = datetime.fromisoformat(_cache["checked_utc"]).timestamp()
            if datetime.now(timezone.utc).timestamp() - checked < 10 and all(0 <= datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(q['tick_utc']).timestamp() <= 10 for q in _cache['quotes']):
                return _cache
        result = await fetch_public_snapshot()
        _cache = result
        _cached_at_monotonic = time.monotonic()
        return result


@router.get("/market/deriv/public")
async def customer_deriv_public_quotes(
    _customer: Customer = Depends(get_current_customer),
) -> dict:
    try:
        return await cached_snapshot()
    except Exception as exc:
        # Do not disclose upstream errors to customers or substitute old prices.
        raise HTTPException(
            status_code=503, detail="DERIV_PUBLIC_MARKET_UNAVAILABLE",
        ) from exc
