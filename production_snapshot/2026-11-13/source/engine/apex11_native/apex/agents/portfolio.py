"""PortfolioAgent — fuses the signal ensemble into target weights.

Regime-conditional trust is the whole idea: mean-reversion is a genius in a range
and a liability in a trend, so the ensemble re-weights itself every bar.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

import numpy as np

from ..core.models import AgentRole, Regime
from ..data.base import annualisation_from_ts, bars_per_year
from ..risk import limits
from .base import Agent, Context

REGIME_TRUST: Dict[Regime, Dict[str, float]] = {
    Regime.TREND_UP:    {"trend": 0.60, "breakout": 0.30, "meanrev": 0.50, "carry": 0.45},
    Regime.TREND_DOWN:  {"trend": 0.60, "breakout": 0.30, "meanrev": 0.50, "carry": 0.45},
    Regime.RANGE:       {"meanrev": 1.00, "trend": 0.10, "breakout": 0.15, "carry": 0.35},
    Regime.HIGH_VOL:    {"meanrev": 0.80, "trend": 0.20, "breakout": 0.20, "carry": 0.30},
    Regime.UNKNOWN:     {"meanrev": 0.35, "trend": 0.25, "breakout": 0.25, "carry": 0.30},
}


class PortfolioAgent(Agent):
    name = "portfolio"
    role = AgentRole.PORTFOLIO

    def __init__(self, cfg, **kw):
        super().__init__(cfg, **kw)
        self._prev: Dict[str, float] = {}
        self.attribution: Dict[str, float] = defaultdict(float)
        # online agent reputation: EWMA of normalised score x realised return
        self.reputation: Dict[str, float] = defaultdict(lambda: 0.02)
        self.memory = None                      # injected by ApexEngine
        self._last_scores: Dict[str, Dict[str, float]] = {}
        self._last_prices: Dict[str, float] = {}

    # ------------------------------------------------------------------
    def _update_reputation(self, ctx: Context) -> None:
        """Learn which agent is actually working, per instrument, online."""
        if not self._last_scores:
            return
        decay = 0.97
        for sym, agents in self._last_scores.items():
            px = ctx.history.last_price(sym)
            px0 = self._last_prices.get(sym, px)
            if px0 <= 0 or px <= 0:
                continue
            ret = px / px0 - 1.0
            rs = ctx.regimes.get(sym)
            bpy = bars_per_year(ctx.asset_class(sym))
            sigma_bar = (rs.realised_vol if rs and rs.realised_vol > 0 else
                         float(ctx.meta.get(sym, {}).get("annual_vol", 0.2))) / np.sqrt(bpy)
            if sigma_bar <= 0:
                continue
            z = float(np.clip(ret / sigma_bar, -4, 4))
            for agent, score in agents.items():
                key = f"{agent}:{sym}"
                contrib = 0.25 * float(score) * z
                self.reputation[key] = decay * self.reputation[key] + (1 - decay) * contrib
                gkey = f"{agent}:*"
                self.reputation[gkey] = decay * self.reputation[gkey] + (1 - decay) * contrib

    def skill(self, agent: str, symbol: str) -> float:
        """Trust multiplier in [0.1, 1.6] from learned reputation (regime-agnostic prior)."""
        sym_ic = self.reputation.get(f"{agent}:{symbol}", self.reputation.get(f"{agent}:*", 0.02))
        return float(np.clip(0.55 + 4.0 * sym_ic, 0.10, 1.60))

    def step(self, ctx: Context) -> None:
        self._tick()
        self.status = "active"
        self._update_reputation(ctx)
        f = self.cfg["agents"]["fusion"]
        min_w = float(f.get("min_abs_weight", 0.01))
        smooth = float(np.clip(float(f.get("smoothing", 0.5)), 0.0, 1.0))
        influence = float(np.clip(float(f.get("memory_influence", 0.0)), 0.0, 1.0))
        target_vol = float(self.cfg["risk"]["target_annual_vol"])

        every = max(1, int(f.get("rebalance_every", 1)))
        if ctx.index % every != 0 and self._prev:
            ctx.raw_weights = dict(self._prev)
            ctx.target_weights = dict(self._prev)
            ctx.note(f"holding book (re-optimise every {every} bars)")
            return

        by_sym: Dict[str, List] = defaultdict(list)
        for sig in ctx.signals:
            by_sym[sig.symbol].append(sig)

        raw: Dict[str, float] = {}
        for sym, sigs in by_sym.items():
            rs = ctx.regimes.get(sym)
            trust = REGIME_TRUST.get(rs.regime if rs else Regime.UNKNOWN, REGIME_TRUST[Regime.UNKNOWN])
            num = den = 0.0
            reg_name = (rs.regime.value if rs else Regime.UNKNOWN.value)
            for s in sigs:
                w = trust.get(s.agent, 0.0) * self.skill(s.agent, sym)
                if self.memory is not None and influence > 0:
                    adj = self.memory.trust_adjust(s.agent, reg_name)
                    w *= 1.0 + influence * (adj - 1.0)
                num += w * s.score
                den += w
            if den <= 1e-9:
                continue
            score = float(np.clip(num / max(den, 1.0), -1.0, 1.0))
            if abs(score) < 0.05:
                continue

            meta = ctx.meta.get(sym, {})
            max_w = float(meta.get("max_weight", 0.2))
            rv = rs.realised_vol if rs and rs.realised_vol > 0 else float(meta.get("annual_vol", 0.2))
            # conviction sets the *ratio* of the cap; portfolio vol targeting
            # (below) decides the absolute size. Avoid double vol-scaling.
            vol_scalar = float(np.clip(0.20 / max(rv, 1e-6), 0.5, 1.5))
            w = score * max_w * vol_scalar
            w = float(np.clip(w, -max_w, max_w))
            if abs(w) >= min_w:
                raw[sym] = w

        # ---- portfolio-level vol targeting -------------------------------
        raw = self._vol_target(ctx, raw, target_vol)

        # ---- EWMA smoothing (turnover control) ---------------------------
        syms = set(raw) | set(self._prev)
        weights: Dict[str, float] = {}
        for s in syms:
            new = raw.get(s, 0.0)
            old = self._prev.get(s, 0.0)
            w = (1 - smooth) * new + smooth * old
            if abs(w) >= min_w:
                weights[s] = w
        self._prev = weights

        # expected move over the rebalance horizon, in bps (used by the cost gate)
        every = max(1, int(f.get("rebalance_every", 1)))
        edge_bps = {}
        for sym, w in weights.items():
            rs = ctx.regimes.get(sym)
            rv = rs.realised_vol if rs else float(ctx.meta.get(sym, {}).get("annual_vol", 0.2))
            bpy = bars_per_year(ctx.asset_class(sym))
            score = abs(raw.get(sym, 0.0)) / max(float(ctx.meta.get(sym, {}).get("max_weight", 0.2)), 1e-6)
            edge_bps[sym] = float(score * rv * np.sqrt(every / bpy) * 1e4)
        ctx.extras["edge_bps"] = edge_bps

        # snapshot for next bar's reputation update
        self._last_scores = {sym: {s.agent: s.score for s in sigs} for sym, sigs in by_sym.items()}
        self._last_prices = {sym: ctx.history.last_price(sym) for sym in by_sym}

        ctx.raw_weights = weights
        ctx.target_weights = dict(weights)
        ctx.extras["ensemble"] = {
            s: {g: round(v, 3) for g, v in meta.items()}
            for s, meta in ((s, REGIME_TRUST.get((ctx.regimes.get(s).regime if s in ctx.regimes else Regime.UNKNOWN),
                                                 REGIME_TRUST[Regime.UNKNOWN]))
                            for s in by_sym)
        }

    # ------------------------------------------------------------------
    def _vol_target(self, ctx: Context, weights: Dict[str, float], target_vol: float) -> Dict[str, float]:
        """Scale the book so *realised* portfolio vol tracks the target.

        Using the portfolio's own return stream is far more robust than trusting a
        covariance estimate built from short, unevenly-spaced samples; the model
        covariance is still used for VaR and cluster limits.
        """
        if not weights:
            return weights
        eq_hist = ctx.broker.equity_curve()
        if len(eq_hist) > 60:
            window = eq_hist[-260:]
            eq = np.array([v for _, v in window])
            r = np.diff(eq) / np.where(eq[:-1] == 0, np.nan, eq[:-1])
            r = np.nan_to_num(r)
            bpy = annualisation_from_ts([t for t, _ in window])
            realised = float(np.std(r) * np.sqrt(bpy))
            if realised > 1e-6:
                scale = float(np.clip(target_vol / realised, 0.2, 5.0))
                out = {s: v * scale for s, v in weights.items()}
                for s in out:
                    cap = float(ctx.meta.get(s, {}).get("max_weight", 0.2))
                    out[s] = float(np.clip(out[s], -cap, cap))
                ctx.extras["realised_vol"] = round(realised, 4)
                ctx.extras["vol_scale"] = round(scale, 3)
                ctx.extras["vol_bpy"] = round(bpy, 1)
                return out
        syms, cov, bpy = ctx.cov(240)
        if not syms:
            return weights
        w = np.array([weights.get(s, 0.0) for s in syms])
        pv = limits.portfolio_vol(w, cov)
        lo, hi = self.cfg["risk"]["vol_target_band"]
        if pv <= 1e-9:
            return weights
        scale = float(np.clip(target_vol / pv, 0.0, 6.0))
        if lo <= pv <= hi:
            scale = float(np.clip(scale, 0.85, 1.15))  # already inside band: nudge only
        out = {s: weights.get(s, 0.0) * scale for s in weights}
        # never let the scaler push an instrument past its own cap
        for s in out:
            cap = float(ctx.meta.get(s, {}).get("max_weight", 0.2))
            out[s] = float(np.clip(out[s], -cap, cap))
        ctx.extras["pre_risk_vol"] = round(pv, 4)
        ctx.extras["vol_scale"] = round(scale, 3)
        return out
