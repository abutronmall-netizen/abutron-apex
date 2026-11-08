"""RiskAgent — the adult in the room.

Every target weight the portfolio agent proposes must survive, in order:
    per-instrument cap -> asset-class cap -> correlation-cluster cap
    -> stop-loss override -> net/gross leverage cap
    -> portfolio vol target -> 1-day 95% VaR cap
    -> daily-loss limit & max-drawdown kill switch
It may only ever shrink risk; it can never invent exposure.
"""
from __future__ import annotations

import time
from typing import Dict, List

import numpy as np

from ..core.models import AgentRole, RiskVerdict
from ..data.base import bars_per_year
from ..risk import limits
from ..strategy import indicators as ta
from .base import Agent, Context


class RiskAgent(Agent):
    name = "risk"
    role = AgentRole.RISK

    def __init__(self, cfg, **kw):
        super().__init__(cfg, **kw)
        self.peak_equity = float(cfg["account"]["starting_equity"])
        self.day_start_equity = self.peak_equity
        self.day = None
        self.halted = False
        self.halt_reason = ""
        self._blocked: Dict[str, int] = {}
        self.history: List[dict] = []

    # ------------------------------------------------------------------
    def step(self, ctx: Context) -> None:
        self._tick()
        self.status = "active"
        r = self.cfg["risk"]
        eq = max(ctx.equity, 1e-9)
        w = dict(ctx.target_weights)
        rejected: Dict[str, str] = {}
        breaches: List[str] = []

        self.peak_equity = max(self.peak_equity, eq)
        day = int(ctx.ts // 86400)
        if day != self.day:
            self.day = day
            self.day_start_equity = eq

        # ---------- 1. kill switch -------------------------------------
        dd = 1.0 - eq / self.peak_equity if self.peak_equity > 0 else 0.0
        day_pnl = eq / self.day_start_equity - 1.0 if self.day_start_equity > 0 else 0.0
        max_dd = float(r["max_drawdown_pct"])
        max_dl = float(r["max_daily_loss_pct"])
        if dd >= max_dd and not self.halted:
            self.halted = True
            self.halt_reason = f"max drawdown {dd:.2%} >= {max_dd:.2%}"
            breaches.append(self.halt_reason)
        if day_pnl <= -max_dl:
            self.halted = True
            self.halt_reason = f"daily loss {day_pnl:.2%} <= -{max_dl:.2%}"
            breaches.append(self.halt_reason)

        verdict = RiskVerdict(weights={}, rejected=rejected, breaches=breaches)
        if self.halted:
            verdict.halted = True
            verdict.flatten = str(r.get("kill_switch_action", "flatten")) == "flatten"
            verdict.weights = {}
            self._record(ctx, verdict, dd, day_pnl)
            ctx.verdict = verdict
            ctx.target_weights = {}
            return

        # ---------- 2. per-instrument cap -------------------------------
        hard_cap = float(r["max_position_weight"])
        for s in list(w):
            cap = min(hard_cap, float(ctx.meta.get(s, {}).get("max_weight", 0.2)))
            if abs(w[s]) > cap:
                w[s] = float(np.sign(w[s]) * cap)
                rejected[s] = f"capped at {cap:.0%} instrument limit"

        # ---------- 3. asset-class caps ---------------------------------
        ac_caps = dict(r["max_asset_class_weight"])
        by_class: Dict[str, List[str]] = {}
        for s in w:
            by_class.setdefault(ctx.asset_class(s), []).append(s)
        for ac, syms in by_class.items():
            cap = float(ac_caps.get(ac, 0.5))
            g = sum(abs(w[s]) for s in syms)
            if g > cap and g > 0:
                k = cap / g
                for s in syms:
                    w[s] *= k
                breaches.append(f"{ac} gross {g:.0%} -> {cap:.0%}")

        # ---------- 4. correlation clusters ------------------------------
        syms = [s for s in w]
        if len(syms) > 1:
            mat_syms, cov, _bpy = ctx.cov(240)
            if mat_syms:
                cl = limits.corr_clusters(mat_syms, cov, float(r["corr_cluster_limit"]))
                cluster_cap = float(r["cluster_weight_limit"])
                for group in cl:
                    g = sum(abs(w.get(s, 0.0)) for s in group)
                    if g > cluster_cap and g > 0:
                        k = cluster_cap / g
                        for s in group:
                            if s in w:
                                w[s] *= k
                        breaches.append(f"cluster {group[:3]} scaled {k:.2f}x")

        # ---------- 4b. stop cooldown (no revenge re-entry) --------------
        for s, until in list(self._blocked.items()):
            if ctx.index < until:
                if s in w and abs(w[s]) > 0:
                    w[s] = 0.0
                    rejected[s] = f"cooldown {until - ctx.index} bars after stop"
            else:
                del self._blocked[s]

        # ---------- 5. stop-loss override --------------------------------
        atr_mult = float(r.get("stop_atr_mult", 2.5))
        eq = max(ctx.equity, 1e-9)
        for s, p in ctx.broker.positions.items():
            if abs(p.qty) < 1e-12 or p.avg_price <= 0:
                continue
            a = ctx.history.arrays(s, 40)
            if len(a["c"]) < 20:
                continue
            atr_v = float(ta.atr(a["h"], a["l"], a["c"], 14)[-1])
            if atr_v <= 0:
                continue
            adverse = (p.last_price - p.avg_price) * np.sign(p.qty)
            if adverse < -atr_mult * atr_v:
                w[s] = 0.0
                self._blocked[s] = ctx.index + int(r.get("stop_cooldown_bars", 12))
                rejected[s] = f"stop hit ({adverse / atr_v:+.1f} ATR): flat + cooldown"

        # ---------- 6. net / gross caps ----------------------------------
        max_gross = float(r["max_gross_leverage"])
        max_net = float(r["max_net_exposure"])
        g = limits.gross(w)
        if g > max_gross:
            w = limits.scale_weights(w, max_gross / g)
            breaches.append(f"gross {g:.2f}x -> {max_gross:.2f}x")
        n = limits.net(w)
        if abs(n) > max_net:
            k = max_net / abs(n)
            # scale only the dominant side to preserve hedges
            pos_sum = sum(v for v in w.values() if v > 0)
            neg_sum = -sum(v for v in w.values() if v < 0)
            if n > 0 and pos_sum > 0:
                f = max(0.0, (max_net + neg_sum) / pos_sum)
                w = {s: (v * f if v > 0 else v) for s, v in w.items()}
            elif n < 0 and neg_sum > 0:
                f = max(0.0, (max_net + pos_sum) / neg_sum)
                w = {s: (v * f if v < 0 else v) for s, v in w.items()}
            breaches.append(f"net {n:+.2f} -> cap {max_net:.2f}")

        # ---------- 7. vol target + VaR ----------------------------------
        lo_band, hi_band = self.cfg["risk"]["vol_target_band"]
        var_val, pv = 0.0, 0.0
        if w:
            msyms, cov, _bpy = ctx.cov(240)
            if msyms:
                wv = np.array([w.get(s, 0.0) for s in msyms])
                pv = limits.portfolio_vol(wv, cov)
                if pv > float(hi_band) and pv > 0:
                    k = float(hi_band) / pv
                    w = limits.scale_weights(w, k)
                    breaches.append(f"port vol {pv:.0%} -> {hi_band:.0%}")
                wv = np.array([w.get(s, 0.0) for s in msyms])
                var_val = limits.parametric_var(wv, cov, float(r["var_confidence"]))
                if var_val > float(r["var_limit_pct"]) and var_val > 0:
                    k = float(r["var_limit_pct"]) / var_val
                    w = limits.scale_weights(w, k)
                    breaches.append(f"VaR {var_val:.2%} -> {r['var_limit_pct']:.2%}")

        for s, v in w.items():
            if abs(v) < 1e-4:
                w[s] = 0.0

        verdict.weights = {s: round(v, 5) for s, v in w.items() if abs(v) > 1e-4}
        verdict.var_95 = var_val
        verdict.gross = limits.gross(verdict.weights)
        verdict.net = limits.net(verdict.weights)
        self._record(ctx, verdict, dd, day_pnl)
        ctx.verdict = verdict
        ctx.target_weights = dict(verdict.weights)

    # ------------------------------------------------------------------
    def _record(self, ctx: Context, v: RiskVerdict, dd: float, day_pnl: float) -> None:
        self.history.append({
            "ts": ctx.ts,
            "equity": round(ctx.equity, 2),
            "drawdown": round(dd, 4),
            "day_pnl": round(day_pnl, 4),
            "var_95": round(v.var_95, 5),
            "gross": round(v.gross, 4),
            "net": round(v.net, 4),
            "breaches": v.breaches[-6:],
            "halted": v.halted,
        })
        if len(self.history) > 5000:
            del self.history[:-5000]

    def resume(self) -> None:
        self.halted = False
        self.halt_reason = ""
        self._blocked: Dict[str, int] = {}
        self.peak_equity = self.peak_equity  # keep high-water mark

    def metrics(self) -> dict:
        if not self.history:
            return {}
        last = self.history[-1]
        return {
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "drawdown": last["drawdown"],
            "day_pnl": last["day_pnl"],
            "var_95": last["var_95"],
            "gross": last["gross"],
            "net": last["net"],
            "peak_equity": round(self.peak_equity, 2),
            "breaches": last["breaches"],
        }
