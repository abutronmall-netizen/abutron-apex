"""Reflection memory — settle every decision, learn which agent works *where*.

APEX's reputation EWMA answers "is this agent any good right now?" but not "why".
This module is the explainable version, imported in spirit from TradingAgents'
memory log (settle the decision against realised outcome, then write the lesson):

    decision at bar i  ->  wait H bars  ->  realised return + alpha vs benchmark
                       ->  update a per-(agent, regime) cell
                       ->  emit a human-readable lesson
                       ->  feed a shrunk trust multiplier back into the ensemble

Everything is causal: a decision is only settled once `bar i + H` exists, and the
cell statistics are a pure function of decisions whose horizon has closed.

Cells store only sufficient statistics, so the memory is O(agents x regimes)
regardless of run length, and it serialises to JSON for restarts.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .core.models import Regime

REGIMES = [Regime.TREND_UP.value, Regime.TREND_DOWN.value, Regime.RANGE.value,
           Regime.HIGH_VOL.value, Regime.UNKNOWN.value]
EPS = 0.05          # scores below this are "no opinion" and don't count as hits


@dataclass
class Cell:
    """Sufficient statistics for one (agent, regime) pair."""
    n: int = 0
    hits: int = 0
    n_long: int = 0
    n_short: int = 0
    sum_r_long: float = 0.0
    sum_r_short: float = 0.0
    sum_score_r: float = 0.0
    sum_r2: float = 0.0

    def add(self, score: float, ret: float) -> None:
        self.n += 1
        self.sum_score_r += score * ret
        self.sum_r2 += ret * ret
        if score > 0:
            self.n_long += 1
            self.sum_r_long += ret
        elif score < 0:
            self.n_short += 1
            self.sum_r_short += ret
        if abs(score) >= EPS and abs(ret) > 0:
            if (score > 0) == (ret > 0):
                self.hits += 1

    # ---- derived -----------------------------------------------------
    @property
    def hit_rate(self) -> float:
        decisive = self.n - (self.n - self.n_long - self.n_short)
        return self.hits / decisive if decisive > 0 else 0.0

    @property
    def ic(self) -> float:
        """Correlation-ish score/return alignment, in [-1, 1]."""
        if self.n < 2 or self.sum_r2 <= 0:
            return 0.0
        return float(self.sum_score_r / math.sqrt(self.sum_r2 * self.n))

    @property
    def edge_bps(self) -> float:
        """Mean return after an up vote minus after a down vote, in bps."""
        if self.n_long == 0 or self.n_short == 0:
            return 0.0
        return float((self.sum_r_long / self.n_long - self.sum_r_short / self.n_short) * 1e4)

    @property
    def tstat(self) -> float:
        return float(self.ic * math.sqrt(max(self.n, 1)))

    def to_dict(self) -> Dict[str, Any]:
        return {"n": self.n, "hit_rate": round(self.hit_rate, 3), "ic": round(self.ic, 4),
                "edge_bps": round(self.edge_bps, 2), "tstat": round(self.tstat, 2),
                "n_long": self.n_long, "n_short": self.n_short}


@dataclass
class Pending:
    index: int
    ts: float
    horizon: int
    prices: Dict[str, float]
    regimes: Dict[str, str]
    votes: Dict[str, Dict[str, float]]
    weights: Dict[str, float]


class ReflectionMemory:
    """Settles decisions, scores agents by regime, and writes the lessons."""

    def __init__(self, horizon: int = 24, min_obs: int = 40,
                 path: Optional[str] = None, max_pending: int = 4000) -> None:
        self.horizon = int(horizon)
        self.min_obs = int(min_obs)
        self.path = Path(path) if path else None
        self.cells: Dict[str, Dict[str, Cell]] = {}
        self.pending: List[Pending] = []
        self.settled = 0
        self.max_pending = int(max_pending)
        self.lessons: List[Dict[str, Any]] = []
        self.last_settle_index = -1
        self._load()

    # ------------------------------------------------------------------ record
    def observe(self, ctx: Any) -> None:
        """Call once per cycle, after execution. Record now, settle the matured."""
        prices = {s: ctx.history.last_price(s) for s in ctx.history.symbols}
        votes: Dict[str, Dict[str, float]] = {}
        for sig in ctx.signals:
            votes.setdefault(sig.symbol, {})[sig.agent] = float(sig.score)
        self.pending.append(Pending(
            index=ctx.index, ts=ctx.ts, horizon=self.horizon, prices=prices,
            regimes={s: r.regime.value for s, r in ctx.regimes.items()},
            votes=votes, weights=dict(ctx.target_weights),
        ))
        self._settle(ctx)

    def _settle(self, ctx: Any) -> None:
        if not self.pending:
            return
        now = {s: ctx.history.last_price(s) for s in ctx.history.symbols}
        keep: List[Pending] = []
        closed = 0
        for p in self.pending:
            if ctx.index - p.index < p.horizon:
                keep.append(p)
                continue
            self._close(p, now, ctx)
            closed += 1
        if closed:
            self.settled += closed
            self.last_settle_index = ctx.index
        self.pending = keep[-self.max_pending:]

    def _close(self, p: Pending, now: Dict[str, float], ctx: Any) -> None:
        rets: Dict[str, float] = {}
        for s, px0 in p.prices.items():
            px1 = now.get(s, px0)
            if px0 > 0 and px1 > 0:
                rets[s] = px1 / px0 - 1.0
        if not rets:
            return
        bench = float(np.mean(list(rets.values())))          # equal-weight alpha

        # score each agent's vote in the regime it was cast in
        for sym, agent_votes in p.votes.items():
            r = rets.get(sym)
            reg = p.regimes.get(sym, Regime.UNKNOWN.value)
            if r is None or abs(r) < 1e-12:
                continue
            for agent, score in agent_votes.items():
                cell = self.cells.setdefault(agent, {}).setdefault(reg, Cell())
                cell.add(float(score), float(r))

        # the book itself (weight x return) for a portfolio-level lesson
        pnl = sum(w * rets.get(s, 0.0) for s, w in p.weights.items())
        self._maybe_lesson(p.index, pnl, bench, rets)

    def _maybe_lesson(self, index: int, pnl: float, bench: float, rets: Dict[str, float]) -> None:
        alpha = pnl - bench * sum(abs(w) for w in (self.pending[-1].weights.values() if self.pending else [0]))
        lesson = {"index": index, "pnl": round(pnl, 5), "bench": round(bench, 5),
                  "alpha": round(alpha, 5), "ts": time.time()}
        self.lessons.append(lesson)
        if len(self.lessons) > 400:
            del self.lessons[:-400]

    # ------------------------------------------------------------------ query
    def cell(self, agent: str, regime: str) -> Cell:
        return self.cells.get(agent, {}).get(regime, Cell())

    def trust_adjust(self, agent: str, regime: str, strength: float = 1.0) -> float:
        """Shrunk multiplier in [0.4, 1.5]. 1.0 = no evidence, no opinion."""
        c = self.cell(agent, regime)
        if c.n < self.min_obs:
            return 1.0
        shrink = c.n / (c.n + 2.0 * self.min_obs)          # small-sample shrinkage
        adj = 1.0 + strength * shrink * float(np.clip(c.tstat / 3.0, -1.0, 1.0)) * 0.5
        return float(np.clip(adj, 0.4, 1.5))

    def agent_regime_report(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for agent, regimes in self.cells.items():
            out[agent] = {r: regimes[r].to_dict() for r in regimes}
        return out

    def leaderboard(self) -> List[Dict[str, Any]]:
        rows = []
        for agent, regimes in self.cells.items():
            tot = Cell()
            for c in regimes.values():
                tot.n += c.n
                tot.hits += c.hits
                tot.n_long += c.n_long
                tot.n_short += c.n_short
                tot.sum_r_long += c.sum_r_long
                tot.sum_r_short += c.sum_r_short
                tot.sum_score_r += c.sum_score_r
                tot.sum_r2 += c.sum_r2
            best = max(regimes.items(), key=lambda kv: kv[1].edge_bps) if regimes else ("-", Cell())
            rows.append({
                "agent": agent, **tot.to_dict(),
                "best_regime": best[0], "best_edge_bps": round(best[1].edge_bps, 2),
            })
        return sorted(rows, key=lambda r: -r["edge_bps"])

    def narratives(self, n: int = 6) -> List[str]:
        """Plain-English lessons, derived only from settled statistics."""
        items: List[Tuple[float, str]] = []
        for agent, regimes in self.cells.items():
            for reg, c in regimes.items():
                if c.n < self.min_obs or abs(c.edge_bps) < 1.0:
                    continue
                verb = "pays" if c.edge_bps > 0 else "hurts"
                skew = ""
                if c.hit_rate >= 0.55 and c.edge_bps < 0:
                    skew = " — right often, wrong big"
                elif c.hit_rate <= 0.45 and c.edge_bps > 0:
                    skew = " — wrong often, right big"
                text = (f"{agent} {verb} in {reg.replace('_', ' ')}: {c.edge_bps:+.0f}bps "
                        f"per {self.horizon} bars over {c.n} votes "
                        f"(hit {c.hit_rate:.0%}, t={c.tstat:+.1f}){skew}")
                items.append((abs(c.edge_bps), text))
        items.sort(key=lambda x: -x[0])
        return [t for _, t in items[:n]]

    # ------------------------------------------------------------------ io
    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizon": self.horizon,
            "settled": self.settled,
            "pending": len(self.pending),
            "last_settle_index": self.last_settle_index,
            "agents": self.agent_regime_report(),
            "leaderboard": self.leaderboard(),
            "narratives": self.narratives(),
        }

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "horizon": self.horizon, "settled": self.settled,
            "cells": {a: {r: asdict(c) for r, c in rs.items()} for a, rs in self.cells.items()},
        }
        self.path.write_text(json.dumps(payload, indent=1))

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        self.settled = int(d.get("settled", 0))
        for agent, regimes in (d.get("cells") or {}).items():
            for reg, c in regimes.items():
                try:
                    self.cells.setdefault(agent, {})[reg] = Cell(**c)
                except TypeError:
                    continue
