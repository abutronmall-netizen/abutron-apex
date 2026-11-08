"""Deriv WebSocket client — DEMO accounts only.

Implements the parts of the Deriv v3 API that APEX needs:
  * authorize            (token -> account, DEMO only, enforced below)
  * ticks_history        (backfill for indicator warm-up)
  * ticks subscribe      (live quote stream)
  * portfolio            (open contracts)
  * buy / sell           (multiplier contracts on synthetic indices)

Design: a dedicated asyncio loop runs in a background thread and keeps the latest
tick per symbol in a thread-safe cache, so the synchronous ApexEngine can consume
`snapshot()` without being rewritten as async.

    token = os.environ["DERIV_API_TOKEN"]      # from app.deriv.com, DEMO account
    client = DerivClient(app_id="1089", token=token)
    client.start(["R_75", "BOOM500"])
    print(client.snapshot()["R_75"])

SAFETY: `require_demo=True` refuses any non-virtual account. Do not disable it in
code you intend to run unattended; use a demo token while developing.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, Dict, List, Optional

from ..core.models import Bar

try:  # pragma: no cover - optional dependency
    import websockets
except Exception:  # pragma: no cover
    websockets = None

ENDPOINT = "wss://ws.derivws.com/websockets/v3"


class DerivError(RuntimeError):
    pass


class DerivClient:
    def __init__(self, app_id: str = "1089", token: Optional[str] = None,
                 endpoint: str = ENDPOINT, require_demo: bool = True) -> None:
        if websockets is None:  # pragma: no cover
            raise DerivError("install `websockets` to use the Deriv adapter")
        self.app_id = app_id
        self.token = token
        self.endpoint = f"{endpoint}?app_id={app_id}"
        self.require_demo = require_demo
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._req_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._lock = threading.Lock()
        self.ticks: Dict[str, Dict[str, float]] = {}
        self._tick_buffer: List[tuple] = []
        self._buf_lock = threading.Lock()
        self.account: Dict[str, Any] = {}
        self.connected = False
        self.last_error: Optional[str] = None

    # ------------------------------------------------------------------ plumbing
    def start(self, symbols: Optional[List[str]] = None) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, args=(symbols or [],), daemon=True)
        self._thread.start()
        for _ in range(100):
            if self.connected:
                return
            time.sleep(0.05)

    def _run(self, symbols: List[str]) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main(symbols))

    async def _main(self, symbols: List[str]) -> None:
        async with websockets.connect(self.endpoint, ping_interval=20) as ws:
            self._ws = ws
            self.connected = True
            asyncio.ensure_future(self._reader())
            if self.token:
                await self.request({"authorize": self.token})
            for s in symbols:
                await self.request({"ticks": s, "subscribe": 1})
            while True:
                await asyncio.sleep(1)

    async def _reader(self) -> None:
        async for raw in self._ws:  # type: ignore[union-attr]
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            rid = msg.get("req_id")
            if rid and rid in self._pending:
                fut = self._pending.pop(rid)
                if not fut.done():
                    fut.set_result(msg)
                continue
            if msg.get("msg_type") == "tick":
                t = msg["tick"]
                quote = float(t["quote"])
                self.ticks[t["symbol"]] = {
                    "quote": quote, "epoch": float(t["epoch"]),
                    "bid": float(t.get("bid", quote)), "ask": float(t.get("ask", quote)),
                }
                with self._buf_lock:
                    if len(self._tick_buffer) < 500_000:
                        self._tick_buffer.append((t["symbol"], float(t["epoch"]), quote))
            elif msg.get("msg_type") == "authorize":
                self.account = msg.get("authorize", {})
                if self.require_demo and not self.account.get("is_virtual", 0):
                    self.last_error = "live account blocked: require_demo=True"
                    raise DerivError("refusing to trade a real-money Deriv account")
            elif msg.get("error"):
                self.last_error = msg["error"].get("message", "unknown")

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def request(self, payload: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
        assert self._ws is not None, "not connected"
        rid = self._next_id()
        payload = {**payload, "req_id": rid}
        fut = self._loop.create_future()  # type: ignore[union-attr]
        self._pending[rid] = fut
        await self._ws.send(json.dumps(payload))
        return await asyncio.wait_for(fut, timeout=timeout)

    def call(self, payload: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
        """Blocking bridge for the synchronous engine."""
        if not self._loop:
            raise DerivError("client not started")
        fut = asyncio.run_coroutine_threadsafe(self.request(payload, timeout), self._loop)
        return fut.result(timeout + 5)

    # ------------------------------------------------------------------ api
    def ticks_history(self, symbol: str, count: int = 500, granularity: int = 3600) -> List[Dict[str, float]]:
        r = self.call({"ticks_history": symbol, "end": "latest", "count": count,
                       "style": "candles", "granularity": granularity})
        return r.get("candles", [])

    def drain_ticks(self, timeout: float = 0.0) -> List[tuple]:
        """Return and clear buffered (symbol, epoch, quote) ticks."""
        if timeout:
            deadline = time.time() + timeout
            while time.time() < deadline:
                with self._buf_lock:
                    if self._tick_buffer:
                        break
                time.sleep(0.05)
        with self._buf_lock:
            out = self._tick_buffer[:]
            self._tick_buffer.clear()
        return out

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return dict(self.ticks)

    def buy_multiplier(self, symbol: str, side: str, stake: float, multiplier: int = 100) -> Dict[str, Any]:
        """Open a MULTUP/MULTDOWN contract (Deriv's leveraged synthetic product)."""
        raise RuntimeError("ABUTRON offline staging: Deriv trade execution disabled")
        return self.call({
            "buy": "1", "price": round(stake, 2),
            "parameters": {
                "amount": round(stake, 2), "basis": "stake", "contract_type": side,
                "currency": self.account.get("currency", "USD"),
                "symbol": symbol, "multiplier": multiplier,
            },
        })

    def sell(self, contract_id: str, price: float = 0.0) -> Dict[str, Any]:
        raise RuntimeError("ABUTRON offline staging: direct Deriv trading disabled")
        return self.call({"sell": contract_id, "price": price})

    def portfolio(self) -> List[Dict[str, Any]]:
        return self.call({"portfolio": 1}).get("portfolio", {}).get("contracts", [])

    def balance(self) -> float:
        r = self.call({"balance": 1})
        return float(r.get("balance", {}).get("balance", 0.0))


class DerivFeed:
    """Adapts live Deriv ticks into hourly bars the ApexEngine can consume."""

    name = "deriv"

    def __init__(self, client: DerivClient, symbols: List[str], bar_seconds: int = 3600) -> None:
        self.client = client
        self.symbols = symbols
        self.bar_seconds = bar_seconds
        self._open: Dict[str, Dict[str, float]] = {}

    def warmup(self, n: int = 400) -> Dict[str, List[Bar]]:
        out: Dict[str, List[Bar]] = {}
        for s in self.symbols:
            candles = self.client.ticks_history(s, count=n, granularity=self.bar_seconds)
            out[s] = [
                Bar(symbol=s, ts=float(c["epoch"]), open=float(c["open"]), high=float(c["high"]),
                    low=float(c["low"]), close=float(c["close"]), volume=float(c.get("volume", 0)))
                for c in candles
            ]
        return out

    def stream(self):
        """Yields {symbol: Bar} whenever a bar closes."""
        while True:
            time.sleep(1.0)
            now = time.time()
            snap = self.client.snapshot()
            closed: Dict[str, Bar] = {}
            for s in self.symbols:
                t = snap.get(s)
                if not t:
                    continue
                bucket = int(t["epoch"] // self.bar_seconds) * self.bar_seconds
                px = t["quote"]
                cur = self._open.get(s)
                if cur is None or cur["ts"] != bucket:
                    if cur is not None:
                        closed[s] = Bar(symbol=s, ts=cur["ts"], open=cur["open"], high=cur["high"],
                                        low=cur["low"], close=cur["close"], volume=cur["n"])
                    self._open[s] = {"ts": bucket, "open": px, "high": px, "low": px, "close": px, "n": 0.0}
                else:
                    cur["high"] = max(cur["high"], px)
                    cur["low"] = min(cur["low"], px)
                    cur["close"] = px
                    cur["n"] += 1
            if closed:
                yield closed
