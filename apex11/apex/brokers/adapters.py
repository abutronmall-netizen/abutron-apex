"""Broker adapters for real (demo) venues.

Both adapters implement the same tiny surface the engine uses:
    set_quote(Quote) -> None
    submit(Order)    -> Fill | None
    equity / cash / positions / trades / flatten

They are intentionally thin: the engine's PaperBroker is the source of truth for
sizing, and these adapters mirror the resulting orders to the venue.

Nothing here runs without credentials, and nothing here will ever touch a
real-money account: Deriv requires `is_virtual`, Alpaca points at paper-api.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..config import Cfg
from ..core.models import Fill, Order, Position, Quote, Side, Trade

__all__ = ["DerivBroker", "AlpacaPaperBroker"]


# --------------------------------------------------------------------------- Deriv
class DerivBroker:
    name = "deriv_demo"

    def __init__(self, cfg: Cfg, client: Any = None) -> None:
        self.cfg = cfg
        self.client = client
        self._quotes: Dict[str, Quote] = {}
        self._fills: List[Fill] = []
        self._trades: List[Trade] = []
        self._pos: Dict[str, Position] = {}
        self.symbol_map = dict(cfg["live"]["deriv"].get("default_symbol_map", {}))
        self.max_stake_pct = float(cfg["live"]["deriv"].get("max_stake_pct", 0.05))

    def set_quote(self, q: Quote) -> None:
        self._quotes[q.symbol] = q

    @property
    def equity(self) -> float:
        if self.client is None:
            return float(self.cfg["account"]["starting_equity"])
        try:
            return float(self.client.balance())
        except Exception:
            return float(self.cfg["account"]["starting_equity"])

    cash = equity

    def positions(self) -> Dict[str, Position]:
        return self._pos

    def trades(self) -> List[Trade]:
        return self._trades

    def submit(self, order: Order) -> Optional[Fill]:
        raise RuntimeError("ABUTRON offline staging: direct Deriv broker submission disabled")
        if self.client is None:
            raise RuntimeError("DerivClient not attached; run with mode=paper instead")
        symbol = self.symbol_map.get(order.symbol)
        if symbol is None:
            return None                       # not tradable on Deriv: skip silently
        q = self._quotes.get(order.symbol)
        if q is None:
            return None
        stake = min(order.qty * q.mid, self.equity * self.max_stake_pct)
        side = "MULTUP" if order.side == Side.BUY else "MULTDOWN"
        resp = self.client.buy_multiplier(symbol, side, stake)
        contract = resp.get("buy", {})
        price = float(contract.get("buy_price", q.mid))
        qty = stake / max(price, 1e-9)
        fill = Fill(order_id=order.id, symbol=order.symbol, side=order.side,
                    qty=qty, price=price, commission=0.0, slippage_bps=0.0)
        self._fills.append(fill)
        p = self._pos.setdefault(order.symbol, Position(symbol=order.symbol, last_price=price))
        signed = qty if order.side == Side.BUY else -qty
        p.qty += signed
        p.avg_price = price if p.avg_price == 0 else (p.avg_price + price) / 2
        self._trades.append(Trade(symbol=order.symbol, side=order.side.value, qty=qty, price=price,
                                  notional=stake, ts=fill.ts, reason=order.tag, agent=order.agent))
        return fill

    def flatten(self, symbol: Optional[str] = None) -> List[Fill]:
        if self.client is None:
            return []
        out: List[Fill] = []
        for c in self.client.portfolio():
            try:
                self.client.sell(c["contract_id"])
                out.append(Fill(order_id=c["contract_id"], symbol=c.get("symbol", ""),
                                side=Side.SELL, qty=float(c.get("buy_price", 0)),
                                price=float(c.get("buy_price", 0))))
            except Exception:
                continue
        self._pos.clear()
        return out


# --------------------------------------------------------------------------- Alpaca
class AlpacaPaperBroker:
    """Minimal Alpaca *paper* REST client (no SDK required)."""

    name = "alpaca_paper"

    def __init__(self, cfg: Cfg) -> None:
        lc = cfg["live"]["alpaca"]
        self.base = str(lc.get("endpoint", "https://paper-api.alpaca.markets")).rstrip("/")
        self.key = os.environ.get(str(lc.get("key_env", "ALPACA_KEY_ID")), "")
        self.secret = os.environ.get(str(lc.get("secret_env", "ALPACA_SECRET_KEY")), "")
        if "paper" not in self.base:
            raise RuntimeError("AlpacaPaperBroker refuses non-paper endpoints")
        self._quotes: Dict[str, Quote] = {}
        self._trades: List[Trade] = []

    def _req(self, path: str, method: str = "GET", body: Optional[dict] = None) -> Any:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            f"{self.base}{path}", data=data, method=method,
            headers={"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode()
        return json.loads(raw) if raw else {}

    def set_quote(self, q: Quote) -> None:
        self._quotes[q.symbol] = q

    @property
    def equity(self) -> float:
        try:
            return float(self._req("/v2/account")["equity"])
        except Exception:
            return 0.0

    cash = equity

    def positions(self) -> Dict[str, Position]:
        out: Dict[str, Position] = {}
        try:
            for p in self._req("/v2/positions"):
                out[p["symbol"]] = Position(symbol=p["symbol"], qty=float(p["qty"]),
                                            avg_price=float(p["avg_entry_price"]),
                                            last_price=float(p.get("current_price", 0)))
        except Exception:
            pass
        return out

    def trades(self) -> List[Trade]:
        return self._trades

    def submit(self, order: Order) -> Optional[Fill]:
        raise RuntimeError("ABUTRON offline staging: Alpaca submission disabled")
        side = "buy" if order.side == Side.BUY else "sell"
        body = {"symbol": order.symbol, "qty": str(round(order.qty, 6)), "side": side,
                "type": "market", "time_in_force": "day"}
        try:
            resp = self._req("/v2/orders", "POST", body)
        except (urllib.error.HTTPError, urllib.error.URLError):
            return None
        fill = Fill(order_id=resp.get("id", order.id), symbol=order.symbol, side=order.side,
                    qty=float(resp.get("filled_qty") or order.qty),
                    price=float(resp.get("filled_avg_price") or self._quotes.get(order.symbol, Quote(order.symbol, 0, 0, 0, 0)).mid))
        self._trades.append(Trade(symbol=order.symbol, side=side, qty=fill.qty, price=fill.price,
                                  notional=fill.qty * fill.price, ts=fill.ts, reason=order.tag,
                                  agent=order.agent))
        return fill

    def flatten(self, symbol: Optional[str] = None) -> List[Fill]:
        try:
            if symbol:
                self._req(f"/v2/positions/{symbol}", "DELETE")
            else:
                self._req("/v2/positions", "DELETE")
        except Exception:
            pass
        return []
