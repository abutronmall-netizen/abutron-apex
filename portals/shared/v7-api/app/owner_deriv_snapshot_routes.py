"""STAGED ONLY. Read-only authenticated V7 owner native snapshot GET.
Never allows arbitrary account selectors, mutation, broker orders, or writes.
The root publisher and real first native snapshot must be certified BEFORE deployment.
"""
from __future__ import annotations
import json
import os
from datetime import datetime,timezone
from pathlib import Path
import stat
import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import AccountStatus, BotTier, Broker, Customer, TradingAccount
from app.owner_deriv_claim_routes import (
    customer_scope, verified_native_proof, BROKER_SLUG, PAUSED_REASON
)
from app.security import get_current_customer
from app.owner_native_closed_pairs_readonly import reconcile, ReconcileRejected

ROUTER_VERSION="ABUTRON_V7_NATIVE_OWNER_SNAPSHOT_GET_V1"
SNAPSHOT=Path("/var/lib/abutron-v7-deriv-owner-snapshot/latest.json")
EXPECTED_KEYS=frozenset({
 "schema","account_login","server","currency","mode","connected_at_capture",
 "captured_unix","history_from_unix","history_to_unix","balance","equity",
 "floating_profit","margin","margin_free","open_positions","open_position_count",
 "pending_order_count","history_deals","history_deal_count",
 "history_is_bounded_not_lifetime","trade_execution_authorized",
 "broker_trade_reconciliation_certified"
})
router=APIRouter(prefix="/api/v1/mt5/owner-demo",tags=["owner-demo-observation"])

def read_attested_snapshot(now=None):
    now=int(time.time()) if now is None else int(now)
    try:
        info=SNAPSHOT.lstat()
        if (SNAPSHOT.is_symlink() or not stat.S_ISREG(info.st_mode)
                or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o640
                or not 200<=info.st_size<=500000):
            raise ValueError("UNTRUSTED_DATA_FILE")
        blob=SNAPSHOT.read_bytes()
        check=SNAPSHOT.lstat()
        if ((check.st_dev,check.st_ino,check.st_size,check.st_mtime_ns)
                !=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)):
            raise ValueError("FILE_CHANGED")
        if len(blob)!=info.st_size or b"\x00" in blob:
            raise ValueError("INVALID_DOCUMENT")
        data=json.loads(blob)
        if not isinstance(data,dict) or set(data)!=EXPECTED_KEYS:
            raise ValueError("INVALID_FIELDS")
        if (data["schema"]!="ABUTRON_V7_NATIVE_ACCOUNT_SNAPSHOT_V1"
              or data["account_login"]!="32456207" or data["server"]!="Deriv-Demo"
              or data["currency"]!="USD" or data["mode"]!="DEMO"
              or data["connected_at_capture"] is not True
              or data["trade_execution_authorized"] is not False
              or data["broker_trade_reconciliation_certified"] is not False
              or data["history_is_bounded_not_lifetime"] is not True):
            raise ValueError("IDENTITY_OR_POLICY_MISMATCH")
        captured=data["captured_unix"]
        if (type(captured) is not int or not 0<=now-captured<=86400
                or type(data["open_position_count"]) is not int
                or type(data["history_deal_count"]) is not int
                or not 0<=data["open_position_count"]<=100
                or not 0<=data["history_deal_count"]<=2000
                or type(data["open_positions"]) is not list
                or type(data["history_deals"]) is not list
                or len(data["open_positions"])!=data["open_position_count"]
                or len(data["history_deals"])!=data["history_deal_count"]):
            raise ValueError("STALE_OR_INCOMPLETE")
        return data
    except Exception:
        raise HTTPException(503,"VERIFIED_DERIV_ACCOUNT_SNAPSHOT_NOT_READY") from None

@router.get("/snapshot")
async def owner_snapshot(
    customer:Customer=Depends(get_current_customer),
    db:AsyncSession=Depends(get_db),
):
    customer_scope(customer)
    # Independent current no-orders attestation, not solely a stale owner assignment.
    verified_native_proof()
    account=await db.scalar(
        select(TradingAccount).join(Broker,Broker.id==TradingAccount.broker_id)
        .where(TradingAccount.customer_id==customer.id,
               TradingAccount.broker_login=="32456207",
               TradingAccount.server_name=="Deriv-Demo",
               TradingAccount.status==AccountStatus.PAUSED,
               TradingAccount.bot_tier==BotTier.INELIGIBLE,
               TradingAccount.route_reason==PAUSED_REASON,
               Broker.slug==BROKER_SLUG,
               Broker.adapter_key=="DISABLED_OWNER_DEMO_NO_TRADE",
               Broker.is_active.is_(False)))
    if account is None:
        raise HTTPException(404,"NO_VERIFIED_OWNER_READONLY_LINK")
    data=read_attested_snapshot()
    # Derived position-pair candidates are separate from independently certified trade history.
    try:
        pairs=reconcile(data)
    except ReconcileRejected:
        pairs=None
    return JSONResponse({
        "source":ROUTER_VERSION,
        "source_certification":"NATIVE_MT5_OWNER_LOCAL_OBSERVATION_ONLY",
        "trading_account_id":str(account.id),
        "account_login":data["account_login"],
        "server":data["server"],
        "captured_unix":data["captured_unix"],
        "observed_at_utc":datetime.fromtimestamp(data["captured_unix"],timezone.utc).isoformat(),
        "snapshot_age_seconds":max(0,int(time.time())-data["captured_unix"]),
        "data_freshness":"FRESH_AT_CAPTURE_ONLY" if max(0,int(time.time())-data["captured_unix"])<=120 else "HISTORICAL_STALE",
        "not_a_live_feed":True,
        "balance":data["balance"],"equity":data["equity"],
        "floating_profit":data["floating_profit"],
        "margin":data["margin"],"margin_free":data["margin_free"],
        "currency":"USD",
        "open_positions":data["open_positions"],
        "pending_order_count":data["pending_order_count"],
        "history_from_unix":data["history_from_unix"],
        "history_to_unix":data["history_to_unix"],
        "deal_event_count_in_window":data["history_deal_count"],
        "recent_broker_deal_events":data["history_deals"][-100:],
        "history_is_bounded_not_lifetime":True,
        "native_closed_pair_status":"DERIVED_FROM_NATIVE_DEAL_PAIRS_NOT_IN_CERTIFIED_LEDGER" if pairs else "RECONCILIATION_NOT_PASSED",
        "native_closed_pairs":pairs["complete_position_pairs"][-100:] if pairs else [],
        "native_pair_count":pairs["position_pairs"] if pairs else 0,
        "native_realized_net_usd":pairs["trading_net_usd"] if pairs else None,
        "native_funding_event_usd":pairs["funding_usd"] if pairs else None,
        "trade_reconciliation_certified":False,
        "orders_enabled":False,"live_enabled":False
    },headers={"Cache-Control":"private, no-store, max-age=0"})
