"""Authenticated native Deriv owner DEMO monitor; never account data or execution."""
from __future__ import annotations
import json,stat
from datetime import datetime,timezone
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import JSONResponse
from app.models import Customer
from app.security import get_current_customer
PATH=Path("/var/lib/abutron-v7-kronos-research/deriv_demo_status_latest.json")
SCHEMA="ABUTRON_V7_DERIV_DEMO_STATUS_READONLY_V1"
FIELDS=frozenset((
 "schema","checked_utc","source","broker","symbol","ea_version","monitor_status",
 "native_heartbeat_seen","order_attempts_since_start","entry_fills_since_start",
 "exit_deals_last_15m","owner_demo_one_attempt_capability","owner_demo_policy_conflict",
 "one_attempt_demo_scope_reported_not_independently_certified",
 "protected_fill_to_close_certified","strategy_profitable_after_costs_certified",
 "shadow_positive_expectancy_certified","customer_broker_linked",
 "customer_orders_allowed","live_orders_allowed","classification"))
router=APIRouter(prefix="/api/v1",tags=["customer-demonstration-observability"])
def checked_status(p=PATH,now=None):
 try:
  v=p.lstat()
  if not stat.S_ISREG(v.st_mode) or p.is_symlink() or v.st_size>4000:raise ValueError("FILE_INVALID")
  doc=json.loads(p.read_text())
  if not isinstance(doc,dict) or set(doc)!=FIELDS:raise ValueError("FIELDS_INVALID")
  stamp=datetime.fromisoformat(doc["checked_utc"]).astimezone(timezone.utc)
  age=((now or datetime.now(timezone.utc))-stamp).total_seconds()
  if age< -30 or age>1800:raise ValueError("SOURCE_STALE")
  if (doc["schema"]!=SCHEMA or doc["source"]!="OWNER_DERIV_DEMO_NATIVE_MONITOR_NOT_CUSTOMER_ACCOUNT"
      or doc["broker"]!="Deriv-Demo" or doc["symbol"]!="Volatility 75 Index.0"
      or doc["ea_version"] not in ("9.351","9.360")
      or doc["monitor_status"] not in ("ATTENTION","OK","PASS")
      or doc["classification"]!="OBSERVED_DEMO_ENGINE_NOT_CERTIFIED_FOR_CLIENT_EXECUTION"):
      raise ValueError("IDENTITY_MISMATCH")
  for k in ("protected_fill_to_close_certified","strategy_profitable_after_costs_certified",
            "customer_broker_linked","customer_orders_allowed","live_orders_allowed"):
   if doc[k] is not False:raise ValueError("UNSAFE_FINANCIAL_FLAG")
  if doc["one_attempt_demo_scope_reported_not_independently_certified"] is not True:
   raise ValueError("DEMO_NOT_INDEPENDENTLY_CERTIFIED_FLAG_INVALID")
  for k in ("native_heartbeat_seen","owner_demo_one_attempt_capability",
            "owner_demo_policy_conflict","shadow_positive_expectancy_certified"):
   if type(doc[k]) is not bool:raise ValueError("INVALID_BOOLEAN")
  for k in ("order_attempts_since_start","entry_fills_since_start","exit_deals_last_15m"):
   if type(doc[k]) is not int or not 0<=doc[k]<=100000:raise ValueError("INVALID_COUNT")
  return doc
 except Exception as e:
  raise HTTPException(status_code=503,detail="DERIV_DEMO_MONITOR_STALE_OR_UNVERIFIED") from e
@router.get("/research/deriv-demo-status")
async def customer_deriv_demo_status(_customer:Customer=Depends(get_current_customer))->JSONResponse:
 return JSONResponse(content=checked_status(),headers={"Cache-Control":"private, no-store, max-age=0"})
