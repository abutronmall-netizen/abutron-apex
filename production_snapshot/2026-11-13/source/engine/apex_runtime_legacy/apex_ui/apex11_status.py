"""APEX 1.1 operator page: account-bound journal summaries, not trading controls."""
from datetime import datetime, timezone
import json
from pathlib import Path

DIR = Path("/var/lib/apex/operator-live")
ACCOUNT_BINDINGS = (("6207", "Deriv", "DEMO"), ("7593", "Deriv", "DEMO"),
                    ("9244", "Deriv", "DEMO"), ("0512", "FP Markets", "DEMO"),
                    ("1636", "FP Markets", "DEMO"), ("1622", "FP Markets", "DEMO"))
COMPONENTS = ("Regime", "Trend", "Mean Reversion", "Breakout", "Portfolio", "Risk")
SCHEMA = "abutron.apex11.operator_engine_telemetry.v1"

def current():
    now = datetime.now(timezone.utc)
    accounts = []
    observed = set()
    for suffix, broker, environment in ACCOUNT_BINDINGS:
        entry = {"account_suffix": suffix, "broker": broker, "environment": environment, "status": "UNAVAILABLE", "age_seconds": None,
                 "checked_utc": None, "symbols": [], "observed_agents": [],
                 "orders_submitted_by_publisher": None}
        try:
            path = DIR / ("apex11-engine-" + suffix + ".json")
            if path.stat().st_size > 15000:
                raise ValueError("oversized output")
            report = json.loads(path.read_text(encoding="utf-8"))
            if (report.get("schema") != SCHEMA or report.get("account_suffix") != suffix
                    or report.get("broker_order_authorized") is not False
                    or report.get("orders_submitted") != 0
                    or (broker == "FP Markets" and (report.get("broker") != broker
                        or report.get("environment") != environment))):
                raise ValueError("wrong account journal")
            stamp = datetime.fromisoformat(report["checked_utc"].replace("Z", "+00:00"))
            age = (now - stamp).total_seconds()
            entry["checked_utc"] = stamp.isoformat()
            entry["age_seconds"] = max(0, round(age))
            entry["status"] = "CURRENT_RESEARCH" if -10 <= age <= 240 else "STALE_RESEARCH"
            entry["orders_submitted_by_publisher"] = 0
            agents = report.get("observed_agents", [])
            if not isinstance(agents, list):
                agents = []
            entry["observed_agents"] = [a for a in COMPONENTS if a in agents]
            symbols = report.get("symbols", [])
            if isinstance(symbols, list):
                entry["symbols"] = [{
                    "symbol": r.get("symbol"), "direction": r.get("direction"),
                    "closed_ts": r.get("closed_ts")}
                    for r in symbols[:(13 if broker == "FP Markets" else 5)] if isinstance(r, dict)
                    and r.get("direction") in ("BUY", "SELL", "HOLD")
                    and isinstance(r.get("closed_ts"), int)
                    and isinstance(r.get("symbol"), str)]
            if entry["status"] == "CURRENT_RESEARCH":
                observed.update(entry["observed_agents"])
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            pass
        accounts.append(entry)
    fresh = [a for a in accounts if a["status"] == "CURRENT_RESEARCH"]
    fp_current = sum(a["broker"] == "FP Markets" and a["status"] == "CURRENT_RESEARCH"
                     and len(a["symbols"]) == 13 for a in accounts)
    return {
        "schema": "abutron.apex11.operator_dashboard.readonly.v1",
        "checked_at_utc": now.isoformat(),
        "engine": "APEX 1.1.0",
        "operation_mode": "ACCOUNT_BOUND_RESEARCH_NO_ORDER_CLAIM",
        "fresh_account_publishers": len(fresh),
        "total_account_publishers": len(ACCOUNT_BINDINGS),
        "deriv_research_publishers": sum(a["broker"] == "Deriv" and a["status"] == "CURRENT_RESEARCH" for a in accounts),
        "fp_research_publishers": fp_current,
        "research_components": [{"name": c, "recent_output_observed": c in observed}
                                for c in COMPONENTS],
        "orders_submitted_by_publishers": 0 if len(fresh) == len(accounts) else None,
        "broker_order_execution_verified": None,
        "broker_evidence_endpoint": "/api/apex11-broker-evidence",
        "fp_apex11_engine_link_verified": fp_current == 3,
        "non_research_accounts": [{"account_suffix":"0178","broker":"Deriv","environment":"LIVE",
                                   "status":"NOT_PART_OF_DEMO_APEX_RESEARCH","symbols":[]}],
        "accounts": accounts,
    }
