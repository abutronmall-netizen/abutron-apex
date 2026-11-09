"""One-use, 15-minute Redis-backed customer password recovery.

No admin/SUPERADMIN reset via unauthenticated email. Generic responses avoid
email existence disclosure. Redis failures fail closed. Never logs a token,
secret, password, recipient or personal account data.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from redis.asyncio import Redis

from app.config import get_settings
from app.email_verification import ensure_mail_ready

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$", re.ASCII)
TOKEN_LIFETIME = 900
GENERIC = {"status": "If the address is eligible, a recovery email has been requested."}


def reset_key(token: str) -> str:
    if not TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(status_code=400, detail="INVALID_OR_EXPIRED_RESET")
    secret = get_settings().jwt_secret.encode()
    digest = hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()
    return "abutron:password-reset:v1:" + digest


async def send_customer_reset(email: str, customer_id: uuid.UUID) -> None:
    ensure_mail_ready()
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    key = reset_key(token)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        try:
            if not await redis.set(key, str(customer_id), ex=TOKEN_LIFETIME, nx=True):
                raise RuntimeError("DUPLICATE_PASSWORD_RESET_TOKEN")
        except Exception as exc:
            raise HTTPException(status_code=503, detail="RESET_TEMPORARILY_UNAVAILABLE") from exc
        url = settings.public_base_url.rstrip("/") + "/#reset-password=" + quote(token, safe="")
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": "Bearer " + settings.resend_api_key},
                    json={
                        "from": settings.verification_from_email,
                        "to": [email],
                        "subject": "Reset your Abutron portal password",
                        "html": (
                            "<p>A password reset was requested for your Abutron customer account.</p>"
                            '<p><a href="' + url + '">Reset password</a></p>'
                            "<p>The link expires in 15 minutes and works once.</p>"
                            "<p>If this wasn't you, ignore this message.</p>"
                        ),
                    },
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            await redis.delete(key)
            raise HTTPException(status_code=503, detail="RESET_TEMPORARILY_UNAVAILABLE") from exc
    finally:
        await redis.aclose()


async def consume_customer_reset(token: str) -> uuid.UUID:
    key = reset_key(token)
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        try:
            owner = await redis.getdel(key)  # Atomic one-use token redemption.
        except Exception as exc:
            raise HTTPException(status_code=503, detail="RESET_TEMPORARILY_UNAVAILABLE") from exc
    finally:
        await redis.aclose()
    if not owner:
        raise HTTPException(status_code=400, detail="INVALID_OR_EXPIRED_RESET")
    try:
        return uuid.UUID(owner)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="INVALID_OR_EXPIRED_RESET") from exc
