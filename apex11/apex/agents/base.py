"""Agent base class + the context object threaded through every cycle."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from ..config import Cfg, universe_map
from ..core.history import HistoryStore
from ..core.models import AgentRole, RegimeState, RiskVerdict, Signal


@dataclass
class Context:
    cfg: Cfg
    history: HistoryStore
    broker: Any
    index: int = 0
    ts: float = field(default_factory=time.time)
    mode: str = "paper"

    regimes: Dict[str, RegimeState] = field(default_factory=dict)
    signals: List[Signal] = field(default_factory=list)
    raw_weights: Dict[str, float] = field(default_factory=dict)
    target_weights: Dict[str, float] = field(default_factory=dict)
    prev_weights: Dict[str, float] = field(default_factory=dict)
    verdict: Optional[RiskVerdict] = None
    notes: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)

    _meta: Optional[Dict[str, Dict[str, Any]]] = None

    @property
    def meta(self) -> Dict[str, Dict[str, Any]]:
        if self._meta is None:
            self._meta = universe_map(self.cfg)
        return self._meta

    def asset_class(self, symbol: str) -> str:
        return str(self.meta.get(symbol, {}).get("asset_class", "unknown"))

    @property
    def equity(self) -> float:
        return float(self.broker.equity)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def cov(self, n: int = 240):
        """Cached (symbols, annualised covariance, bars_per_year) for the cycle."""
        key = f"cov_{n}"
        if key not in self.extras:
            from ..data.base import bars_per_year as _bpy
            from ..risk import limits
            syms, mat = self.history.returns_matrix(n)
            if not syms:
                self.extras[key] = ([], np.zeros((0, 0)), 1.0)
            else:
                bpy = np.array([_bpy(self.asset_class(s)) for s in syms], dtype=float)
                self.extras[key] = (syms, limits.annualised_cov(mat, bpy), bpy)
        return self.extras[key]

    def current_weights(self) -> Dict[str, float]:
        eq = self.equity
        if eq <= 0:
            return {}
        return {s: p.notional / eq for s, p in self.broker.positions.items()}


class Agent:
    name = "agent"
    role: AgentRole = AgentRole.SIGNAL

    def __init__(self, cfg: Cfg, **kwargs: Any) -> None:
        self.cfg = cfg
        self.settings: Dict[str, Any] = dict(kwargs)
        self.last_run: float = 0.0
        self.runs: int = 0
        self.status: str = "idle"

    # subclasses override
    def step(self, ctx: Context) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def _tick(self) -> None:
        self.runs += 1
        self.last_run = time.time()

    def describe(self) -> Dict[str, Any]:
        return {"name": self.name, "role": self.role.value, "runs": self.runs, "status": self.status}


class SignalAgent(Agent):
    role = AgentRole.SIGNAL

    def generate(self, ctx: Context, symbol: str) -> Optional[Signal]:
        raise NotImplementedError  # pragma: no cover

    def step(self, ctx: Context) -> None:
        self._tick()
        self.status = "active"
        active = ctx.extras.get("active")
        for sym in ctx.history.symbols:
            if active is not None and sym not in active:
                continue
            if ctx.history.n(sym) < 40:
                continue
            sig = self.generate(ctx, sym)
            if sig is not None and abs(sig.score) > 1e-6:
                ctx.signals.append(sig)


def instrument_limit(cfg: Cfg, symbol: str) -> Dict[str, float]:
    for u in cfg["universe"]:
        if u["symbol"] == symbol:
            return {
                "max_weight": float(u.get("max_weight", 0.2)),
                "annual_vol": float(u.get("annual_vol", 0.2)),
            }
    return {"max_weight": 0.2, "annual_vol": 0.2}
