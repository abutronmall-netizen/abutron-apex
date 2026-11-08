"""RegimeAgent — classifies each instrument's state so the ensemble can re-weight itself."""
from __future__ import annotations

import numpy as np

from ..core.models import AgentRole, Regime, RegimeState
from ..data.base import bars_per_year
from ..strategy import indicators as ta
from .base import Agent, Context


class RegimeAgent(Agent):
    name = "regime"
    role = AgentRole.REGIME

    def step(self, ctx: Context) -> None:
        self._tick()
        self.status = "active"
        s = self.cfg["agents"]["regime"]
        look = int(s.get("lookback", 240))
        adx_n = int(s.get("adx_period", 14))
        thr = float(s.get("adx_trend_threshold", 22.0))
        vol_hi = float(s.get("vol_percentile_high", 0.75))

        for sym in ctx.history.symbols:
            if ctx.history.n(sym) < 60:
                continue
            a = ctx.history.arrays(sym, look)
            c, h, l = a["c"], a["h"], a["l"]
            bpy = bars_per_year(ctx.asset_class(sym))

            adx_v = float(ta.adx(h[-80:], l[-80:], c[-80:], adx_n)[-1])
            slp = float(ta.slope(c[-60:], min(55, len(c) - 2))[-1])

            # realised vol + its percentile, vectorised over the last 120 windows
            r = np.diff(c) / np.where(c[:-1] == 0, np.nan, c[:-1])
            r = np.nan_to_num(r)
            win = min(30, len(r))
            if len(r) >= win + 5:
                rv_series = np.lib.stride_tricks.sliding_window_view(r, win).std(axis=1) * np.sqrt(bpy)
            else:
                rv_series = np.array([r.std() * np.sqrt(bpy)])
            rv = float(rv_series[-1])
            vol_pct = float((rv_series[-look:] <= rv).mean())

            if vol_pct > vol_hi and adx_v < thr:
                regime, conf = Regime.HIGH_VOL, min(1.0, vol_pct)
            elif adx_v > thr and slp > 0:
                regime, conf = Regime.TREND_UP, min(1.0, adx_v / 60.0)
            elif adx_v > thr and slp < 0:
                regime, conf = Regime.TREND_DOWN, min(1.0, adx_v / 60.0)
            elif adx_v <= thr:
                regime, conf = Regime.RANGE, min(1.0, 1.0 - adx_v / max(thr, 1e-9))
            else:
                regime, conf = Regime.UNKNOWN, 0.2

            ctx.regimes[sym] = RegimeState(
                symbol=sym, regime=regime, adx=adx_v, slope=slp,
                vol_pct=vol_pct, realised_vol=rv, confidence=float(np.clip(conf, 0.0, 1.0)),
            )
