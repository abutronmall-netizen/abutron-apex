"""ExecutionAgent — turns target weights into child orders.

Handles hysteresis (don't churn the book for a 0.3% drift), slice sizing with a
participation cap, and the flatten path used by the risk kill switch.
"""
from __future__ import annotations

from typing import Dict, List

from ..core.models import AgentRole, Fill, Order, Side
from .base import Agent, Context


class ExecutionAgent(Agent):
    name = "execution"
    role = AgentRole.EXECUTION

    def __init__(self, cfg, **kw):
        super().__init__(cfg, **kw)
        self.orders: List[Order] = []
        self.fills: List[Fill] = []
        self.skipped: Dict[str, str] = {}

    def step(self, ctx: Context) -> None:
        self._tick()
        self.status = "active"
        self.orders, self.fills, self.skipped = [], [], {}

        verdict = ctx.verdict
        if verdict and verdict.halted:
            if verdict.flatten:
                fills = ctx.broker.flatten()
                self.fills.extend(fills)
                if fills:
                    ctx.note(f"FLATTEN: risk kill switch ({'; '.join(verdict.breaches[:2])})")
            return

        eq = ctx.equity
        if eq <= 0:
            return
        ex = self.cfg["execution"]
        f = self.cfg["agents"]["fusion"]
        thresh_w = float(f.get("rebalance_threshold", 0.015))
        min_notional = float(ex.get("min_notional", 50.0))
        n_slices = max(1, int(ex.get("n_slices", 3)))
        part_cap = float(ex.get("participation_cap", 0.05))

        target = dict(ctx.target_weights)
        current = {s: p.notional for s, p in ctx.broker.positions.items()}
        symbols = set(target) | set(current)

        edges = ctx.extras.get("edge_bps", {})
        active = ctx.extras.get("active")
        for s in sorted(symbols):
            if active is not None and s not in active:
                self.skipped[s] = "market closed / no new bar"
                continue
            px = ctx.history.last_price(s) or ctx.broker.price(s)
            if px <= 0:
                continue
            cur_notional = current.get(s, 0.0)
            tgt_notional = target.get(s, 0.0) * eq
            delta = tgt_notional - cur_notional
            if abs(delta) < max(min_notional, thresh_w * eq):
                if abs(delta) > 0:
                    self.skipped[s] = f"within hysteresis ({abs(delta):.0f})"
                continue

            # --- cost-aware gate: never pay more than a third of the edge ---
            if delta * cur_notional >= 0 and s in edges:   # adding risk, not reducing
                meta = ctx.meta.get(s, {})
                cost_bps = float(meta.get("spread_bps", 2.0)) + float(meta.get("commission_bps", 0.0)) * 2
                if float(edges[s]) < 1.5 * cost_bps:
                    self.skipped[s] = f"edge {edges[s]:.1f}bps < cost gate {1.5 * cost_bps:.1f}bps"
                    continue

            qty_total = delta / px
            vol = float(ctx.history.arrays(s, 2)["v"][-1]) if ctx.history.n(s) > 1 else 0.0
            slice_qty = qty_total / n_slices
            if vol > 0 and abs(slice_qty) > part_cap * vol:
                slice_qty = (1.0 if slice_qty > 0 else -1.0) * part_cap * vol

            parent_id = f"{s}-{ctx.index}"
            filled = 0.0
            for k in range(n_slices):
                q = slice_qty
                if k == n_slices - 1:
                    q = qty_total - filled
                if abs(q) * px < min_notional / 2:
                    continue
                order = Order(
                    symbol=s, side=Side.BUY if q > 0 else Side.SELL, qty=abs(q),
                    tag=f"{'increase' if abs(tgt_notional) > abs(cur_notional) else 'reduce'}",
                    agent="execution", parent_id=parent_id,
                )
                self.orders.append(order)
                fill = ctx.broker.submit(order)
                if fill:
                    self.fills.append(fill)
                    filled += fill.qty if fill.side == Side.BUY else -fill.qty
                    ctx.broker.mark(ctx.ts)
                else:
                    self.skipped[s] = "broker rejected"
                    break
            if filled:
                side = "BUY" if filled > 0 else "SELL"
                ctx.note(f"{side} {abs(filled):.4g} {s} @ {px:.5g} ({(filled * px) / eq:+.2%} of equity)")
