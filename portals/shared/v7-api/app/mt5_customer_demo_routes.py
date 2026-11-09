"""Customer-initiated, isolated broker-native MT5 DEMO identity verification only.
No broker password persistence, trading capability, LIVE servers, finance or license.
No mock connection: persist PAUSED, INELIGIBLE, inactive adapter only after
verified broker-native private socket attestation and customer's signed consent.
"""
from __future__ import annotations
import asyncio
import hmac
import json
import re
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, SecretStr, Field
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import AccountStatus, AuditEvent, BotTier, Broker, Customer, Role, TradingAccount
from app.security import get_current_customer
from app.customer_mt5_proof_routes import csrf_check

router=APIRouter(prefix="/api/v1/auth/mt5-link/native-demo",tags=["mt5-customer-demo"])
SOCKET="/run/abutron-mt5-gateway/verify.sock"
SCHEMA="ABUTRON_MT5_V6_PRIVATE_DEMO_GATEWAY"
SERVERS={
    "DERIV_BVI":"Deriv-Demo",
    "IC_MARKETS":"ICMarketsSC-Demo",
    "FP_MARKETS":"FPMarketsSC-Demo Server",
}
DISPLAY={
    "DERIV_BVI":"Deriv (BVI) Ltd.",
    "IC_MARKETS":"IC Markets",
    "FP_MARKETS":"FP Markets",
}
BROKER_SLUG_PREFIX="mt5-identity-v6-"
INACTIVE_ADAPTER="DISABLED_NATIVE_MT5_DEMO_IDENTITY_ONLY"
REASON="broker_native_demo_verified_once_readonly_no_stored_credentials"
MAX_PASSWORD=256

class Connect(BaseModel):
    model_config={"extra":"forbid"}
    broker:str=Field(min_length=6,max_length=32)
    server:str=Field(min_length=8,max_length=96)
    login:str=Field(pattern=r"^[0-9]{3,20}$")
    password:SecretStr=Field(min_length=1,max_length=MAX_PASSWORD,repr=False)
    authorize_abutron:bool

class Disconnect(BaseModel):
    model_config={"extra":"forbid"}
    account_id:uuid.UUID
    confirm_disconnect:bool

def owner(customer:Customer):
    if customer.role!=Role.CUSTOMER or not customer.is_active:
        raise HTTPException(403,"ACTIVE_CUSTOMER_SESSION_REQUIRED")

async def limit_attempts(customer:Customer,request:Request):
    """Bound verification attempts; fail closed when Redis is unavailable."""
    from hashlib import sha256
    if not request.client or not request.client.host:
        raise HTTPException(503,"NETWORK_IDENTITY_UNAVAILABLE")
    cfg=get_settings()
    redis=Redis.from_url(cfg.redis_url,decode_responses=True)
    name=sha256((cfg.jwt_secret+"mt5-v6:"+str(customer.id)).encode()).hexdigest()
    key="abutron:mt5:native-demo:lim:"+name
    try:
        count=await redis.incr(key)
        if count==1:await redis.expire(key,900)
        if count>3:raise HTTPException(429,"MT5_VERIFICATION_RATE_LIMITED")
    except HTTPException:raise
    except Exception:raise HTTPException(503,"VERIFICATION_RATE_GATE_UNAVAILABLE") from None
    finally:await redis.aclose()

async def native_verify(customer_id:str,broker:str,server:str,login:str,password:str):
    """One short-lived UNIX request, never persist/log secrets or echo broker results."""
    if any(c in password for c in "\r\n\x00") or not 1<=len(password)<=MAX_PASSWORD:
        raise HTTPException(422,"INVALID_PASSWORD_FORMAT")
    payload={"owner_id":customer_id,"broker":broker,"server":server,
             "login":login,"password":password,"mode":"DEMO"}
    encoded=json.dumps(payload,separators=(",",":"),ensure_ascii=True).encode()+b"\n"
    if len(encoded)>1800:
        raise HTTPException(422,"BROKER_VERIFICATION_REQUEST_TOO_LARGE")
    writer=None
    try:
        async with asyncio.timeout(111):
            reader,writer=await asyncio.open_unix_connection(SOCKET,limit=1900)
            writer.write(encoded)
            await writer.drain()
            raw=await asyncio.wait_for(reader.readline(),timeout=105)
        if not raw or len(raw)>900:raise ValueError("INVALID_NATIVE_RESPONSE")
        proof=json.loads(raw)
        if (set(proof)!={"schema","broker_native_identity_verified",
               "customer_broker_account_linked","trading_authorized","result"}
            or proof["schema"]!=SCHEMA
            or proof["broker_native_identity_verified"] is not True
            or proof["customer_broker_account_linked"] is not False
            or proof["trading_authorized"] is not False
            or proof["result"]!="NATIVE_IDENTITY_OBSERVED"):
            raise ValueError("BROKER_NATIVE_PROOF_UNVERIFIED")
        return True
    except Exception:
        raise HTTPException(503,"MT5_BROKER_NATIVE_VERIFICATION_NOT_CONFIRMED") from None
    finally:
        if writer is not None:
            writer.close()
            try:await asyncio.wait_for(writer.wait_closed(),timeout=2)
            except Exception:pass

@router.post("/connect")
async def connect_mt5_demo(body:Connect,request:Request,
            customer:Customer=Depends(get_current_customer),
            db:AsyncSession=Depends(get_db)):
    owner(customer)
    csrf_check(request,customer)
    if body.authorize_abutron is not True:
        raise HTTPException(403,"EXPLICIT_ACCOUNT_AUTHORIZATION_REQUIRED")
    if SERVERS.get(body.broker)!=body.server:
        raise HTTPException(403,"LIVE_SERVER_OR_UNAPPROVED_BROKER_NOT_SUPPORTED")
    password=body.password.get_secret_value()
    if re.search(r"[\x00-\x1f]",password):
        raise HTTPException(422,"INVALID_PASSWORD_FORMAT")
    await limit_attempts(customer,request)
    # IMPORTANT: do not place broker secrets in audit logs or exceptions.
    await native_verify(str(customer.id),body.broker,body.server,body.login,password)
    del password
    slug=BROKER_SLUG_PREFIX+body.broker.lower()
    await db.execute(text("SELECT pg_advisory_xact_lock(583720426202)"))
    result=await db.execute(select(TradingAccount).join(Broker,Broker.id==TradingAccount.broker_id)
                 .where(Broker.slug==slug,TradingAccount.broker_login==body.login).with_for_update())
    existing=result.scalar_one_or_none()
    if existing is not None and existing.customer_id!=customer.id:
        raise HTTPException(409,"ACCOUNT_ALREADY_ASSIGNED_TO_ANOTHER_CUSTOMER")
    broker=await db.scalar(select(Broker).where(Broker.slug==slug))
    if broker is None:
        broker=Broker(slug=slug,display_name=DISPLAY[body.broker],
                      adapter_key=INACTIVE_ADAPTER,is_active=False)
        db.add(broker);await db.flush()
    elif broker.adapter_key!=INACTIVE_ADAPTER or broker.is_active is not False:
        raise HTTPException(409,"BROKER_ADAPTER_UNSAFE")
    if existing is not None:
        if (existing.status not in (AccountStatus.PAUSED,AccountStatus.DISABLED)
              or existing.bot_tier!=BotTier.INELIGIBLE):
            raise HTTPException(409,"UNSAFE_EXISTING_ACCOUNT_STATE")
        existing.status=AccountStatus.PAUSED
        existing.route_reason=REASON
        existing.server_name=body.server
        account=existing
    else:
        account=TradingAccount(customer_id=customer.id,broker_id=broker.id,
              broker_login=body.login,server_name=body.server,currency="USD",
              equity_usd=0,bot_tier=BotTier.INELIGIBLE,
              route_reason=REASON,status=AccountStatus.PAUSED,last_synced_at=None)
        db.add(account)
    try:
        await db.flush()
        db.add(AuditEvent(actor_customer_id=customer.id,
            action="customer_mt5_broker_native_demo_verified_once",
            entity_type="trading_account",entity_id=str(account.id),
            payload={"broker":body.broker,"mode":"DEMO","orders_enabled":False,
                     "credential_storage":False,"native_proof":SCHEMA}))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409,"ACCOUNT_ALREADY_REGISTERED") from None
    return {"verified":True,"account_id":str(account.id),
            "status":"PAUSED_READ_ONLY","trading_authorized":False,
            "credentials_saved":False,
            "message":"Broker login verified once. Trading disabled; future session requires separate authorization."}

@router.post("/disconnect")
async def disconnect_mt5_demo(body:Disconnect,request:Request,
           customer:Customer=Depends(get_current_customer),
           db:AsyncSession=Depends(get_db)):
    owner(customer)
    csrf_check(request,customer)
    if body.confirm_disconnect is not True:
        raise HTTPException(403,"EXPLICIT_DISCONNECT_REQUIRED")
    await db.execute(text("SELECT pg_advisory_xact_lock(583720426202)"))
    row=await db.scalar(select(TradingAccount).join(Broker,
             Broker.id==TradingAccount.broker_id)
             .where(TradingAccount.id==body.account_id,
                    TradingAccount.customer_id==customer.id,
                    Broker.slug.in_([BROKER_SLUG_PREFIX+x.lower() for x in SERVERS]))
             .with_for_update())
    if row is None:
        raise HTTPException(404,"OWNED_MT5_ACCOUNT_NOT_FOUND")
    if row.status==AccountStatus.DISABLED:
        return {"disconnected":True,"native_terminal_unchanged":True}
    if row.status!=AccountStatus.PAUSED or row.bot_tier!=BotTier.INELIGIBLE:
        raise HTTPException(409,"ACCOUNT_REQUIRES_PROTECTED_TRADING_HANDOFF")
    row.status=AccountStatus.DISABLED
    row.route_reason="customer_disconnected_portal_only"
    db.add(AuditEvent(actor_customer_id=customer.id,
        action="customer_mt5_demo_portal_disconnected",
        entity_type="trading_account",entity_id=str(row.id),
        payload={"native_terminal_unchanged":True,"trading_authorized":False}))
    await db.commit()
    return {"disconnected":True,"native_terminal_unchanged":True,
            "trading_authorized":False}
