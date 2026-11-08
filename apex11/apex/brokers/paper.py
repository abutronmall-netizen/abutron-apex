"""Paper broker: realistic simulated fills (spread + square-root impact + fees).

Everything the backtester and the live-paper loop executes goes through here, so
strategy and infrastructure see exactly the same cost model in both modes.
"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Deque, Dict, List, Optional

from ..config import Cfg
from ..core.models import Fill, Order, Position, Quote, Side, Trade


class PaperBroker:
    name = "paper"

    def __init__(self, cfg: Cfg, starting_equity: Optional[float] = None) -> None:
        self.cfg = cfg
        self.starting_equity = float(
            starting_equity if starting_equity is not None else cfg["account"]["starting_equity"]
        )
        self._cash = self.starting_equity
        self._pos: Dict[str, Position] = {}
        self._quotes: Dict[str, Quote] = {}
        self._fills: List[Fill] = []
        self._trades: List[Trade] = []
        self._equity_hist: Deque[tuple[float, float]] = deque(maxlen=20000)
        self._adv: Dict[str, float] = {}
        self.meta = {u["symbol"]: dict(u) for u in cfg["universe"]}
        self.ex = cfg["execution"]
        self.rejections: List[dict] = []
        self.total_commission = 0.0
        self.total_slippage = 0.0
        # ---- venue behaviour (NautilusTrader-style backtest/live parity) ----
        # A signal computed on bar t cannot be filled at bar t's own price: the
        # order travels, arrives on a later bar, and may only get a fraction of
        # the volume that actually traded.
        self.latency_bars = max(0, int(self.ex.get("latency_bars", 0)))
        self.order_ttl = max(1, int(self.ex.get("working_order_ttl_bars", 3)))
        self._bar = 0
        self._working: List[dict] = []
        self._emergency_halt = False
        self.partial_fills = 0
        self.expired_orders = 0
        self.replaced_orders = 0
        self._equity_hist.append((time.time(), self.starting_equity))

    # ------------------------------------------------------------------ market data
    def set_quote(self, q: Quote) -> None:
        self._quotes[q.symbol] = q
        p = self._pos.get(q.symbol)
        if p:
            p.last_price = q.mid
        # crude ADV proxy (notional traded per bar)
        prev = self._adv.get(q.symbol, 0.0)
        est = q.volume * q.mid if q.volume else prev
        self._adv[q.symbol] = 0.9 * prev + 0.1 * est if prev else est

    def price(self, symbol: str) -> float:
        q = self._quotes.get(symbol)
        if q:
            return q.mid
        p = self._pos.get(symbol)
        return p.last_price if p else 0.0

    def _half_spread(self, symbol: str) -> float:
        q = self._quotes.get(symbol)
        if q and q.ask > q.bid:
            return 0.5 * (q.ask - q.bid)
        m = self.price(symbol)
        return m * float(self.meta.get(symbol, {}).get("spread_bps", 2.0)) / 2.0 / 1e4

    def _impact_bps(self, symbol: str, notional: float) -> float:
        """Square-root market impact: bps = 1e4 * coef * sqrt(Q / ADV).

        coef ~ 0.001 reproduces the empirically observed ~1bp at 1% participation.
        """
        coef = float(self.ex.get("impact_coef", 0.001))
        adv = self._adv.get(symbol, 0.0)
        if adv <= 0:
            return coef * 1e4 * 0.05          # unknown liquidity: assume 5% participation
        return coef * math.sqrt(max(notional, 0.0) / adv) * 1e4

    def _commission(self, symbol: str, notional: float) -> float:
        bps = float(self.meta.get(symbol, {}).get("commission_bps", 0.0))
        return abs(notional) * bps / 1e4

    # ------------------------------------------------------------------ account
    @property
    def cash(self) -> float:
        return self._cash

    @property
    def positions(self) -> Dict[str, Position]:
        return self._pos

    @property
    def gross_exposure(self) -> float:
        return sum(abs(p.notional) for p in self._pos.values())

    @property
    def net_exposure(self) -> float:
        return sum(p.notional for p in self._pos.values())

    @property
    def unrealised(self) -> float:
        return sum(p.unrealised for p in self._pos.values())

    @property
    def equity(self) -> float:
        return self._cash + self.unrealised + sum(p.realised for p in self._pos.values())

    @property
    def leverage(self) -> float:
        eq = self.equity
        return self.gross_exposure / eq if eq > 0 else 0.0

    def equity_curve(self) -> List[tuple[float, float]]:
        return list(self._equity_hist)

    def mark(self, ts: Optional[float] = None) -> float:
        eq = self.equity
        self._equity_hist.append((ts or time.time(), eq))
        return eq

    # ------------------------------------------------------------------ execution
    def submit(self, order: Order) -> Optional[Fill]:
        """Route an order. With latency enabled it rests until a later bar."""
        if self._emergency_halt:
            self.rejections.append({"reason": "emergency halt active", "order": order.to_dict()})
            return None
        if self.latency_bars > 0:
            q = self._quotes.get(order.symbol)
            if q is None:
                self.rejections.append({"reason": "no quote", "order": order.to_dict()})
                return None
            # pre-trade gate runs now; execution-quality checks run on arrival
            qty = abs(order.qty)
            notional = qty * (order.limit_price or q.mid)
            if qty <= 0:
                return None
            if notional < float(self.ex.get("min_notional", 50.0)):
                self.rejections.append({"reason": "below min notional", "order": order.to_dict()})
                return None
            max_gross = self.equity * float(self.cfg["account"]["leverage"])
            if self.gross_exposure + notional > max_gross and not self._reducing(order):
                self.rejections.append({"reason": "margin", "order": order.to_dict()})
                return None
            # latest intent wins: never stack a second working order on the same
            # symbol+side, or the book silently doubles its intended size
            for w in list(self._working):
                if w["order"].symbol == order.symbol and w["order"].side == order.side:
                    self._working.remove(w)
                    self.replaced_orders += 1
            self._working.append({"order": order, "remaining": qty,
                                  "due": self._bar + self.latency_bars})
            return None
        return self._fill_now(order)

    def begin_bar(self, ts: Optional[float] = None) -> List[Fill]:
        """Advance the venue clock and try to work any resting orders."""
        self._bar += 1
        if self._emergency_halt:
            return []
        if not self._working:
            return []
        return self._work_orders(ts)

    def _work_orders(self, ts: Optional[float] = None) -> List[Fill]:
        out: List[Fill] = []
        still: List[dict] = []
        for w in self._working:
            if w["due"] > self._bar:
                still.append(w)
                continue
            if self._bar - w["due"] > self.order_ttl:
                self.expired_orders += 1
                self.rejections.append({"reason": "working order expired (TTL)",
                                        "order": w["order"].to_dict()})
                continue
            fill = self._fill_now(w["order"], cap_participation=True)
            if fill is None:                       # no quote this bar: keep resting
                still.append(w)
                continue
            out.append(fill)
            remaining = w["remaining"] - abs(fill.qty)
            if remaining > 1e-9:
                w["remaining"] = remaining
                w["order"].qty = remaining
                still.append(w)
                self.partial_fills += 1
        self._working = still
        return out

    def _fill_now(self, order: Order, cap_participation: bool = False) -> Optional[Fill]:
        q = self._quotes.get(order.symbol)
        if q is None:
            self.rejections.append({"reason": "no quote", "order": order.to_dict()})
            return None
        qty = abs(order.qty)
        if qty <= 0:
            return None
        if cap_participation:
            cap_frac = float(self.ex.get("participation_cap", 0.05))
            bar_vol = float(q.volume) if q.volume else 0.0
            if bar_vol > 0:
                qty = min(qty, max(cap_frac * bar_vol, 0.0))
                if qty <= 1e-9:
                    return None
        ref = order.limit_price or q.mid
        notional = qty * ref
        if notional < float(self.ex.get("min_notional", 50.0)):
            self.rejections.append({"reason": "below min notional", "order": order.to_dict()})
            return None

        # price with spread + market impact, adverse to the trader
        slip_bps = self._impact_bps(order.symbol, notional)
        if slip_bps > float(self.ex.get("max_slippage_bps", 25)):
            self.rejections.append(
                {"reason": f"slippage {slip_bps:.1f}bps > cap", "order": order.to_dict()}
            )
            return None
        half = self._half_spread(order.symbol)
        impact = ref * slip_bps / 1e4
        if order.side == Side.BUY:
            px = q.ask + impact if q.ask > q.bid else ref + half + impact
        else:
            px = q.bid - impact if q.ask > q.bid else ref - half - impact

        # margin check
        new_gross = self.gross_exposure + notional
        max_gross = self.equity * float(self.cfg["account"]["leverage"])
        if new_gross > max_gross and not self._reducing(order):
            self.rejections.append({"reason": "margin", "order": order.to_dict()})
            return None

        commission = self._commission(order.symbol, notional)
        self._apply_fill(order, px, qty, commission)
        fill = Fill(
            order_id=order.id, symbol=order.symbol, side=order.side, qty=qty,
            price=px, commission=commission, slippage_bps=slip_bps, ts=time.time(),
        )
        self._fills.append(fill)
        return fill

    def _reducing(self, order: Order) -> bool:
        p = self._pos.get(order.symbol)
        if not p or p.qty == 0:
            return False
        return (p.qty > 0 and order.side == Side.SELL) or (p.qty < 0 and order.side == Side.BUY)

    def _apply_fill(self, order: Order, px: float, qty: float, commission: float) -> None:
        p = self._pos.setdefault(order.symbol, Position(symbol=order.symbol, last_price=px))
        signed = qty if order.side == Side.BUY else -qty
        self._cash -= commission
        self.total_commission += commission
        p.fees += commission

        if p.qty == 0 or (p.qty > 0) == (signed > 0):
            new_qty = p.qty + signed
            p.avg_price = (abs(p.qty) * p.avg_price + qty * px) / abs(new_qty)
            p.qty = new_qty
            pnl = 0.0
        else:
            closing = min(abs(signed), abs(p.qty))
            direction = 1.0 if p.qty > 0 else -1.0
            pnl = (px - p.avg_price) * closing * direction
            p.realised += pnl
            p.qty += signed
            if abs(p.qty) < 1e-12:
                p.qty = 0.0
                p.avg_price = 0.0
            elif (p.qty > 0) != (direction > 0):
                p.avg_price = px
        p.last_price = px
        self._trades.append(
            Trade(
                symbol=order.symbol, side=order.side.value, qty=qty, price=px,
                notional=qty * px, ts=time.time(), pnl=pnl,
                reason=order.tag, agent=order.agent,
            )
        )

    def flatten(self, symbol: Optional[str] = None) -> List[Fill]:
        # Cancel unfilled orders BEFORE liquidation so they cannot reopen exposure.
        if symbol is None:
            self._working.clear()
            self._emergency_halt = True
        else:
            self._working = [w for w in self._working if w["order"].symbol != symbol]
        fills: List[Fill] = []
        targets = [symbol] if symbol else [s for s, p in self._pos.items() if abs(p.qty) > 1e-12]
        for s in targets:
            p = self._pos.get(s)
            if not p or abs(p.qty) < 1e-12:
                continue
            side = Side.SELL if p.qty > 0 else Side.BUY
            # a risk kill switch must not be simulated into a slow fill: bypass latency
            f = self._fill_now(Order(symbol=s, side=side, qty=abs(p.qty),
                                     tag="flatten", agent="risk"))
            if f:
                fills.append(f)
        return fills

    def cancel_working(self) -> int:
        """Cancel queued paper orders on pause, independent of liquidation."""
        count = len(self._working)
        self._working.clear()
        return count

    def resume_after_halt(self) -> None:
        """Explicit paper-mode reset; never called implicitly by an engine cycle."""
        self._emergency_halt = False

    # ------------------------------------------------------------------ reporting
    def trades(self) -> List[Trade]:
        return self._trades

    def fills(self) -> List[Fill]:
        return self._fills

    def snapshot(self) -> dict:
        return {
            "broker": self.name,
            "cash": round(self._cash, 2),
            "equity": round(self.equity, 2),
            "starting_equity": self.starting_equity,
            "unrealised": round(self.unrealised, 2),
            "gross_exposure": round(self.gross_exposure, 2),
            "net_exposure": round(self.net_exposure, 2),
            "leverage": round(self.leverage, 3),
            "positions": {s: p.to_dict() for s, p in self._pos.items() if abs(p.qty) > 1e-12},
            "n_trades": len(self._trades),
            "total_commission": round(self.total_commission, 2),
        }
