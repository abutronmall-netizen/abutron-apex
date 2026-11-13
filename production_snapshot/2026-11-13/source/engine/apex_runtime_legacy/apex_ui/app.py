"""APEX operator dashboard. Read-only, broker-backed and tunnel-only.

The upstream AgenticTrading Lab is preserved and mounted separately.
No MT5 accounts, credentials, order-send actions, or write APIs are exposed.
"""
from __future__ import annotations
from collections import deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess

from fastapi import FastAPI, HTTPException, Query
from apex_ui.telemetry import broker_account, scanner_status, governor_status, broker_prechecks, execution_preview, demo_auto_status
from apex_ui.candle_compare import compare as compare_completed_candles
from apex_ui.decision_intelligence import build as build_decision_intelligence
from apex_ui.agent_stack import build as build_agent_stack
from apex_ui.quant_first_status import current as build_quant_first_status
from apex_ui.trading_health import snapshot as build_trading_health
from apex_ui.fp_market_operator import overview as fp_market_ui, chart as fp_native_chart
from apex_ui.fp_native_history_operator import read as fp_native_broker_history
import sqlite3
import logging
import time
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

APPROOT = Path("/opt/apex/runtime/apex_ui/static")
BROKER = Path("/var/lib/apex/operator-live/native-market.json")
OPERATOR = Path("/var/lib/apex/operator-live/native-status.json")
RISK = Path("/var/lib/apex/mt5-market/contract_risk_latest.json")
SIGNALS = Path("/var/lib/apex/agentic/signals.jsonl")
LATEST = Path("/var/lib/apex/agentic/latest.json")
ERRORS = Path("/var/lib/apex/agentic/errors.jsonl")
FRAMES = ("M1", "M5", "M15", "H1", "H4", "D1")
SERVICES = {
    "client_portal":"apex-client-portal.service",
    "mt5_manager":"abutron-client-mt5-manager.service",
    "native_feed":"abutron-client-native-feed.timer",
    "research_fanout":"abutron-client-shadow-fanout.timer",
    "execution_preflight":"abutron-apex-customer-execution-preflight.timer",
    "handover_watch":"abutron-apex-handover-readiness.timer",
    "destination_shadow":"apex-destination-shadow.timer",
    "operator_dashboard":"apex-homepage.service",
    "local_model":"ollama-apex.service",
    "auto_orders":"abutron-apex-native-orders.timer",
    "remote_management":"desktop-commander-remote.service",
}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, title="APEX Operator Dashboard")


@app.middleware("http")
async def private_headers(request, next_handler):
    reply = await next_handler(request)
    reply.headers["Cache-Control"] = "no-store, max-age=0"
    reply.headers["X-Content-Type-Options"] = "nosniff"
    reply.headers["X-Frame-Options"] = "DENY"
    reply.headers["Referrer-Policy"] = "no-referrer"
    reply.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    )
    return reply


def read_json(path: Path):
    try:
        if path.stat().st_size > 8_000_000:
            raise ValueError("oversized file")
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, UnicodeError):
        return None


def recent_lines(path: Path, count: int = 15):
    try:
        if path.stat().st_size > 20_000_000:
            return []
        with path.open("r", encoding="utf-8") as stream:
            lines = deque(stream, maxlen=count)
        return [json.loads(line) for line in reversed(lines) if line.strip()]
    except (OSError, UnicodeError, ValueError, TypeError):
        return []


def age_seconds(value):
    try:
        raw = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return max(0, int((datetime.now(timezone.utc) - raw).total_seconds()))
    except (ValueError, TypeError):
        return None


def service_state(service: str):
    try:
        p = subprocess.run(
            ["/usr/bin/systemctl", "is-active", service],
            capture_output=True, text=True, timeout=2, check=False,
        )
        text = p.stdout.strip()
        return text if text in ("active", "inactive", "activating", "failed", "deactivating") else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def price_trend(rows):
    closing = [float(r["close"]) for r in rows[-65:]]
    if len(closing) < 22:
        return "UNKNOWN"
    def ema(period):
        start = sum(closing[:period]) / period
        f = 2.0 / (period + 1)
        for value in closing[period:]:
            start = start * (1.0 - f) + value * f
        return start
    x, y = ema(9), ema(21)
    return "UP" if x > y else "DOWN" if x < y else "FLAT"


def instruments_snapshot(doc):
    if not isinstance(doc, dict) or doc.get("source") != "Deriv DEMO MT5" or doc.get("execution_enabled") is not False:
        return [], None
    data = doc.get("data")
    if not isinstance(data, dict):
        return [], None
    instruments = []
    for name, frames in data.items():
        if not isinstance(name, str) or not isinstance(frames, dict):
            continue
        m5 = frames.get("M5") or []
        if len(m5) < 3:
            continue
        try:
            last, previous = m5[-1], m5[-2]
            price = float(last["close"])
            p = float(previous["close"])
            if not math.isfinite(price) or not math.isfinite(p) or p <= 0:
                continue
            trends = {t: price_trend(frames.get(t, [])) for t in ("M15", "H1", "H4")}
            instruments.append({
                "name": name,
                "price": price,
                "change_pct": round((price / p - 1.0) * 100, 4),
                "last_bar_utc": datetime.fromtimestamp(int(last["time"]), timezone.utc).isoformat(),
                "trend": trends,
                "timeframes": [t for t in FRAMES if t in frames],
            })
        except (KeyError, ValueError, TypeError, OverflowError, ZeroDivisionError):
            continue
    return instruments, age_seconds(doc.get("generated_at_utc"))


def clean_signal(raw):
    if not isinstance(raw, dict):
        return None
    rating = raw.get("rating")
    original_note = str(raw.get("agent_summary", ""))
    forbidden = ("revenue", "earnings", "dividend", "company", "shareholder",
                 "balance sheet", "financial projection", "growth potential",
                 "market expansion", "stock price", "cash flow", "corporate",
                 "profitability")
    invalid = any(term in original_note.lower() for term in forbidden)
    if invalid:
        rating = "REJECTED"
    return {
        "timestamp_utc": str(raw.get("timestamp_utc", "")),
        "symbol": str(raw.get("symbol", ""))[:80],
        "rating": str(rating or "UNKNOWN")[:40],
        "technical_direction": str(raw.get("technical_direction", "UNKNOWN"))[:20],
        "shadow_direction": "HOLD" if invalid else str(raw.get("shadow_direction", "HOLD"))[:20],
        "execution_authorized": raw.get("execution_authorized") is True,
        "model": str(raw.get("model", ""))[:100],
        "reason": ("Historical AI report rejected: company fundamentals do not apply to Deriv synthetic indices."
                   if invalid else str(raw.get("reason", ""))[:220]),
        "summary": ("Unverified corporate reasoning suppressed. This research record is not eligible for a trade."
                    if invalid else original_note[:1800]),
    }


def risk_brief():
    risk = read_json(RISK)
    if not isinstance(risk, dict) or risk.get("status") != "inspection_only":
        return {"available": False, "verified_contracts": 0, "unverified_contracts": 0, "age_seconds": None, "instruments": {}}
    instruments = {}
    for obj in risk.get("instruments", []):
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("symbol", ""))[:80]
        instruments[name] = {
            "minimum_lot": obj.get("minimum_lot"),
            "buy_estimate_usd": obj.get("buy_sl_est_usd"),
            "sell_estimate_usd": obj.get("sell_sl_est_usd"),
            "verified": obj.get("verified") is True,
        }
    return {
        "available": True,
        "verified_contracts": sum(1 for x in instruments.values() if x["verified"]),
        "unverified_contracts": sum(1 for x in instruments.values() if not x["verified"]),
        "age_seconds": age_seconds(risk.get("checked_at_utc")),
        "reference_usd": risk.get("budget_reference_usd"),
        "disclaimer": "Single-position hypothetical estimates only; not an enforceable loss limit.",
        "instruments": instruments,
    }


@app.get("/")
def index():
    return FileResponse(APPROOT / "index.html", media_type="text/html")


@app.get("/assets/{asset}")
def asset(asset: str):
    if asset == "apex11-engines.js":
        return FileResponse(APPROOT / asset, media_type="application/javascript")
    if asset == "apex11-engines.css":
        return FileResponse(APPROOT / asset, media_type="text/css")
    if asset == "apex11-broker-evidence.js":
        return FileResponse(APPROOT / asset, media_type="application/javascript")
    if asset == "app.js":
        return FileResponse(APPROOT / asset, media_type="application/javascript")
    if asset == "style.css":
        return FileResponse(APPROOT / asset, media_type="text/css")
    if asset == "agent-stack.js":
        return FileResponse(APPROOT / asset, media_type="application/javascript")
    if asset == "agent-stack.css":
        return FileResponse(APPROOT / asset, media_type="text/css")
    if asset == "fp-operator-ui.js":
        return FileResponse(APPROOT / asset, media_type="application/javascript")
    if asset == "fp-operator-ui.css":
        return FileResponse(APPROOT / asset, media_type="text/css")
    if asset == "fp-native-history-operator.js":
        return FileResponse(APPROOT / asset, media_type="application/javascript")
    if asset == "fp-quality-diagnostics.js":
        return FileResponse(APPROOT / asset, media_type="application/javascript")
    raise HTTPException(status_code=404)


@app.get("/api/fp-quality-diagnostics")
def fp_quality_diagnostics_readonly():
    from apex_ui.fp_quality_diagnostics import current
    return JSONResponse(current())


@app.get("/api/fp-native-history")
def fp_native_history_readonly():
    return JSONResponse(fp_native_broker_history())


@app.get("/api/fp-market")
def fp_market_overview_readonly():
    return JSONResponse(fp_market_ui())


@app.get("/api/fp-market-accounts")
def fp_market_accounts_readonly():
    from apex_ui.fp_market_operator import accounts
    return JSONResponse(accounts())

@app.get("/api/fp-market-account")
def fp_market_selected_account(slot: int = Query(0, ge=0, le=5)):
    from apex_ui.fp_market_operator import account_overview
    try:return JSONResponse(account_overview(slot))
    except KeyError:raise HTTPException(status_code=404,detail="FP account unavailable")

@app.get("/api/fp-market-account-chart")
def fp_market_selected_account_chart(
    slot: int = Query(0,ge=0,le=5),
    symbol: str = Query(...,min_length=3,max_length=16),
    timeframe: str = Query("M5",pattern="^(M1|M5|M15|H1|H4|D1)$"),
):
    from apex_ui.fp_market_operator import account_chart
    try:return JSONResponse(account_chart(slot,symbol,timeframe))
    except KeyError:raise HTTPException(status_code=404,detail="FP account/symbol unavailable")
    except (OSError,ValueError,TypeError,OverflowError):
        raise HTTPException(status_code=503,detail="FP broker data unavailable")


@app.get("/api/fp-market-chart")
def fp_market_candles_readonly(
    symbol: str = Query(..., min_length=3, max_length=16),
    timeframe: str = Query("M5", pattern="^(M1|M5|M15|H1|H4|D1)$"),
):
    try:
        return JSONResponse(fp_native_chart(symbol,timeframe))
    except KeyError:
        raise HTTPException(status_code=404, detail="FP Markets symbol not available")
    except (OSError,ValueError,TypeError,OverflowError):
        raise HTTPException(status_code=503, detail="FP broker-native candles unavailable")


@app.get("/api/apex11-engines")
def apex11_engines_readonly():
    from apex_ui.apex11_status import current
    return JSONResponse(current())


@app.get("/api/apex11-broker-evidence")
def apex11_broker_evidence_readonly():
    from apex_ui.broker_evidence import current
    return JSONResponse(current())


@app.get("/api/runtime-health")
def runtime_health_readonly():
    return JSONResponse(build_trading_health())


@app.get("/api/agent-stack")
def agent_stack_read_only():
    return JSONResponse(build_agent_stack())


@app.get("/api/quant-first")
def quant_first_operator_read_only():
    """Independent broker-native quant research; no execution controls."""
    return JSONResponse(build_quant_first_status())


@app.get("/api/overview")
def overview():
    op = read_json(OPERATOR)
    if not isinstance(op, dict) or op.get("schema") != "abutron.operator.native.v1":
        op = {"available":False, "sessions_connected":0, "sessions_total":0,
              "bridges_ready":0,"trading_enabled":0,"accounts":[],
              "primary_account":{"available":False,"stale":True}}
    status_age=age_seconds(op.get("checked_at_utc"))
    fresh=status_age is not None and status_age<=165
    op["fresh"]=fresh
    op["age_seconds"]=status_age
    if not fresh:
        op["sessions_connected"]=0
        op["bridges_ready"]=0
        op["accounts"]=[]
        op["primary_account"]={"available":False,"stale":True}
    doc=read_json(BROKER)
    instruments, market_age=instruments_snapshot(doc)
    if not fresh:
        market_age=None
    raw=read_json(LATEST)
    archived=[clean_signal(x) for x in recent_lines(SIGNALS,30)]
    archived=[x for x in archived if x]
    latest=clean_signal(raw) if raw else None
    if latest and (age_seconds(latest.get("timestamp_utc")) or 10**9)>600:
        latest=None
    errors=recent_lines(ERRORS,3)
    risk=risk_brief()
    if risk.get("age_seconds") is None or risk["age_seconds"]>900:
        risk["available"]=False
    demo=demo_auto_status()
    demo["timer_active"]=service_state("apex-demo-auto-v3.timer")=="active"
    execution_proof=op.get("account_execution") if isinstance(op.get("account_execution"),dict) else {}
    proof_age=age_seconds(execution_proof.get("checked_at_utc"))
    proof_fresh=bool(fresh and proof_age is not None and proof_age<=165)
    return JSONResponse({
        "ok":True,"environment":"Deriv MT5 DEMO",
        "data_source":"Deriv DEMO: research and broker-verified execution reported separately",
        "execution_enabled":bool(proof_fresh and execution_proof.get("all_demo_accounts_fully_operational_verified") is True),"live_enabled":False,
        "crm_effective_switches_on":execution_proof.get("crm_effective_on_count",0) if proof_fresh else None,
        "account_execution":execution_proof if proof_fresh else {"available":False,"all_demo_accounts_fully_operational_verified":False,"status":"EXECUTION_EVIDENCE_STALE_OR_MISSING"},
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "operator_native":op,
        "market":{"count":len(instruments) if fresh else 0,
                  "age_seconds":market_age,
                  "generated_at_utc":doc.get("generated_at_utc") if isinstance(doc,dict) else None,
                  "stale":market_age is None or market_age>170,
                  "instruments":instruments if fresh else []},
        "agents":{"latest":latest,"signals":archived,
                  "count":len(archived),"archive":True},
        "risk":risk,"broker_account":op.get("primary_account",{"available":False,"stale":True}),
        "scanner":scanner_status(),
        "risk_governor":governor_status(),
        "broker_prechecks":broker_prechecks(),
        "execution_preview":execution_preview(),
        "demo_auto":demo,
        "services":{label:service_state(unit) for label,unit in SERVICES.items()},
        "agent_cycle":service_state("abutron-client-shadow-fanout.timer"),
        "recent_errors":[{"timestamp_utc":x.get("timestamp_utc"),"error_type":x.get("error_type")}
            for x in errors if isinstance(x,dict)],
    })


@app.get("/api/broker")
def broker_status():
    op=read_json(OPERATOR)
    if not isinstance(op,dict) or age_seconds(op.get("checked_at_utc")) is None or age_seconds(op.get("checked_at_utc"))>165:
        return JSONResponse({"available":False,"stale":True,"reason":"Native broker snapshot unavailable"})
    return JSONResponse(op.get("primary_account",{"available":False,"stale":True}))


@app.get("/api/scanner")
def full_scanner():
    return JSONResponse(scanner_status())


@app.get("/api/risk-governor")
def full_risk_governor():
    return JSONResponse(governor_status())


@app.get("/api/demo-auto")
def demo_auto():
    return JSONResponse({**demo_auto_status(),
                         "timer_active":service_state("apex-basket-dashboard-sync.timer")=="active"})

@app.get("/api/order-prechecks")
def order_prechecks():
    return JSONResponse(broker_prechecks())


@app.get("/api/execution-preview")
def execution_status():
    return JSONResponse(execution_preview())


@app.get("/api/ai-smc-ict-status")
def ai_smc_ict_current_status():
    """Sanitized, read-only DEMO decisions: independent of older scanner ranking."""
    path=Path("/var/lib/apex/operator-live/ai-smc-ict-status.json")
    if path.is_symlink() or not path.is_file() or path.stat().st_size>120_000:
        return JSONResponse({"available":False,"reason":"Verified decision status unavailable"},status_code=503)
    doc=read_json(path)
    if (not isinstance(doc,dict)
        or doc.get("schema")!="abutron.apex.ai_smc_ict.operator_status.v1"
        or doc.get("environment")!="DEMO"
        or doc.get("broker")!="Deriv"
        or doc.get("live_trading_allowed") is not False
        or not isinstance(doc.get("accounts"),list)
        or age_seconds(doc.get("generated_at_utc")) is None
        or age_seconds(doc.get("generated_at_utc"))>130):
        return JSONResponse({"available":False,"reason":"AI/SMC/ICT evidence stale or untrusted"},status_code=503)
    return JSONResponse({"available":True,**doc})


@app.get("/api/decision-intelligence")
def decision_intelligence_read_only():
    # Native market and scanner JSON files are published separately. When a
    # client hits their refresh window, retry the WHOLE verified pair; never
    # override the strict timestamp, completeness, or historical DB checks.
    known = {
        "SCANNER_BROKER_SNAPSHOT_MISMATCH",
        "UNMATCHED_COMPLETED_M5_CANDLE",
        "STALE_NATIVE_BROKER_SNAPSHOT",
        "INCOMPLETE_BROKER_TIMEFRAMES",
        "HISTORICAL_DATABASE_CHECK_FAILED",
        "BROKER_FEED_NOT_VERIFIED",
    }
    reason_code = "EVIDENCE_TEMPORARILY_UNAVAILABLE"
    for attempt in range(4):
        try:
            data = build_decision_intelligence()
            data["verification_retries"] = attempt
            return JSONResponse(data)
        except (ValueError, OSError, sqlite3.Error, TypeError, KeyError, OverflowError) as exc:
            # Only allow fixed, non-sensitive reason codes into output/logs.
            if isinstance(exc, ValueError) and str(exc) in known:
                reason_code = str(exc)
            elif isinstance(exc, sqlite3.OperationalError):
                reason_code = "HISTORY_DATABASE_BUSY"
            else:
                reason_code = "EVIDENCE_TEMPORARILY_UNAVAILABLE"
            if attempt < 3:
                time.sleep(0.16)
    logging.getLogger(__name__).warning("AI_DECISION_SAFE_HOLD %s", reason_code)
    # Never silently fall back to an older or unverified research signal.
    return JSONResponse({
        "schema":"abutron.apex.decision_intelligence.readonly.v1",
        "available":False,
        "reason":"Verified broker or historical evidence unavailable",
        "reason_code":reason_code,
        "retry_after_seconds":4,
        "top_three":[],"all_symbols":[],
        "order_routing_changed":False,"live_trading":False
    },status_code=503)


@app.get("/api/candle-comparison")
def comparison(symbol: str = Query(..., min_length=3, max_length=80)):
    try:
        return JSONResponse(compare_completed_candles(symbol))
    except ValueError as ex:
        # Broker-source, closed-bar and age checks are required.
        if "approved Deriv" in str(ex):
            raise HTTPException(status_code=404,detail="Unknown broker symbol")
        raise HTTPException(status_code=503,detail="Broker candles unavailable or unverified")


@app.get("/api/chart")
def chart(symbol: str = Query(..., min_length=3, max_length=80),
          timeframe: str = Query("M5", pattern="^(M1|M5|M15|H1|H4|D1)$")):
    doc = read_json(BROKER)
    if not isinstance(doc, dict) or doc.get("source") != "Deriv DEMO MT5" or doc.get("execution_enabled") is not False:
        raise HTTPException(503, detail="Broker data not verified")
    source = doc.get("data", {})
    if symbol not in source:
        raise HTTPException(404, detail="Broker symbol unavailable")
    snapshot_age=age_seconds(doc.get("generated_at_utc"))
    if snapshot_age is None or snapshot_age>660:
        raise HTTPException(503,detail="Broker snapshot stale")
    items = source[symbol].get(timeframe, [])
    bars = []
    for row in items[-150:]:
        try:
            bars.append({"t": int(row["time"]), "o": float(row["open"]), "h": float(row["high"]),
                         "l": float(row["low"]), "c": float(row["close"]), "v": int(row.get("volume",0))})
        except (KeyError, ValueError, TypeError):
            continue
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "source": "Deriv DEMO MT5",
            "age_seconds": age_seconds(doc.get("generated_at_utc")), "bars": bars}
