"""ResearchAgent — low-frequency *event intelligence* overlay.

This is the one idea worth importing from TauricResearch/TradingAgents into APEX.

TradingAgents runs an analyst team (fundamentals / news / sentiment / technical),
a bull-vs-bear researcher debate, a trader and an LLM risk committee, per decision.
That is genuinely good at *explaining* a market and terrible at being a hot loop:
tens of LLM calls and minutes of latency per decision.

APEX already owns the things a research framework does not have — a deterministic
risk ladder, position sizing, VaR, correlation clusters, a kill switch, execution
cost modelling and a multi-asset / synthetic-index universe. So the integration is
deliberately asymmetric:

    research tells you WHEN NOT TO TRADE  ·  APEX decides what and how much

The agent runs on a slow cadence (default: once per day of bars) and can only ever
*reduce* risk:

    conviction_mult  <= 1.0     scale the target weight down
    stop_mult        >= 1.0     widen the stop (give a thesis room to breathe)
    veto_bars        >= 0       block new exposure for N bars

It can never add exposure, flip direction, or introduce an instrument. Same
guardrail as the LlmAdvisor, but event-driven rather than a periodic review.

Two providers ship here:
  * CalendarProvider  — deterministic, no LLM, no key: blackout windows around
                        configured macro/earnings events.
  * LlmResearchProvider — OpenAI-compatible, structured JSON out, clipped hard.

Both are pure functions of data available *as of* ctx.ts. Nothing may look ahead.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from ..core.models import AgentRole
from .base import Agent, Context


@dataclass
class EventOverlay:
    symbol: str
    conviction_mult: float = 1.0     # [0, 1] only
    stop_mult: float = 1.0           # [1, 3]
    veto_bars: int = 0               # >= 0
    thesis: str = ""
    invalidation: str = ""
    source: str = "heuristic"
    ts: float = field(default_factory=time.time)

    def clip(self) -> "EventOverlay":
        self.conviction_mult = float(np.clip(self.conviction_mult, 0.0, 1.0))
        self.stop_mult = float(np.clip(self.stop_mult, 1.0, 3.0))
        self.veto_bars = int(max(0, self.veto_bars))
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "conviction_mult": round(self.conviction_mult, 3),
            "stop_mult": round(self.stop_mult, 2),
            "veto_bars": self.veto_bars,
            "thesis": self.thesis[:240],
            "invalidation": self.invalidation[:160],
            "source": self.source,
        }


# --------------------------------------------------------------------------- providers
class CalendarProvider:
    """Deterministic event blackout. No model, no key, no hallucination risk.

    `events` maps a UTC day (YYYY-MM-DD) or a weekday rule to affected symbols:
        {"2026-11-05": ["SPY", "QQQ", "US500"],   # FOMC
         "2026-11-07": ["NVDA"]}                  # earnings
    Anything inside `window_bars` of the event start gets its conviction cut and new
    exposure blocked; nothing is ever added.
    """

    name = "calendar"

    def __init__(self, event_map: Optional[Dict[str, List[str]]] = None,
                 window_bars: int = 6, cut: float = 0.5) -> None:
        self.event_map = event_map or {}
        self.window_bars = int(window_bars)
        self.cut = float(cut)
        self._bar_counts: Dict[str, int] = {}

    def _days(self, ts: float) -> List[str]:
        d = time.strftime("%Y-%m-%d", time.gmtime(ts))
        return [d, time.strftime("%Y-%m-%d", time.gmtime(ts + 86400))]

    def review(self, ctx: Context, symbols: List[str]) -> List[EventOverlay]:
        out: List[EventOverlay] = []
        days = self._days(ctx.ts)
        for sym in symbols:
            for day in days:
                if sym in self.event_map.get(day, ()):
                    out.append(EventOverlay(
                        symbol=sym, conviction_mult=self.cut, stop_mult=1.6,
                        veto_bars=self.window_bars, source="calendar",
                        thesis=f"scheduled event on {day}",
                        invalidation="event passes without a gap",
                    ))
                    break
        return out


class LlmResearchProvider:
    """OpenAI-compatible research call. Returns overlays, never orders."""

    name = "llm"

    SYSTEM = """You are a risk-focused research analyst on an automated desk.
For each instrument you may ONLY reduce risk. Output JSON:
{"overlays":[{"symbol":"...","conviction_mult":0..1,"stop_mult":1..3,
"veto_bars":0..N,"thesis":"<=25 words","invalidation":"<=12 words"}]}
Rules: conviction_mult <= 1 always; use < 1 only with a concrete, dated reason
(event risk, liquidity, regime break). Never output a symbol not in the input list.
If there is nothing material, return {"overlays":[]}."""

    def __init__(self, model: str = "gpt-4o-mini",
                 base_url: str = "https://api.openai.com/v1",
                 timeout: float = 25.0, api_key: Optional[str] = None) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key or os.environ.get("APEX_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def review(self, ctx: Context, symbols: List[str]) -> List[EventOverlay]:
        if not self.available:
            return []
        snapshot = {
            "as_of_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ctx.ts)),
            "instruments": {
                s: {
                    "regime": (ctx.regimes[s].regime.value if s in ctx.regimes else "unknown"),
                    "realised_vol": round(ctx.regimes[s].realised_vol, 3) if s in ctx.regimes else None,
                    "target_weight": round(ctx.target_weights.get(s, 0.0), 4),
                }
                for s in symbols
            },
        }
        body = json.dumps({
            "model": self.model, "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self.SYSTEM},
                {"role": "user", "content": json.dumps(snapshot)},
            ],
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            payload = json.loads(r.read().decode())
        text = payload["choices"][0]["message"]["content"]
        data = json.loads(text)
        out: List[EventOverlay] = []
        for o in data.get("overlays", []):
            if o.get("symbol") not in symbols:
                continue                      # never introduce an instrument
            out.append(EventOverlay(
                symbol=o["symbol"],
                conviction_mult=float(o.get("conviction_mult", 1.0)),
                stop_mult=float(o.get("stop_mult", 1.0)),
                veto_bars=int(o.get("veto_bars", 0)),
                thesis=str(o.get("thesis", ""))[:240],
                invalidation=str(o.get("invalidation", ""))[:160],
                source="llm",
            ).clip())
        return out


class HeuristicProvider:
    """Offline fallback: flags vol-regime breakouts and signal disagreement."""

    name = "heuristic"

    def review(self, ctx: Context, symbols: List[str]) -> List[EventOverlay]:
        out: List[EventOverlay] = []
        votes: Dict[str, List[float]] = {}
        for s in ctx.signals:
            votes.setdefault(s.symbol, []).append(s.score)
        for sym in symbols:
            rs = ctx.regimes.get(sym)
            v = votes.get(sym, [])
            if rs and rs.vol_pct > 0.9 and rs.confidence > 0.7:
                out.append(EventOverlay(
                    symbol=sym, conviction_mult=0.6, stop_mult=1.4,
                    thesis=f"vol percentile {rs.vol_pct:.0%} in {rs.regime.value}",
                    invalidation="vol percentile back under 75%", source="heuristic"))
            elif len(v) > 1 and float(np.std(v)) > 1.0:
                out.append(EventOverlay(
                    symbol=sym, conviction_mult=0.7,
                    thesis="agent disagreement exceeds 1.0 score", source="heuristic"))
        return out


# --------------------------------------------------------------------------- agent
class ResearchAgent(Agent):
    role = AgentRole.ADVISOR
    name = "research"

    def __init__(self, cfg, provider: Any = None, **kw) -> None:
        super().__init__(cfg, **kw)
        r = cfg["agents"].get("research", {}) or {}
        self.refresh_every = int(r.get("refresh_every", 24))
        self.max_veto = int(r.get("max_veto_bars", 24))
        self.enabled = bool(r.get("enabled", False))
        if provider is not None:
            self.provider = provider
        else:
            key = os.environ.get("APEX_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
            self.provider = (LlmResearchProvider(
                model=str(cfg["llm"].get("model", "gpt-4o-mini")),
                base_url=str(cfg["llm"].get("base_url", "https://api.openai.com/v1")),
                timeout=float(cfg["llm"].get("timeout_s", 25)), api_key=key)
                if key else HeuristicProvider())
        self.overlays: Dict[str, EventOverlay] = {}
        self.veto_until: Dict[str, int] = {}
        self.last_refresh: int = -10**9
        self.log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    def step(self, ctx: Context) -> None:
        if not self.enabled:
            return
        self._tick()
        self.status = "active"
        if ctx.index - self.last_refresh >= self.refresh_every:
            self.last_refresh = ctx.index
            self._refresh(ctx)
        self._apply(ctx)

    def _refresh(self, ctx: Context) -> None:
        symbols = list(ctx.target_weights) or list(ctx.meta)
        try:
            found = self.provider.review(ctx, symbols)
        except Exception as exc:            # a research failure must never stop trading
            self.status = f"degraded: {type(exc).__name__}"
            return
        self.overlays = {}
        for o in found:
            o.clip()
            o.veto_bars = min(o.veto_bars, self.max_veto)
            self.overlays[o.symbol] = o
            if o.veto_bars:
                self.veto_until[o.symbol] = ctx.index + o.veto_bars
            entry = {"ts": ctx.ts, "index": ctx.index, **o.to_dict()}
            self.log.append(entry)
            ctx.note(f"RESEARCH {o.symbol}: x{o.conviction_mult:.2f} veto {o.veto_bars}b — {o.thesis}")
        if len(self.log) > 500:
            del self.log[:-500]

    def _apply(self, ctx: Context) -> None:
        """Down-only transform of the post-risk target weights."""
        w = dict(ctx.target_weights)
        for sym, o in self.overlays.items():
            if sym in w:
                w[sym] = w[sym] * o.conviction_mult
        for sym, until in list(self.veto_until.items()):
            if ctx.index < until:
                w[sym] = 0.0                # blackout: no new exposure
            else:
                del self.veto_until[sym]
        ctx.target_weights = {k: v for k, v in w.items() if abs(v) > 1e-6}

    def stop_multiplier(self, symbol: str) -> float:
        o = self.overlays.get(symbol)
        return o.stop_mult if o else 1.0

    def describe(self) -> Dict[str, Any]:
        d = super().describe()
        d.update({"enabled": self.enabled, "provider": getattr(self.provider, "name", "?"),
                  "refresh_every": self.refresh_every, "overlays": len(self.overlays),
                  "active_vetoes": len(self.veto_until)})
        return d
