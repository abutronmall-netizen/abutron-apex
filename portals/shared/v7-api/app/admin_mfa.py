"""Admin/SUPERADMIN second-factor email code with one-time Redis challenge.

The customer login path remains password-only and read-only. Verified admin
accounts must prove mailbox access before a bearer session is issued.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

import httpx
from fastapi import HTTPException
from redis.asyncio import Redis

from app.config import get_settings
from app.email_verification import ensure_mail_ready
from app.password_recovery import TOKEN_PATTERN

MFA_TTL=300


def challenge_key(challenge:str)->str:
    if not TOKEN_PATTERN.fullmatch(challenge):
        raise HTTPException(status_code=400,detail="ADMIN_MFA_INVALID_OR_EXPIRED")
    digest=hmac.new(get_settings().jwt_secret.encode(),
        ("admin-mfa-id:"+challenge).encode(),hashlib.sha256).hexdigest()
    return "abutron:admin-mfa:v1:"+digest


def code_digest(challenge:str,code:str)->str:
    return hmac.new(get_settings().jwt_secret.encode(),
        ("admin-mfa-code:"+challenge+":"+code).encode(),hashlib.sha256).hexdigest()


async def begin_admin_mfa(customer_id:uuid.UUID,email:str)->str:
    ensure_mail_ready()
    config=get_settings()
    challenge=secrets.token_urlsafe(32)
    code=f"{secrets.randbelow(1000000):06d}"
    redis=Redis.from_url(config.redis_url,decode_responses=True)
    key=challenge_key(challenge)
    try:
        try:
            stored=await redis.set(key,str(customer_id)+":"+code_digest(challenge,code),
                ex=MFA_TTL,nx=True)
            if not stored:raise ValueError("duplicate mfa challenge")
        except Exception as exc:
            raise HTTPException(status_code=503,detail="ADMIN_MFA_TEMPORARILY_UNAVAILABLE") from exc
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r=await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization":"Bearer "+config.resend_api_key},
                    json={
                        "from":config.verification_from_email,
                        "to":[email],
                        "subject":"Abutron Admin security code",
                        "html":"<p>Your one-time administrator sign-in code is:</p>"
                               +"<p><strong>"+code+"</strong></p>"
                               +"<p>Valid for 5 minutes and only one attempt. "
                               +"If you did not sign in, change your account password and contact security.</p>",
                    })
                r.raise_for_status()
        except (httpx.HTTPError,ValueError) as exc:
            await redis.delete(key)
            raise HTTPException(status_code=503,detail="ADMIN_MFA_TEMPORARILY_UNAVAILABLE") from exc
    finally:
        await redis.aclose()
    return challenge


async def complete_admin_mfa(challenge:str,code:str)->uuid.UUID:
    if not isinstance(code,str) or len(code)!=6 or not code.isascii() or not code.isdecimal():
        raise HTTPException(status_code=400,detail="ADMIN_MFA_INVALID_OR_EXPIRED")
    key=challenge_key(challenge)
    redis=Redis.from_url(get_settings().redis_url,decode_responses=True)
    try:
        try:
            data=await redis.getdel(key) # One attempt, consumed atomically even if incorrect.
        except Exception as exc:
            raise HTTPException(status_code=503,detail="ADMIN_MFA_TEMPORARILY_UNAVAILABLE") from exc
    finally:
        await redis.aclose()
    if not data or ":" not in data:
        raise HTTPException(status_code=400,detail="ADMIN_MFA_INVALID_OR_EXPIRED")
    user_id,expected=data.split(":",1)
    if not hmac.compare_digest(expected,code_digest(challenge,code)):
        raise HTTPException(status_code=400,detail="ADMIN_MFA_INVALID_OR_EXPIRED")
    try:return uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail="ADMIN_MFA_INVALID_OR_EXPIRED") from exc
