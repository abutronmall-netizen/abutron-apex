"""Read-only APEX TradingAgents telemetry. No orders, secrets or controller writes."""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen

PRODUCTION = Path("/opt/apex-client-mt5/abutron_selective_tradingagents_v1.py")
CANARY = Path("/opt/apex/apps/abutron-broker-agents-canary/three_agent_canary.py")
LATEST = Path("/var/lib/abutron-scanner-llm/latest.json")
EXPECTED_CANARY_SHA = "72cc184e80dd2a36c92be501ab254cf9e360ca01829a2f21f5c7e39880457b5b"

def utcnow():
    return datetime.now(timezone.utc)

def declared_model(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf8"))
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MODEL" for t in stmt.targets
            ) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                return stmt.value.value[:70]
    except (OSError, SyntaxError, UnicodeError):
        pass
    return None

def unit_active(unit):
    try:
        proc = subprocess.run(
            ["/usr/bin/systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=1, check=False)
        return proc.stdout.strip() == "active"
    except (OSError, subprocess.TimeoutExpired):
        return False

def snapshot(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 200000:
            return {}
        d = json.loads(path.read_text(encoding="utf8"))
        return d if isinstance(d, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}

def seconds_old(stamp):
    try:
        raw = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if raw.tzinfo is None:
            return None
        return max(0, int((utcnow() - raw).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return None

def installed_models():
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=1.3) as resp:
            data = json.load(resp)
        return [m.get("name") for m in data.get("models", []) if isinstance(m, dict)]
    except (OSError, ValueError, TypeError, TimeoutError):
        return []

def build():
    prod = declared_model(PRODUCTION)
    checkpoint = snapshot(Path('/opt/apex/runtime/apex_ui/agent_canary_checkpoint.json'))
    proof_ok = (checkpoint.get('sha256') == EXPECTED_CANARY_SHA and
                checkpoint.get('state') == 'STAGED_RESEARCH_ONLY')
    candidate = checkpoint.get('model') if proof_ok else None
    models = installed_models()
    review = snapshot(LATEST)
    age = seconds_old(review.get("checked_at_utc"))
    fresh = (review.get("schema") == "abutron.scanner.llm.v1" and age is not None
             and age <= 180 and review.get("model") == prod)
    status = review.get("status") if fresh else "UNVERIFIED_OR_STALE"
    return {
        "schema": "abutron.apex.agent_stack.readonly.v1",
        "checked_at_utc": utcnow().isoformat(),
        "source": "Production reviewer config, local Ollama, systemd and private review journal",
        "production": {
            "model": prod or "UNVERIFIED",
            "installed": prod in models if prod else False,
            "ollama_service_active": unit_active("ollama-apex.service"),
            "selective_reviewer_timer_active": unit_active("abutron-scanner-llm.timer"),
            "tradingagents_mode": "SELECTIVE_MARKET_ANALYST",
            "full_multi_agent_graph_active": False,
            "execution_authority": False,
        },
        "last_review": {
            "fresh": fresh,
            "status": status if isinstance(status, str) else "UNVERIFIED",
            "age_seconds": age if fresh else None,
            "candidate_count": review.get("candidate_count", 0) if fresh else None,
            "checked_at_utc": review.get("checked_at_utc") if fresh else None,
        },
        "upgrade": {
            "candidate_model": candidate or "UNVERIFIED",
            "model_installed": candidate in models if candidate else False,
            "three_agent_canary_integrity_verified": proof_ok,
            "verification_scope": "ROOT_CHECKPOINT_ONLY_NOT_CONTINUOUS",
            "checkpoint_utc": checkpoint.get("verified_at_utc") if proof_ok else None,
            "roles": ["Technical", "Regime", "Risk"],
            "state": "STAGED_RESEARCH_ONLY" if proof_ok else "UNVERIFIED",
            "production_connected": False,
            "broker_order_authorized": False,
            "broker_candle_3_agent_proof": "NOT_VERIFIED",
        },
        "broker_review": {
            "deriv": "SCHEDULED_ADVISORY" if unit_active("abutron-scanner-llm.timer") else "PAUSED",
            "fp_markets": "SCHEDULED_ADVISORY_NO_FRESH_PROOF" if unit_active("fp-apex-ai-readonly.timer") else "PAUSED",
            "unified_monitor_active": unit_active("abutron-unified-decision-readonly.timer"),
        },
        "risk_and_execution_unchanged": True,
        "warning": "Qwen3 three-agent canary is not connected to the production router; reviews do not prove MT5 orders.",
    }
