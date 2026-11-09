"""One existing Deriv DEMO native session, customer-initiated read-only V7 claim.
Requires fresh V7 customer JWT, portal reauth, email OTP, CSRF, one-use ticket
and root-generated attestation of current broker-native session. No MT5 password.
No orders, no license, no trade operations. No generic broker account enrollment.
"""
from __future__ import annotations
import datetime as dt
import hmac
import json
from pathlib import Path
import stat
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import AccountStatus, AuditEvent, BotTier, Broker, Customer, Role, TradingAccount
from app.security import get_current_customer, auth_version
from app.customer_mt5_proof_routes import csrf_check
from app.customer_mt5_enrollment_prepare_v1 import (
    consume_verified_ticket, reserve_customer_attempt, PrepareUnavailable
)

router=APIRouter(prefix="/api/v1/auth/mt5-link/owner-deriv",tags=["owner-deriv-readonly"])
PROOF=Path("/var/lib/abutron-v7-deriv-owner-proof/owner-demo-proof-v9381.json")
SCHEMA="ABUTRON_NATIVE_OWNER_DEMO_AUTH_ATTESTATION_V3"
BROKER_SLUG="deriv-existing-owner-mt5-demo"
ACCOUNT_LOGIN="32456207"
ACCOUNT_SERVER="Deriv-Demo"
OWNER_EMAIL="abutronmall@gmail.com"
PAUSED_REASON="verified_existing_owner_deriv_demo_readonly_no_orders"

class ClaimRequest(BaseModel):
    model_config={"extra":"forbid"}
    mfa_ticket:str=Field(min_length=43,max_length=43,repr=False)
    mt5_login:str=Field(pattern=r"^\d{8}$")
    server:str=Field(min_length=5,max_length=80)
    accept_readonly_assignment:bool

class UnlinkRequest(BaseModel):
    model_config={"extra":"forbid"}
    mfa_ticket:str=Field(min_length=43,max_length=43,repr=False)
    mt5_login:str=Field(pattern=r"^\d{8}$")
    accept_portal_only_unlink:bool

def customer_scope(customer:Customer):
    if (customer.role!=Role.CUSTOMER or not customer.is_active
            or not hmac.compare_digest(customer.email.casefold(),OWNER_EMAIL)):
        raise HTTPException(403,"OWNER_CUSTOMER_ACCOUNT_REQUIRED")

def verified_native_proof(now:dt.datetime|None=None)->dict:
    now=now or dt.datetime.now(dt.timezone.utc)
    try:
        s=PROOF.lstat()
        if (not stat.S_ISREG(s.st_mode) or PROOF.is_symlink() or
                s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o640 or
                not 10<s.st_size<1100):
            raise ValueError("UNTRUSTED_PROOF_FILE")
        p=json.loads(PROOF.read_text())
        mandatory={"schema","broker","server","login","mode","verified_utc",
            "last_broker_native_authorization_utc",
            "last_authenticated_demo_m5_cycle_utc","service_main_pid",
            "demo_orders_enabled","customer_claimed","portal_orders_authorized",
            "live_orders_authorized","native_history_verified"}
        if not isinstance(p,dict) or set(p)!=mandatory:
            raise ValueError("INVALID_PROOF_SCHEMA")
        if (p["schema"]!=SCHEMA or p["broker"]!="DERIV_BVI"
                or p["server"]!=ACCOUNT_SERVER or p["login"]!=ACCOUNT_LOGIN
                or p["mode"]!="DEMO" or p["demo_orders_enabled"] is not True
                or p["customer_claimed"] is not False
                or p["portal_orders_authorized"] is not False
                or p["live_orders_authorized"] is not False
                or type(p["native_history_verified"]) is not bool
                or type(p["service_main_pid"]) is not int or p["service_main_pid"]<2):
            raise ValueError("NATIVE_ACCOUNT_MISMATCH")
        checked=dt.datetime.fromisoformat(p["verified_utc"])
        auth=dt.datetime.fromisoformat(p["last_broker_native_authorization_utc"])
        tick=dt.datetime.fromisoformat(p["last_authenticated_demo_m5_cycle_utc"])
        if checked.tzinfo is None or auth.tzinfo is None or tick.tzinfo is None:
            raise ValueError("CLOCK_NOT_TRUSTED")
        if not (dt.timedelta(0)<=now-checked<=dt.timedelta(seconds=135)
                and dt.timedelta(0)<=now-tick<=dt.timedelta(minutes=7)
                and dt.timedelta(0)<=now-auth<=dt.timedelta(days=7)
                and auth<=tick<=checked):
            raise ValueError("NATIVE_PROOF_STALE")
        if not Path("/proc",str(p["service_main_pid"]),"stat").exists():
            raise ValueError("NATIVE_SESSION_STOPPED")
        return p
    except Exception:
        raise HTTPException(503,"VERIFIED_NATIVE_DERIV_DEMO_SESSION_UNAVAILABLE") from None

async def require_mfa_ticket(req:Request,customer:Customer,ticket:str):
    csrf_check(req,customer)
    if req.client is None or not req.client.host:
        raise HTTPException(503,"VERIFIED_CLIENT_NETWORK_UNAVAILABLE")
    cfg=get_settings()
    r=Redis.from_url(cfg.redis_url,decode_responses=True)
    try:
        await consume_verified_ticket(redis=r,secret=cfg.jwt_secret.encode(),
            owner=str(customer.id),auth_version=auth_version(customer),token=ticket)
    except PrepareUnavailable:
        raise HTTPException(403,"MT5_ONE_TIME_EMAIL_PROOF_REQUIRED") from None
    finally:
        await r.aclose()
    try:
        reserve_customer_attempt(owner=str(customer.id),validated_client_ip=req.client.host)
    except PrepareUnavailable:
        raise HTTPException(429,"MT5_CLAIM_RATE_LIMITED") from None

async def locked_account(db:AsyncSession):
    # Serialize all attempts targeting this one owner-native MT5 account.
    await db.execute(text("SELECT pg_advisory_xact_lock(583720426101)"))
    return await db.scalar(select(TradingAccount).join(Broker,
        Broker.id==TradingAccount.broker_id).where(
            Broker.slug==BROKER_SLUG,TradingAccount.broker_login==ACCOUNT_LOGIN)
        .with_for_update())

@router.post("/claim")
async def claim_existing_owner_demo(body:ClaimRequest,request:Request,
        customer:Customer=Depends(get_current_customer),db:AsyncSession=Depends(get_db)):
    customer_scope(customer)
    if (body.accept_readonly_assignment is not True or
            not hmac.compare_digest(body.mt5_login,ACCOUNT_LOGIN) or
            body.server!=ACCOUNT_SERVER):
        raise HTTPException(403,"DERIV_OWNER_IDENTITY_SCOPE_DENIED")
    # No amount of V7 login/email proof can substitute for a fresh broker proof.
    verified_native_proof()
    await require_mfa_ticket(request,customer,body.mfa_ticket)
    verified_native_proof()
    current=await locked_account(db)
    if current is not None:
        if current.customer_id!=customer.id or current.bot_tier!=BotTier.INELIGIBLE:
            raise HTTPException(409,"BROKER_ACCOUNT_ALREADY_BOUND_TO_OTHER_OWNER")
        if current.status==AccountStatus.DISABLED and current.route_reason=="owner_demo_portal_readonly_unlinked_native_terminal_unaffected":
            current.status=AccountStatus.PAUSED
            current.route_reason=PAUSED_REASON
            db.add(AuditEvent(actor_customer_id=customer.id,
                action="native_deriv_owner_demo_readonly_reclaim",entity_type="trading_account",
                entity_id=str(current.id),payload={"orders_authorized":False}))
            await db.commit()
        elif current.status!=AccountStatus.PAUSED or current.route_reason!=PAUSED_REASON:
            raise HTTPException(409,"UNSAFE_EXISTING_LINK_STATE")
        return {"linked":True,"account_id":str(current.id),
                "status":"VERIFIED_OWNER_DEMO_READONLY","order_execution_authorized":False,
                "message":"Existing Deriv DEMO account is assigned read-only"}
    broker=await db.scalar(select(Broker).where(Broker.slug==BROKER_SLUG))
    if broker is None:
        broker=Broker(slug=BROKER_SLUG,display_name="Deriv MT5 Existing Owner DEMO (read-only)",
            adapter_key="DISABLED_OWNER_DEMO_NO_TRADE",is_active=False)
        db.add(broker)
        await db.flush()
    else:
        if broker.adapter_key!="DISABLED_OWNER_DEMO_NO_TRADE" or broker.is_active is not False:
            raise HTTPException(409,"BROKER_ADAPTER_NOT_FAIL_CLOSED")
    current=TradingAccount(customer_id=customer.id,broker_id=broker.id,
        broker_login=ACCOUNT_LOGIN,server_name=ACCOUNT_SERVER,
        currency="USD",bot_tier=BotTier.INELIGIBLE,
        route_reason=PAUSED_REASON,status=AccountStatus.PAUSED,
        equity_usd=0,last_synced_at=None)
    db.add(current)
    await db.flush()
    db.add(AuditEvent(actor_customer_id=customer.id,
        action="native_deriv_owner_demo_readonly_claim",entity_type="trading_account",
        entity_id=str(current.id),payload={"server":ACCOUNT_SERVER,"mode":"DEMO",
        "source":"current_root_native_broker_proof","orders_authorized":False}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409,"DUPLICATE_DEMO_ACCOUNT") from None
    return {"linked":True,"account_id":str(current.id),
            "status":"VERIFIED_OWNER_DEMO_READONLY","order_execution_authorized":False,
            "message":"Deriv DEMO native owner session assigned read-only"}

@router.post("/unlink")
async def unlink_existing_owner_demo(body:UnlinkRequest,request:Request,
        customer:Customer=Depends(get_current_customer),db:AsyncSession=Depends(get_db)):
    customer_scope(customer)
    if (body.accept_portal_only_unlink is not True or
            not hmac.compare_digest(body.mt5_login,ACCOUNT_LOGIN)):
        raise HTTPException(403,"DERIV_OWNER_IDENTITY_SCOPE_DENIED")
    await require_mfa_ticket(request,customer,body.mfa_ticket)
    existing=await locked_account(db)
    if existing is None or existing.customer_id!=customer.id:
        raise HTTPException(404,"OWNER_DEMO_LINK_NOT_FOUND")
    if existing.status!=AccountStatus.PAUSED or existing.bot_tier!=BotTier.INELIGIBLE:
        raise HTTPException(409,"UNSAFE_OWNER_DEMO_ACCOUNT_STATE")
    # Portal access revoked only; never terminate the separate owner's broker terminal.
    existing.status=AccountStatus.DISABLED
    existing.route_reason="owner_demo_portal_readonly_unlinked_native_terminal_unaffected"
    db.add(AuditEvent(actor_customer_id=customer.id,
        action="native_deriv_owner_demo_portal_unlink",entity_type="trading_account",
        entity_id=str(existing.id),payload={"broker_session_terminated":False,
        "orders_authorized":False}))
    await db.commit()
    return {"linked":False,"account_id":str(existing.id),
            "native_terminal_unchanged":True,"order_execution_authorized":False}
