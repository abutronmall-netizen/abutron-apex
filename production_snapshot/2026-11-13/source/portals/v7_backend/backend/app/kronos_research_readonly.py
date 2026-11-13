"""Authenticated V7 Kronos research, NEVER trading or customer broker linkage.

Only sanitized reports written by unprivileged research exporter are read.
No broker credentials, historical raw OHLC, customer-account positions,
orders, admin mutation or Kronos execution client imported here.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
import math
from pathlib import Path

from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import JSONResponse

from app.models import Customer
from app.security import get_current_customer

REPORT=Path("/var/lib/abutron-v7-kronos-research/portal_latest.json")
ALLOWED_SYMBOLS=frozenset(("R_10","R_25","R_50","R_75","R_100",
    "CRASH150N","CRASH300N","CRASH600","CRASH1000",
    "BOOM150N","BOOM600","BOOM1000"))
ALLOWED_TF=frozenset(("M1","M5","M15","H1","H4","D1"))
router=APIRouter(prefix="/api/v1",tags=["customer-research-readonly"])
TOP_FIELDS=frozenset((
    "account_balance_provided","account_connected_to_customer",
    "execution_certified","forward_profitability_certified",
    "historical_feature_evaluations","historical_model_evaluations",
    "market_quotes_provided","model","orders_allowed","pairs",
    "published_utc","recorded_forecast_count","schema",
    "snapshot_market","source_snapshot","state","symbols","timeframes",
    "warnings",
))
PAIR_FIELDS=frozenset((
    "candidate_is_executable","context","decision","forecast_close",
    "last_close","model_score","research_bias","research_status",
    "symbol","timeframe",
))

def checked_report(path:Path)->dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size>250_000:
        raise ValueError("RESEARCH_FILE_MISSING_OR_INVALID")
    data=json.loads(path.read_text(encoding="utf8"))
    if not isinstance(data,dict) or set(data)!=TOP_FIELDS:
        raise ValueError("RESEARCH_SCHEMA_OR_FIELDS_INVALID")
    if (data.get("schema")!="ABUTRON_V7_AUTHENTICATED_KRONOS_RESEARCH_V1" or
        data.get("state")!="RESEARCH_ONLY_NOT_TRADING_CERTIFIED" or
        data.get("snapshot_market")!="DERIV_CTRADER_DEMO_VIEW_ONLY" or
        data.get("historical_model_evaluations")!=0 or
        data.get("historical_feature_evaluations")!=0 or
        data.get("forward_profitability_certified") is not False or
        data.get("execution_certified") is not False or
        data.get("account_connected_to_customer") is not False or
        data.get("account_balance_provided") is not False or
        data.get("orders_allowed") is not False or
        data.get("market_quotes_provided") is not False):
        raise ValueError("RESEARCH_RELEASE_GATES_REJECTED")
    published=datetime.fromisoformat(data["published_utc"])
    if published.tzinfo is None:raise ValueError("RESEARCH_PUBLISHED_TZ_INVALID")
    age=(datetime.now(timezone.utc)-published.astimezone(timezone.utc)).total_seconds()
    if age< -30 or age>30*3600:
        raise ValueError("RESEARCH_REPORT_STALE")
    rows=data.get("pairs")
    if not isinstance(rows,list) or len(rows)!=72:raise ValueError("RESEARCH_PAIR_COUNT_INVALID")
    seen=set()
    for r in rows:
        if not isinstance(r,dict) or set(r)!=PAIR_FIELDS:
            raise ValueError("RESEARCH_PAIR_SCHEMA_INVALID")
        key=(r.get("symbol"),r.get("timeframe"))
        if (key in seen or key[0] not in ALLOWED_SYMBOLS or key[1] not in ALLOWED_TF or
            r.get("decision")!="HOLD" or
            r.get("research_bias") not in ("UP","DOWN","FLAT","UNAVAILABLE") or
            r.get("candidate_is_executable") is not False):
            raise ValueError("UNSAFE_PAIR_OR_DUPLICATE")
        seen.add(key)
    if len(seen)!=72:raise ValueError("RESEARCH_PAIRS_NOT_COMPLETE")
    # A locked schema forbids private account fields even if exporter changes.
    if any(k in data for k in ("broker_login","account_id","access_token","positions","trades","pnl")):
        raise ValueError("UNSAFE_PRIVATE_RESEARCH_FIELDS")
    return data

@router.get("/research/kronos")
async def authenticated_kronos_research(
    _customer:Customer=Depends(get_current_customer),
)->JSONResponse:
    try:doc=checked_report(REPORT)
    except Exception as exc:
        # Avoid leaking local file paths, system internals or private data.
        raise HTTPException(status_code=503,detail="KRONOS_RESEARCH_NOT_VERIFIED_OR_STALE") from exc
    return JSONResponse(content=doc,headers={
        "Cache-Control":"private, no-store, max-age=0",
        "X-Content-Type-Options":"nosniff",
    })
