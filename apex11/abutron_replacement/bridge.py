"""APEX 1.1.0 decision engine as an ABUTRON read-only signal provider.

No MT5 credentials, network, broker adapter or order submission exists here.
Consumes *closed*, independently attested OHLCV bars from existing broker feed.
Output is a research/decision proposal; native ABUTRON risk & MT5 remain separate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
from typing import Any, Mapping

from apex.config import Cfg, load_config
from apex.core.models import Bar
from apex.engine import ApexEngine


class CandleRejected(ValueError):
    pass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    broker: str
    asset_class: str
    tick_size: float
    spread_bps: float
    commission_bps: float
    annual_vol: float
    max_weight: float
    timeframe_seconds: int = 300

    @classmethod
    def parse(cls, x: Mapping[str, Any]) -> "Instrument":
        try:
            m = cls(**{k: x[k] for k in cls.__dataclass_fields__ if k in x})
        except (KeyError, TypeError) as exc:
            raise ValueError("instrument metadata incomplete") from exc
        if not m.symbol or m.broker not in {"deriv", "fp_markets"}:
            raise ValueError("instrument must have a symbol and broker deriv/fp_markets")
        if m.asset_class not in {"deriv_synthetic", "fx_index"}:
            raise ValueError("instrument asset class not approved for replacement")
        if m.broker == "deriv" and m.asset_class != "deriv_synthetic":
            raise ValueError("invalid Deriv asset class")
        if m.broker == "fp_markets" and m.asset_class != "fx_index":
            raise ValueError("invalid FP Markets asset class")
        if m.timeframe_seconds != 300:
            raise ValueError("M5 only in this research replacement")
        for key in ("tick_size", "spread_bps", "commission_bps", "annual_vol", "max_weight"):
            val = getattr(m, key)
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError(f"invalid {key}")
        if m.tick_size <= 0 or m.spread_bps < 0 or m.commission_bps < 0 or m.annual_vol <= 0 or not (0 < m.max_weight <= 0.2):
            raise ValueError("instrument metadata out of allowed ranges")
        return m


class AbutronApex11SignalBridge:
    """APEX signal computation. Broker submission lives in a separate integration."""

    def __init__(self, instruments: list[Mapping[str, Any]], config_path: str | Path | None = None,
                 warmup_bars: int = 0) -> None:
        if not instruments:
            raise ValueError("nonempty measured instrument manifest required")
        parsed = [Instrument.parse(x) for x in instruments]
        if len({x.symbol for x in parsed}) != len(parsed):
            raise ValueError("duplicate symbols across brokers are ambiguous")
        self.instrument_by_symbol = {x.symbol: x for x in parsed}
        self.warmup_bars = int(warmup_bars)
        if self.warmup_bars < 0:
            raise ValueError("warmup_bars cannot be negative")
        base = Path(config_path) if config_path else Path(__file__).resolve().parents[1] / "config/abutron_signal_only.yaml"
        cfg = deepcopy(load_config(base))
        if cfg["system"]["mode"] != "signal_only":
            raise ValueError("only signal_only mode accepted")
        if cfg["agents"]["research"].get("enabled") or cfg["agents"]["carry"].get("enabled") or cfg["llm"].get("enabled"):
            raise ValueError("legacy/LLM/research/carry options not allowed")
        cfg["universe"] = [{
            "symbol": m.symbol, "asset_class": m.asset_class,
            "tick_size": m.tick_size, "spread_bps": m.spread_bps,
            "commission_bps": m.commission_bps, "annual_vol": m.annual_vol,
            "max_weight": m.max_weight,
        } for m in parsed]
        self.engine = ApexEngine(Cfg(cfg), mode="signal_only", log_decisions=False)
        self._last_ts: dict[str, float] = {}
        self._n: dict[str, int] = {m.symbol: 0 for m in parsed}

    def on_closed_candle(self, raw: Mapping[str, Any], *, observed_at: float | None = None) -> dict[str, Any]:
        symbol = raw.get("symbol")
        if symbol not in self.instrument_by_symbol:
            raise CandleRejected("unknown or unapproved symbol")
        if raw.get("is_closed") is not True or raw.get("provenance") != "authenticated_mt5":
            raise CandleRejected("only authenticated MT5 closed bars accepted")
        m = self.instrument_by_symbol[symbol]
        try:
            ts = float(raw["ts"])
            o, h, l, c = (float(raw[k]) for k in ("open", "high", "low", "close"))
            vol = float(raw.get("volume", 0.0))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise CandleRejected("invalid OHLCV") from exc
        vals=(ts, o, h, l, c, vol)
        if any(not math.isfinite(v) for v in vals) or min(o,h,l,c) <= 0 or vol < 0:
            raise CandleRejected("nonfinite or nonpositive price or invalid volume")
        if l > min(o,c) or h < max(o,c) or l > h:
            raise CandleRejected("invalid OHLC range")
        if ts <= self._last_ts.get(symbol, -math.inf):
            raise CandleRejected("duplicate or out-of-order closed bar")
        previous = self._last_ts.get(symbol)
        if previous is not None and ts - previous != m.timeframe_seconds:
            # No extra uninterrupted-history gate. Restart this instrument's
            # in-memory indicator window; do not fabricate missing candles.
            self._reset_symbol_history(symbol)
        if observed_at is not None:
            obs=float(observed_at)
            if not math.isfinite(obs) or ts > obs + 2:
                raise CandleRejected("future or invalid observation timestamp")
        # This timestamp contract is a *closing* time, not the bar-opening time.
        self._last_ts[symbol] = ts
        self._n[symbol] += 1
        b = Bar(symbol=symbol, ts=ts, open=o, high=h, low=l, close=c, volume=vol)
        if self._n[symbol] <= self.warmup_bars:
            self.engine.warmup({symbol: b})
            return self._proposal(symbol, ts, "WARMUP", {}, [], [], "insufficient closed bars")
        decision = self.engine.step({symbol: b}, ts=ts)
        weight = float(decision.target_weights.get(symbol, 0.0))
        halted = bool(decision.verdict.get("halted", False))
        side = "HOLD" if halted or abs(weight) < 1e-6 else ("BUY" if weight > 0 else "SELL")
        signals = [s for s in decision.signals if s["symbol"] == symbol]
        notes = list(decision.notes)
        if halted:
            notes.append("APEX paper-only risk model halted (not broker risk certification)")
        return self._proposal(symbol, ts, side, decision.regimes.get(symbol, {}),
                              signals, notes, "APEX 1.1 regime+ensemble+paper-risk",
                              weight=weight, verdict=decision.verdict)

    def _reset_symbol_history(self, symbol: str) -> None:
        # Use existing APEX state; on a candle gap, continue from the new
        # session without treating a missing interval as a market return.
        for name in ("_o", "_h", "_l", "_c", "_v", "_ts"):
            getattr(self.engine.history, name)[symbol].clear()
        self._n[symbol] = 0
        agent = self.engine.portfolio_agent
        agent._prev.pop(symbol, None)
        agent._last_prices.pop(symbol, None)
        agent._last_scores.pop(symbol, None)
        for key in list(agent.reputation):
            if key.endswith(":" + symbol):
                agent.reputation.pop(key, None)

    def _proposal(self, symbol, ts, side, regime, signals, notes, reason, weight=0.0, verdict=None):
        m = self.instrument_by_symbol[symbol]
        return {
            "decision_id": sha256(f"apex1.1|{m.broker}|{symbol}|{ts:.3f}".encode()).hexdigest(),
            "engine": "APEX_1_1_0", "broker": m.broker, "symbol": symbol,
            "timeframe": "M5", "bar_closed_ts": ts, "status": side,
            "target_weight_research_only": round(weight, 5),
            "regime": regime, "signals": signals, "reason": reason,
            "risk_verdict_simulated": verdict or {}, "notes": notes,
            "order": None,
            "position_size": None, "stop_loss": None, "take_profit": None,
        }
