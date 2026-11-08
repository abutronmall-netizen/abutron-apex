"""ApexEngine — the supervisor that runs one full decision cycle per bar."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agents.base import Context
from .agents.execution import ExecutionAgent
from .agents.portfolio import PortfolioAgent
from .agents.regime import RegimeAgent
from .agents.research import ResearchAgent
from .agents.risk import RiskAgent
from .agents.signals import BreakoutAgent, CarryAgent, MeanReversionAgent, TrendAgent
from .brokers.paper import PaperBroker
from .paths import data_path
from .config import Cfg, load_config
from .core.bus import BUS, JsonlLog
from .core.history import HistoryStore
from .core.models import Bar, Decision, Quote
from .llm.advisor import LlmAdvisor
from .memory import ReflectionMemory


class ApexEngine:
    """Multi-agent supervisor: regime -> signals -> portfolio -> risk -> advisor -> execution."""

    def __init__(self, cfg: Optional[Cfg] = None, mode: str = "paper", seed: Optional[int] = None,
                 broker: Any = None, log_decisions: bool = True) -> None:
        self.cfg = cfg or load_config()
        self.mode = mode
        self.seed = seed
        a = self.cfg["agents"]

        self.symbols = [u["symbol"] for u in self.cfg["universe"]]
        self.history = HistoryStore(self.symbols, maxlen=1500)
        # Signal-only contract is strictly local and cannot accept a network broker.
        if mode == "signal_only" and broker is not None:
            raise ValueError("signal_only cannot accept an external broker")
        self.broker = broker or PaperBroker(self.cfg)
        self.log_decisions = log_decisions
        self.log = JsonlLog(self.cfg["system"]["decision_log"])

        self.regime_agent = RegimeAgent(self.cfg, **a.get("regime", {}))
        self.signal_agents = []
        if a.get("trend", {}).get("enabled", True):
            self.signal_agents.append(TrendAgent(self.cfg))
        if a.get("mean_reversion", {}).get("enabled", True):
            self.signal_agents.append(MeanReversionAgent(self.cfg))
        if a.get("breakout", {}).get("enabled", True):
            self.signal_agents.append(BreakoutAgent(self.cfg))
        if a.get("carry", {}).get("enabled", True):
            self.signal_agents.append(CarryAgent(self.cfg))
        self.portfolio_agent = PortfolioAgent(self.cfg)
        self.risk_agent = RiskAgent(self.cfg)
        self.execution_agent = ExecutionAgent(self.cfg)
        self.advisor = LlmAdvisor(self.cfg)
        self.research_agent = ResearchAgent(self.cfg)
        self.memory = ReflectionMemory(
            horizon=int(self.cfg["agents"]["fusion"].get("memory_horizon", 24)),
            min_obs=int(self.cfg["agents"]["fusion"].get("memory_min_obs", 40)),
            path=str(data_path(self.cfg["system"].get(
                "memory_file",
                str(Path(self.cfg["system"].get("log_dir", "state")) / "memory.json")))),
        )
        self.portfolio_agent.memory = self.memory

        self.index = 0
        self.paused = False
        self.decisions: List[Decision] = []
        self.equity_curve: List[tuple[float, float]] = []

    # ------------------------------------------------------------------ helpers
    def _quotes_from_history(self, bars: Dict[str, Bar]) -> Dict[str, Quote]:
        spreads = {u["symbol"]: float(u.get("spread_bps", 2.0)) for u in self.cfg["universe"]}
        out: Dict[str, Quote] = {}
        for s in self.symbols:
            px = self.history.last_price(s)
            if px <= 0:
                continue
            bar = bars.get(s)
            vol = bar.volume if bar else 0.0
            half = px * spreads.get(s, 2.0) / 2.0 / 1e4
            out[s] = Quote(symbol=s, ts=self.history.last_ts, bid=px - half,
                           ask=px + half, last=px, volume=vol)
        return out

    def warmup(self, bars: Dict[str, Bar]) -> None:
        """Feed history without trading (indicator warm-up window)."""
        for b in bars.values():
            self.history.append(b)
        for q in self._quotes_from_history(bars).values():
            self.broker.set_quote(q)
        self.broker.mark(self.history.last_ts)
        self.index += 1

    # ------------------------------------------------------------------ core step
    def step(self, bars: Dict[str, Bar], ts: Optional[float] = None) -> Decision:
        for b in bars.values():
            self.history.append(b)
        quotes = self._quotes_from_history(bars)
        for q in quotes.values():
            self.broker.set_quote(q)
        # venue clock: orders sent on an earlier bar get their chance to fill here
        if hasattr(self.broker, "begin_bar"):
            self.broker.begin_bar(ts or self.history.last_ts)

        ctx = Context(
            cfg=self.cfg, history=self.history, broker=self.broker,
            index=self.index, ts=ts or self.history.last_ts, mode=self.mode,
        )
        ctx.extras["active"] = set(bars)

        if not self.paused:
            self.regime_agent.step(ctx)
            for agent in self.signal_agents:
                agent.step(ctx)
            self.portfolio_agent.step(ctx)
            self.risk_agent.step(ctx)

            # ---- optional advisory layer (risk down / veto only) --------
            advisory: Dict[str, Any] = {}
            if self.advisor.should_consult(ctx):
                advisory = self.advisor.consult(ctx)
                if ctx.verdict and not ctx.verdict.halted:
                    k = float(advisory.get("scale", 1.0))
                    vetoes = set(advisory.get("vetoes", []))
                    w = {s: v * k for s, v in ctx.verdict.weights.items() if s not in vetoes}
                    ctx.verdict.weights = {s: round(v, 5) for s, v in w.items() if abs(v) > 1e-4}
                    ctx.verdict.scale = k
                    ctx.target_weights = dict(ctx.verdict.weights)
                    if k < 0.999 or vetoes:
                        ctx.note(f"advisor: scale {k:.2f}, veto {sorted(vetoes) or '-'} :: {advisory.get('note','')}")
            ctx.extras["advisory"] = advisory

            # ---- event-intelligence overlay (down-only, optional) -------
            self.research_agent.step(ctx)

            # This mode is a replacement signal engine, NOT an order dispatcher.
            if self.mode != "signal_only":
                self.execution_agent.step(ctx)

        equity = self.broker.mark(ctx.ts)
        if not self.paused:
            self.memory.observe(ctx)
            if self.memory.settled and self.memory.settled % 200 == 0 and \
                    self.memory.settled != getattr(self, "_memory_saved_at", -1):
                self._memory_saved_at = self.memory.settled
                self.memory.save()
        self.equity_curve.append((ctx.ts, equity))

        decision = Decision(
            ts=ctx.ts, bar_index=self.index, equity=round(equity, 2),
            regimes={s: r.to_dict() for s, r in ctx.regimes.items()},
            signals=[s.to_dict() for s in ctx.signals],
            target_weights={k: round(v, 5) for k, v in ctx.target_weights.items()},
            verdict=ctx.verdict.to_dict() if ctx.verdict else {},
            advisory=dict(ctx.extras.get("advisory") or {}),
            research=[o.to_dict() for o in self.research_agent.overlays.values()],
            orders=[o.to_dict() for o in self.execution_agent.orders],
            notes=ctx.notes,
        )
        self.decisions.append(decision)
        if len(self.decisions) > 400:
            del self.decisions[:-400]
        if self.log_decisions:
            self.log.write(decision.to_dict())
        BUS.publish("decision", {"decision": decision.to_dict()})
        self.index += 1
        return decision

    # ------------------------------------------------------------------ control
    def pause(self, flag: bool = True) -> None:
        self.paused = flag
        if flag and hasattr(self.broker, "cancel_working"):
            self.broker.cancel_working()

    def flatten(self) -> List[Any]:
        return self.broker.flatten()

    def resume_risk(self) -> None:
        self.risk_agent.resume()
        if hasattr(self.broker, "resume_after_halt"):
            self.broker.resume_after_halt()

    # ------------------------------------------------------------------ state
    def state(self) -> Dict[str, Any]:
        snap = self.broker.snapshot()
        eq_curve = self.equity_curve[-500:]
        last = self.decisions[-1] if self.decisions else None
        return {
            "system": {
                "name": self.cfg["system"]["name"],
                "mode": self.mode,
                "paused": self.paused,
                "index": self.index,
                "ts": self.history.last_ts,
                "universe": self.symbols,
                "advisor": self.advisor.describe(),
            },
            "account": snap,
            "risk": self.risk_agent.metrics(),
            "research": self.research_agent.describe(),
            "memory": self.memory.to_dict(),
            "research_overlays": [o.to_dict() for o in self.research_agent.overlays.values()],
            "agents": [a.describe() for a in
                       [self.regime_agent, *self.signal_agents, self.portfolio_agent,
                        self.risk_agent, self.execution_agent]],
            "equity_curve": [[t, v] for t, v in eq_curve],
            "reputation": {k: round(v, 4) for k, v in
                           dict(sorted(self.portfolio_agent.reputation.items(),
                                       key=lambda kv: -kv[1])).items() if k.endswith(":*")},
            "regimes": last.regimes if last else {},
            "signals": last.signals if last else [],
            "target_weights": last.target_weights if last else {},
            "verdict": last.verdict if last else {},
            "notes": last.notes if last else [],
            "trades": [t.to_dict() for t in self.broker.trades()[-40:]][::-1],
            "recent_decisions": [d.to_dict() for d in self.decisions[-6:]][::-1],
        }
