"""Optional LLM advisory layer.

Design constraint: the LLM is a *risk-reducing* agent, never a source of alpha.
It can inspect state through tools and may only (a) cut overall risk and (b) veto
individual instruments. Its output is clipped by hard guardrails before it ever
touches a weight, so a hallucinating model can lose you opportunity — never the
account.

Works with any OpenAI-compatible endpoint (OpenAI, xAI, Groq, Ollama, vLLM...).
If no API key is present the advisor degrades to a deterministic heuristic so the
agent pipeline stays intact and observable.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

import numpy as np

from ..agents.base import Context


SYSTEM_PROMPT = """You are APEX-ADVISOR, a risk officer on an automated multi-asset desk.
Your ONLY permitted actions are:
  1. reduce overall portfolio risk by returning a scale in [min_scale, 1.0]
  2. veto specific instruments (they will be flattened)
You may NOT increase exposure, add instruments, or change direction.
Use the tools to inspect the book. Be terse and evidence-driven.
When done, reply with JSON only:
{"scale": <float>, "vetoes": [<symbol>, ...], "note": "<one sentence>"}
"""

TOOLS = [
    {"type": "function", "function": {
        "name": "get_portfolio_state",
        "description": "Current equity, positions, exposures and drawdown.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_market_snapshot",
        "description": "Per-symbol regime, realised vol, ADX and signal votes.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_risk_limits",
        "description": "Active risk limits and current breach list.",
        "parameters": {"type": "object", "properties": {}}}},
]


class LlmAdvisor:
    name = "advisor"

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        c = cfg["llm"]
        self.enabled = bool(c.get("enabled", False))
        self.model = str(c.get("model", "gpt-4o-mini"))
        self.base_url = str(c.get("base_url", "https://api.openai.com/v1")).rstrip("/")
        self.temperature = float(c.get("temperature", 0.1))
        self.timeout = float(c.get("timeout_s", 20))
        self.min_scale = max(0.0, 1.0 - float(c.get("max_risk_scale", 0.6)))
        self.cooldown = int(c.get("cooldown_bars", 12))
        self.api_key = os.environ.get("APEX_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.mode = "llm" if (self.enabled and self.api_key) else "heuristic"
        self._last_call = -10**9
        self.last_result: Dict[str, Any] = {}
        self.calls = 0
        self.errors = 0

    # ------------------------------------------------------------------ public
    def should_consult(self, ctx: Context) -> bool:
        if not self.enabled:
            return False
        return (ctx.index - self._last_call) >= self.cooldown

    def consult(self, ctx: Context) -> Dict[str, Any]:
        self._last_call = ctx.index
        if self.mode == "llm":
            try:
                res = self._llm_loop(ctx)
            except Exception as exc:  # network, auth, rate limit -> fail safe
                self.errors += 1
                res = {"scale": 1.0, "vetoes": [], "note": f"LLM unavailable ({type(exc).__name__}): no change",
                       "mode": "llm-error"}
        else:
            res = self._heuristic(ctx)
        res["scale"] = float(np.clip(res.get("scale", 1.0), self.min_scale, 1.0))
        res["vetoes"] = [v for v in res.get("vetoes", []) if v in ctx.meta]
        res["mode"] = res.get("mode", self.mode)
        self.last_result = res
        self.calls += 1
        return res

    def describe(self) -> Dict[str, Any]:
        return {"name": self.name, "mode": self.mode, "enabled": self.enabled,
                "calls": self.calls, "errors": self.errors, "last": self.last_result}

    # ------------------------------------------------------------------ tools
    def _tool_state(self, ctx: Context) -> Dict[str, Any]:
        b = ctx.broker
        return {
            "equity": round(b.equity, 2),
            "cash": round(b.cash, 2),
            "gross_leverage": round(b.gross_exposure / max(b.equity, 1e-9), 3),
            "positions": {s: round(p.notional / max(b.equity, 1e-9), 3)
                          for s, p in b.positions.items() if abs(p.qty) > 1e-12},
            "target_weights": {k: round(v, 3) for k, v in ctx.target_weights.items()},
        }

    def _tool_market(self, ctx: Context) -> Dict[str, Any]:
        out = {}
        for s, r in ctx.regimes.items():
            votes = [x for x in ctx.signals if x.symbol == s]
            out[s] = {
                "regime": r.regime.value,
                "realised_vol": round(r.realised_vol, 3),
                "adx": round(r.adx, 1),
                "vol_pct": round(r.vol_pct, 2),
                "votes": {v.agent: round(v.score, 2) for v in votes},
            }
        return out

    def _tool_limits(self, ctx: Context) -> Dict[str, Any]:
        v = ctx.verdict
        return {
            "limits": {k: self.cfg["risk"][k] for k in
                       ("target_annual_vol", "max_gross_leverage", "max_drawdown_pct",
                        "max_daily_loss_pct", "var_limit_pct")},
            "breaches": (v.breaches if v else []),
            "var_95": round(v.var_95, 4) if v else 0.0,
        }

    def _dispatch(self, name: str, ctx: Context) -> Any:
        return {
            "get_portfolio_state": lambda: self._tool_state(ctx),
            "get_market_snapshot": lambda: self._tool_market(ctx),
            "get_risk_limits": lambda: self._tool_limits(ctx),
        }.get(name, lambda: {"error": "unknown tool"})()

    # ------------------------------------------------------------------ llm
    def _chat(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        body = json.dumps({
            "model": self.model, "messages": messages, "tools": TOOLS,
            "tool_choice": "auto", "temperature": self.temperature,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def _llm_loop(self, ctx: Context) -> Dict[str, Any]:
        ctx_summary = (
            f"bar={ctx.index} equity={ctx.equity:,.0f} "
            f"gross={ctx.verdict.gross if ctx.verdict else 0:.2f} "
            f"var95={ctx.verdict.var_95 if ctx.verdict else 0:.3f} "
            f"min_scale={self.min_scale:.2f}"
        )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT + f"\n(min_scale={self.min_scale:.2f})"},
            {"role": "user", "content": f"Review the book. Context: {ctx_summary}"},
        ]
        for _ in range(4):
            resp = self._chat(messages)
            msg = resp["choices"][0]["message"]
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                return self._parse(msg.get("content") or "")
            for call in calls:
                fn = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._dispatch(fn, ctx)
                messages.append({
                    "role": "tool", "tool_call_id": call.get("id", fn),
                    "content": json.dumps(result, default=str)[:6000],
                })
        return {"scale": 1.0, "vetoes": [], "note": "advisor loop exhausted; no change"}

    @staticmethod
    def _parse(text: str) -> Dict[str, Any]:
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "", 1).strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            s = text.find("{")
            e = text.rfind("}")
            obj = json.loads(text[s:e + 1]) if s >= 0 and e > s else {}
        return {
            "scale": float(obj.get("scale", 1.0)),
            "vetoes": list(obj.get("vetoes", []) or []),
            "note": str(obj.get("note", ""))[:280],
        }

    # ------------------------------------------------------------------ fallback
    def _heuristic(self, ctx: Context) -> Dict[str, Any]:
        """Deterministic stand-in: cut risk on signal disagreement + vol stress."""
        votes: Dict[str, List[float]] = {}
        for s in ctx.signals:
            votes.setdefault(s.symbol, []).append(s.score)
        disagree = [s for s, v in votes.items() if len(v) > 1 and np.std(v) > 0.8]
        pv = float(ctx.extras.get("pre_risk_vol", 0.0) or 0.0)
        stress = 1.0
        note = "no action"
        if disagree:
            stress *= 0.85
            note = f"agent disagreement on {', '.join(disagree[:3])}"
        if pv > float(self.cfg["risk"]["vol_target_band"][1]):
            stress *= 0.8
            note = f"pre-risk portfolio vol {pv:.0%} above band; risk reduced"
        if ctx.verdict and ctx.verdict.breaches:
            stress *= 0.95
        return {"scale": float(np.clip(stress, self.min_scale, 1.0)), "vetoes": [],
                "note": note, "mode": "heuristic"}
