"""Deterministic synthetic market generator.

Produces a multi-asset OHLCV panel that behaves like the real thing:
  * a shared market risk factor  -> realistic cross-asset correlation
  * slow regimes (bull / bear / chop) with persistent drift
  * volatility clustering (log-vol AR(1)) and fat tails (student-t shocks)
  * asset-class session masks (equities/FX only trade part of the day)
  * Deriv-style synthetic indices:
        volatility (R_*)  pure random walk with scaled vol, 24/7
        boom / crash      one-directional steps + rare violent spikes
        step              discretised random walk (1-in-5 steps)
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from ..config import Cfg
from ..core.models import Bar
from .base import Panel, bars_per_year, in_session

SUBSTEPS = 4


def _ar1(n: int, rho: float, sd: float, rng: np.random.Generator, start: float = 0.0) -> np.ndarray:
    eps = rng.normal(0.0, sd, n)
    out = np.empty(n)
    x = start
    for i in range(n):
        x = rho * x + eps[i]
        out[i] = x
    return out


def _regime_path(n: int, rng: np.random.Generator, persistence: float = 0.9998) -> np.ndarray:
    """-1 bear / 0 chop / +1 bull, sticky Markov chain."""
    states = np.zeros(n, dtype=np.int8)
    s = int(rng.choice([-1, 0, 1]))
    for i in range(n):
        if rng.random() > persistence:
            s = int(rng.choice([-1, 0, 1], p=[0.34, 0.32, 0.34]))
        states[i] = s
    return states


def make_panel(
    cfg: Cfg,
    n_bars: int = 5000,
    seed: Optional[int] = None,
    start_ts: float = 1_704_067_200.0,  # 2024-01-01 UTC
    bar_seconds: int = 3600,
) -> Panel:
    seed = int(cfg["system"].get("seed", 7) if seed is None else seed)
    universe = cfg["universe"]

    rng = np.random.default_rng(seed)
    n_sub = n_bars * SUBSTEPS

    ts = start_ts + np.arange(n_bars) * bar_seconds

    # ---- shared market factor (student-t shocks => fat tails) -------------
    factor = rng.standard_t(df=5, size=n_sub) / np.sqrt(5 / 3)
    mkt_vol = np.exp(_ar1(n_sub, 0.9995, 0.02, rng))          # vol clustering
    drift_map = {-1: -2.50, 0: 0.0, 1: 2.50}   # x annual_vol => regime Sharpe +/-2.5

    out = {"o": {}, "h": {}, "l": {}, "c": {}, "v": {}, "active": {}}
    asset_class: Dict[str, str] = {}

    for u in universe:
        sym = u["symbol"]
        ac = str(u["asset_class"])
        asset_class[sym] = ac
        model = str(u.get("synthetic_model", "trend"))
        ann_vol = float(u.get("annual_vol", 0.2))
        px0 = float(u.get("ref_price", 100.0))
        bpy = bars_per_year(ac)
        dt = 1.0 / bpy
        dt_sub = dt / SUBSTEPS

        # correlation structure
        if ac == "crypto":
            beta = 1.25
        elif ac == "us_equity":
            beta = 0.95
        elif ac == "fx_index":
            beta = -0.20
        else:
            beta = 0.0  # synthetics are independent of the real market factor

        regime = _regime_path(n_sub, rng)          # each asset has its own cycle
        idio = rng.standard_t(df=6, size=n_sub) / np.sqrt(6 / 4)
        z = beta * factor + np.sqrt(max(0.0, 1 - beta ** 2)) * idio
        sigma = ann_vol * mkt_vol

        if model == "volatility":
            # pure martingale random walk, vol exactly as advertised
            ret = sigma * np.sqrt(dt_sub) * z
        elif model in ("boom", "crash"):
            sign = 1.0 if model == "boom" else -1.0
            grind = 0.50 * sign                                          # ~50%/yr grind
            ret = grind * dt_sub + sigma * 0.22 * np.sqrt(dt_sub) * z
            # ~25 violent spikes/yr against the grind (the reason you size down)
            spike_hits = rng.random(n_sub) < (1.0 / 1400.0)
            spike_mag = rng.gamma(2.0, 0.0045, n_sub)
            ret = ret - sign * spike_hits * spike_mag
        elif model == "step":
            step_sz = 0.0009 * ann_vol / 0.35
            move = rng.random(n_sub) < 0.2
            ret = np.where(move, rng.choice([-1.0, 1.0], n_sub) * step_sz, 0.0)
            ret = ret + sigma * 0.02 * np.sqrt(dt_sub) * z
        else:
            # regime-switching mean-reverting trend model:
            #   trend regimes  -> strong drift, almost no pull  (trend followers eat)
            #   chop regime    -> zero drift, strong OU pull to a slow anchor
            #                     (mean reversion eat) -- both real edges exist
            x = np.log(px0)
            anchor = x
            hl_days = 10.0
            alpha = 1.0 - np.exp(-dt_sub / (hl_days / 365.25))
            xs = np.empty(n_sub)
            sqrt_dt = np.sqrt(dt_sub)
            for t in range(n_sub):
                reg = int(regime[t])
                mu = drift_map[reg] * ann_vol          # annual drift
                kappa = 1.0 if reg != 0 else 800.0     # OU pull / year (none in trends)
                x = x + (mu - kappa * (x - anchor)) * dt_sub + sigma[t] * sqrt_dt * z[t]
                anchor += (x - anchor) * alpha
                xs[t] = x
            ret = np.diff(np.concatenate([[0.0], xs - xs[0]]))
        logp = np.cumsum(ret)
        px_sub = px0 * np.exp(logp)

        # ---- fold substeps into OHLC bars -------------------------------
        blocks = px_sub.reshape(n_bars, SUBSTEPS)
        o = np.concatenate([[px0], blocks[:, 0][:-1]])
        c = blocks[:, -1]
        h = blocks.max(axis=1)
        l = blocks.min(axis=1)
        h = np.maximum.reduce([h, o, c])
        l = np.minimum.reduce([l, o, c])

        bar_ret = np.abs(np.diff(np.concatenate([[px0], c]))) / np.maximum(px0, 1e-9)
        v = np.exp(rng.normal(0, 0.6, n_bars)) * (1.0 + 400.0 * bar_ret) * 1000.0

        hours = ((ts // 3600) % 24).astype(int)
        act = np.array([in_session(ac, int(h)) for h in hours])

        out["o"][sym], out["h"][sym], out["l"][sym] = o, h, l
        out["c"][sym], out["v"][sym], out["active"][sym] = c, v, act

    return Panel(
        symbols=[u["symbol"] for u in universe], ts=ts,
        o=out["o"], h=out["h"], l=out["l"], c=out["c"], v=out["v"],
        active=out["active"], asset_class=asset_class,
    )


class SyntheticSource:
    """Infinite synthetic stream (used by the live paper-trading loop)."""

    name = "synthetic"

    def __init__(self, cfg: Cfg, seed: Optional[int] = None, bar_seconds: int = 3600) -> None:
        self.cfg = cfg
        self.seed = int(cfg["system"].get("seed", 7) if seed is None else seed)
        self.bar_seconds = bar_seconds
        self._panel: Optional[Panel] = None
        self._cursor = 0
        self._chunk = 0

    def _regenerate(self, n: int = 1200) -> None:
        p = make_panel(
            self.cfg, n_bars=n, seed=self.seed + self._chunk * 7919,
            start_ts=1_760_000_000.0 + self._chunk * n * self.bar_seconds,
            bar_seconds=self.bar_seconds,
        )
        self._chunk += 1
        self._panel, self._cursor = p, 0

    def warmup(self, n: int) -> Dict[str, List[Bar]]:
        # continuous history: generate a long panel and keep the tail
        p = make_panel(self.cfg, n_bars=n + 200, seed=self.seed, bar_seconds=self.bar_seconds)
        hist: Dict[str, List[Bar]] = {
            s: [p.bar(s, i) for i in range(len(p) - n, len(p))] for s in p.symbols
        }
        self._regenerate()
        return hist

    def stream(self):
        while True:
            if self._panel is None or self._cursor >= len(self._panel) - 1:
                self._regenerate()
            i = self._cursor
            self._cursor += 1
            yield {s: self._panel.bar(s, i) for s in self._panel.symbols if self._panel.active[s][i]}
