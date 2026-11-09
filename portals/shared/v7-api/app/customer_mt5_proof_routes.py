"""Customer MT5-link step-up: proof only. Does NOT accept MT5 passwords."""
from __future__ import annotations
import hashlib,hmac,secrets,time,uuid
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field,SecretStr
from redis.asyncio import Redis
from sqlalchemy import select
import httpx
from app.config import get_settings,approved_release_origin
from app.models import Customer,Role
from app.security import get_current_customer,verify_password,auth_version
from app.email_verification import ensure_mail_ready
from app.customer_mt5_stepup_service import begin,complete,StepupUnavailable
from app.customer_mt5_enrollment_prepare_v1 import (
    issue_verified_ticket, consume_verified_ticket, reserve_customer_attempt, PrepareUnavailable,
)

router=APIRouter(prefix="/api/v1/auth/mt5-link",tags=["mt5-link-stepup"])
COOKIE="abutron_mt5_csrf"
class StartRequest(BaseModel):
    portal_password: SecretStr = Field(repr=False)
class VerifyRequest(BaseModel):
    challenge:str=Field(min_length=43,max_length=43)
    code:str=Field(min_length=6,max_length=6)
class PrepareRequest(BaseModel):
    mfa_ticket:str=Field(min_length=43,max_length=43,repr=False)

def require_customer(customer):
    if customer.role!=Role.CUSTOMER or not customer.is_active:
        raise HTTPException(status_code=403,detail="CUSTOMER_SESSION_REQUIRED")
    return customer

def csrf_mac(customer,nonce,at):
    key=get_settings().jwt_secret.encode()
    data="mt5-stepup-csrf-v1|"+str(customer.id)+"|"+auth_version(customer)+"|"+str(at)+"|"+nonce
    return hmac.new(key,data.encode(),hashlib.sha256).hexdigest()

def csrf_check(request,customer):
    origin=request.headers.get("origin","")
    if not approved_release_origin(origin):
        raise HTTPException(status_code=403,detail="MT5_SECURITY_PROOF_DENIED")
    raw=request.cookies.get(COOKIE,"")
    supplied=request.headers.get("x-abutron-mt5-csrf","")
    if not supplied or not hmac.compare_digest(raw,supplied):
        raise HTTPException(status_code=403,detail="MT5_SECURITY_PROOF_DENIED")
    fields=raw.split(".")
    if len(fields)!=3:
        raise HTTPException(status_code=403,detail="MT5_SECURITY_PROOF_DENIED")
    nonce,at_txt,mac=fields
    try:at=int(at_txt)
    except ValueError:at=0
    if len(nonce)!=43 or not (0<=int(time.time())-at<=300):
        raise HTTPException(status_code=403,detail="MT5_SECURITY_PROOF_DENIED")
    if not hmac.compare_digest(mac,csrf_mac(customer,nonce,at)):
        raise HTTPException(status_code=403,detail="MT5_SECURITY_PROOF_DENIED")

@router.get("/csrf")
async def get_mt5_link_csrf(response:Response,
         customer:Customer=Depends(get_current_customer)):
    require_customer(customer)
    nonce=secrets.token_urlsafe(32)
    at=int(time.time())
    token=nonce+"."+str(at)+"."+csrf_mac(customer,nonce,at)
    response.set_cookie(COOKIE,token,max_age=300,secure=True,httponly=True,
                        samesite="strict",path="/api/v1/auth/mt5-link")
    return {"csrf_token":token,"expires_seconds":300,
            "broker_password_collection_enabled":False}

@router.post("/stepup/start")
async def start_mt5_link_stepup(req:StartRequest,request:Request,
         customer:Customer=Depends(get_current_customer)):
    require_customer(customer)
    csrf_check(request,customer)
    if not verify_password(req.portal_password.get_secret_value(),customer.password_hash):
        raise HTTPException(status_code=401,detail="INVALID_CUSTOMER_AUTHORIZATION")
    if not request.client or not request.client.host:
        raise HTTPException(status_code=503,detail="MT5_IDENTITY_UNAVAILABLE")
    ensure_mail_ready()
    settings=get_settings()
    async def private_delivery(code):
        async with httpx.AsyncClient(timeout=8) as client:
            result=await client.post("https://api.resend.com/emails",
               headers={"Authorization":"Bearer "+settings.resend_api_key},
               json={"from":settings.verification_from_email,"to":[customer.email],
                 "subject":"Abutron MT5 account linking security code",
                 "html":"<p>Your Abutron MT5-link security code is: <strong>"+code+
                        "</strong></p><p>Expires in five minutes. No broker account was linked.</p>"})
            result.raise_for_status()
    redis=Redis.from_url(settings.redis_url,decode_responses=True)
    try:
        result=await begin(redis=redis,secret=settings.jwt_secret.encode(),
           owner=str(customer.id),auth_version=auth_version(customer),
           remote_ip=request.client.host,fresh_auth=True,
           send_private_code=private_delivery)
    except StepupUnavailable:
        raise HTTPException(status_code=503,detail="MT5_STEPUP_TEMPORARILY_UNAVAILABLE") from None
    finally:
        await redis.aclose()
    return result

@router.post("/stepup/verify")
async def verify_mt5_link_stepup(req:VerifyRequest,request:Request,
         customer:Customer=Depends(get_current_customer)):
    require_customer(customer)
    csrf_check(request,customer)
    settings=get_settings()
    redis=Redis.from_url(settings.redis_url,decode_responses=True)
    try:
        result=await complete(redis=redis,secret=settings.jwt_secret.encode(),
           owner=str(customer.id),auth_version=auth_version(customer),
           challenge=req.challenge,code=req.code)
        if result.get('mfa_verified') is not True:
            raise StepupUnavailable('SECOND_FACTOR_REQUIRED')
        result['mfa_ticket']=await issue_verified_ticket(
            redis=redis,secret=settings.jwt_secret.encode(),
            owner=str(customer.id),auth_version=auth_version(customer))
    except PrepareUnavailable:
        raise HTTPException(status_code=503,detail='MT5_STEPUP_TEMPORARILY_UNAVAILABLE') from None
    except StepupUnavailable:
        raise HTTPException(status_code=400,detail="MT5_STEPUP_INVALID_OR_EXPIRED") from None
    finally:
        await redis.aclose()
    return result


@router.post("/enrollment/prepare")
async def prepare_mt5_link_enrollment(req:PrepareRequest,request:Request,
         customer:Customer=Depends(get_current_customer)):
    """One-use OTP proof -> atomic shared reservation; no MT5 passwords/broker contact."""
    require_customer(customer)
    csrf_check(request,customer)
    if request.client is None or not request.client.host:
        raise HTTPException(status_code=503,detail="MT5_SECURITY_SERVICE_UNAVAILABLE")
    settings=get_settings()
    redis=Redis.from_url(settings.redis_url,decode_responses=True)
    try:
        await consume_verified_ticket(redis=redis,secret=settings.jwt_secret.encode(),
            owner=str(customer.id),auth_version=auth_version(customer),token=req.mfa_ticket)
    except PrepareUnavailable:
        raise HTTPException(status_code=403,detail="MT5_SECURITY_PROOF_DENIED") from None
    finally:
        await redis.aclose()
    try:
        return reserve_customer_attempt(
            owner=str(customer.id),validated_client_ip=request.client.host)
    except PrepareUnavailable:
        raise HTTPException(status_code=429,detail="MT5_ENROLLMENT_NOT_AVAILABLE") from None
