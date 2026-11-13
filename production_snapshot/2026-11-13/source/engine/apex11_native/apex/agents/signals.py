"""Signal agents. Each is an independent, stateless-with-respect-to-others opinion
generator; the PortfolioAgent decides how much to trust each one given the regime."""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..core.models import Signal
from ..strategy import indicators as ta
from .base import Context, SignalAgent


class TrendAgent(SignalAgent):
    name = "trend"

    def generate(self, ctx: Context, symbol: str) -> Optional[Signal]:
        s = self.cfg["agents"]["trend"]
        fast_n, slow_n = int(s.get("fast", 20)), int(s.get("slow", 55))
        a = ctx.history.arrays(symbol, slow_n + 80)
        if len(a["c"]) < slow_n + 10:
            return None
        c = a["c"]
        f, sl = ta.ema(c, fast_n)[-1], ta.ema(c, slow_n)[-1]
        atr_v = float(ta.atr(a["h"], a["l"], c, int(s.get("atr_period", 14)))[-1])
        if atr_v <= 0:
            return None
        norm = (f - sl) / atr_v
        if abs(norm) < 0.15:
            return None
        adx_v = float(ta.adx(a["h"], a["l"], c, 14)[-1])
        strength = float(np.clip(abs(norm) / 1.5, 0, 1) * np.clip(adx_v / 45.0, 0.2, 1.0))
        return Signal(
            symbol=symbol, direction=float(np.sign(norm)), strength=strength,
            agent=self.name, horizon="swing",
            rationale=f"EMA{fast_n}/EMA{slow_n} spread {norm:+.2f} ATR, ADX {adx_v:.0f}",
        )


class MeanReversionAgent(SignalAgent):
    name = "meanrev"

    def generate(self, ctx: Context, symbol: str) -> Optional[Signal]:
        s = self.cfg["agents"]["mean_reversion"]
        look = int(s.get("lookback", 40))
        entry = float(s.get("entry_z", 1.6))
        a = ctx.history.arrays(symbol, look + 60)
        if len(a["c"]) < look + 5:
            return None
        c = a["c"]
        z = float(ta.zscore(c, look)[-1])
        if abs(z) < entry:
            return None
        r = float(ta.rsi(c, 14)[-1])
        confirm = (z > 0 and r > 60) or (z < 0 and r < 40) or abs(z) > entry * 1.5
        if not confirm:
            return None
        strength = float(np.clip((abs(z) - entry) / (2 * entry) + 0.25, 0, 1))
        return Signal(
            symbol=symbol, direction=float(-np.sign(z)), strength=strength,
            agent=self.name, horizon="mean-reversion",
            rationale=f"z={z:+.2f} vs {look}-bar mean, RSI {r:.0f}",
        )


class BreakoutAgent(SignalAgent):
    name = "breakout"

    def generate(self, ctx: Context, symbol: str) -> Optional[Signal]:
        s = self.cfg["agents"]["breakout"]
        ch = int(s.get("channel", 55))
        buf = float(s.get("atr_buffer", 0.35))
        a = ctx.history.arrays(symbol, ch + 80)
        if len(a["c"]) < ch + 5:
            return None
        atr_v = float(ta.atr(a["h"], a["l"], a["c"], int(s.get("atr_period", 14)))[-1])
        if atr_v <= 0:
            return None
        px = a["c"][-1]
        # previous bar's channel => no lookahead, no full-array allocation
        upper = float(a["h"][-ch - 1:-1].max())
        lower = float(a["l"][-ch - 1:-1].min())
        if px > upper + buf * atr_v:
            d = 1.0
            dist = (px - upper) / atr_v
        elif px < lower - buf * atr_v:
            d = -1.0
            dist = (lower - px) / atr_v
        else:
            return None
        strength = float(np.clip(dist / 2.0, 0.15, 1.0))
        side = "high" if d > 0 else "low"
        return Signal(
            symbol=symbol, direction=d, strength=strength, agent=self.name,
            horizon="momentum",
            rationale=f"{ch}-bar {side} breakout ({dist:.2f} ATR beyond channel)",
        )


class CarryAgent(SignalAgent):
    """Structural-drift agent.

    Deriv's Boom/Crash synthetics are engineered with an asymmetric step: a slow
    grind in one direction interrupted by rare violent spikes in the other. The
    drift is real, the tail is lethal -> the agent votes WITH the drift and the
    RiskAgent caps the residual skew exposure.
    """

    name = "carry"

    def generate(self, ctx: Context, symbol: str) -> Optional[Signal]:
        model = str(ctx.meta.get(symbol, {}).get("synthetic_model", ""))
        min_strength = float(self.cfg["agents"]["carry"].get("min_strength", 0.25))
        if model == "boom":
            d, why = -1.0, "Boom: typical downward drift, upward-spike tail"
        elif model == "crash":
            d, why = 1.0, "Crash: typical upward drift, downward-spike tail"
        elif model == "step":
            d, why = 0.0, ""
        else:
            return None
        if d == 0.0:
            return None
        a = ctx.history.arrays(symbol, 500)
        if len(a["c"]) < 100:
            return None
        r = np.diff(a["c"]) / np.where(a["c"][:-1] == 0, np.nan, a["c"][:-1])
        r = np.nan_to_num(r)
        mu = float(np.mean(r) * len(r))
        sd = float(np.std(r) + 1e-12)
        tstat = mu / sd * np.sqrt(len(r))
        strength = float(np.clip(abs(tstat) / 4.0, min_strength, 0.85))
        # the drift must actually agree with the engineered direction
        if np.sign(mu) != d and abs(tstat) > 1.5:
            strength *= 0.5
        return Signal(
            symbol=symbol, direction=d, strength=strength, agent=self.name,
            horizon="structural", rationale=f"{why} (t={tstat:+.1f})",
        )
