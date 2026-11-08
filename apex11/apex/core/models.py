"""Core domain objects shared by every agent, broker and reporter."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


# ----------------------------------------------------------------------------- enums
class AssetClass(str, Enum):
    CRYPTO = "crypto"
    US_EQUITY = "us_equity"
    FX_INDEX = "fx_index"
    DERIV_SYNTHETIC = "deriv_synthetic"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Regime(str, Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOL = "high_vol"
    UNKNOWN = "unknown"


class AgentRole(str, Enum):
    REGIME = "regime"
    SIGNAL = "signal"
    RISK = "risk"
    PORTFOLIO = "portfolio"
    EXECUTION = "execution"
    ADVISOR = "advisor"
    SUPERVISOR = "supervisor"


# ----------------------------------------------------------------------------- market data
@dataclass(slots=True)
class Quote:
    symbol: str
    ts: float
    bid: float
    ask: float
    last: float
    volume: float = 0.0

    @property
    def mid(self) -> float:
        return 0.5 * (self.bid + self.ask)

    @property
    def spread_bps(self) -> float:
        m = self.mid
        return 0.0 if m <= 0 else (self.ask - self.bid) / m * 1e4


@dataclass(slots=True)
class Bar:
    symbol: str
    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


# ----------------------------------------------------------------------------- agent output
@dataclass
class Signal:
    symbol: str
    direction: float          # -1..+1  (negative = short)
    strength: float           # 0..1    (conviction)
    agent: str
    horizon: str = "swing"
    rationale: str = ""
    ts: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        return self.direction * self.strength

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["score"] = round(self.score, 4)
        return d


@dataclass
class RegimeState:
    symbol: str
    regime: Regime
    adx: float
    slope: float              # normalised trend slope (per-bar, in vol units)
    vol_pct: float            # percentile of realised vol in lookback
    realised_vol: float       # annualised
    confidence: float
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["regime"] = self.regime.value
        return {k: (round(v, 5) if isinstance(v, float) else v) for k, v in d.items()}


@dataclass
class RiskVerdict:
    """Output of the risk agent: scaled target weights + reasons for rejections."""
    weights: Dict[str, float]
    scale: float = 1.0
    rejected: Dict[str, str] = field(default_factory=dict)
    breaches: List[str] = field(default_factory=list)
    var_95: float = 0.0
    gross: float = 0.0
    net: float = 0.0
    halted: bool = False
    flatten: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weights": {k: round(v, 5) for k, v in self.weights.items()},
            "scale": round(self.scale, 4),
            "rejected": self.rejected,
            "breaches": self.breaches,
            "var_95": round(self.var_95, 6),
            "gross": round(self.gross, 4),
            "net": round(self.net, 4),
            "halted": self.halted,
            "flatten": self.flatten,
        }


# ----------------------------------------------------------------------------- execution
@dataclass
class Order:
    symbol: str
    side: Side
    qty: float                      # base units (negative allowed -> normalised in __post_init__)
    order_type: str = "market"
    limit_price: Optional[float] = None
    tag: str = ""
    agent: str = "execution"
    parent_id: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    ts: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.qty < 0:
            self.qty = abs(self.qty)
            self.side = Side.SELL if self.side == Side.BUY else Side.BUY

    @property
    def signed_qty(self) -> float:
        return self.qty if self.side == Side.BUY else -self.qty

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        return d


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: float
    price: float
    commission: float = 0.0
    slippage_bps: float = 0.0
    ts: float = field(default_factory=time.time)

    @property
    def notional(self) -> float:
        return self.qty * self.price

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["notional"] = round(self.notional, 2)
        return d


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0
    last_price: float = 0.0
    realised: float = 0.0
    fees: float = 0.0

    @property
    def notional(self) -> float:
        return self.qty * self.last_price

    @property
    def unrealised(self) -> float:
        return (self.last_price - self.avg_price) * self.qty

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "qty": round(self.qty, 6),
            "avg_price": round(self.avg_price, 5),
            "last_price": round(self.last_price, 5),
            "notional": round(self.notional, 2),
            "unrealised": round(self.unrealised, 2),
            "realised": round(self.realised, 2),
            "fees": round(self.fees, 2),
        }


@dataclass
class Trade:
    symbol: str
    side: str
    qty: float
    price: float
    notional: float
    ts: float
    pnl: float = 0.0
    reason: str = ""
    agent: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "symbol": self.symbol,
            "side": self.side,
            "qty": round(self.qty, 6),
            "price": round(self.price, 5),
            "notional": round(self.notional, 2),
            "pnl": round(self.pnl, 2),
            "reason": self.reason,
            "agent": self.agent,
        }


@dataclass
class Decision:
    """One complete reasoning cycle, fully auditable."""
    ts: float
    bar_index: int
    equity: float
    regimes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    signals: List[Dict[str, Any]] = field(default_factory=list)
    target_weights: Dict[str, float] = field(default_factory=dict)
    verdict: Dict[str, Any] = field(default_factory=dict)
    advisory: Dict[str, Any] = field(default_factory=dict)
    research: List[Dict[str, Any]] = field(default_factory=list)
    orders: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
