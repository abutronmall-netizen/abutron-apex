"""Fail-closed, Redis-backed immediate JWT logout revocation, no raw tokens persisted."""
from __future__ import annotations

import hashlib
import hmac
import math
import time

import jwt
from fastapi import HTTPException
from redis.asyncio import Redis

from app.config import get_settings


def _token_expiry_and_key(token: str) -> tuple[str, int]:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "av"]},
        )
        if not isinstance(claims.get("exp"), int):
            raise ValueError("INVALID_EXP")
        remaining = math.ceil(claims["exp"] - time.time())
        if remaining <= 0 or remaining > max(86400, settings.access_token_minutes * 60 + 120):
            raise ValueError("INVALID_SESSION_LIFETIME")
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    digest = hmac.new(settings.jwt_secret.encode(), ("logout:" + token).encode(), hashlib.sha256).hexdigest()
    return "abutron:session-revoked:v1:" + digest, remaining


async def reject_revoked_session(token: str) -> None:
    key, _ = _token_expiry_and_key(token)
    try:
        redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="SESSION_REVOCATION_UNAVAILABLE") from exc
    try:
        try:
            blocked = await redis.exists(key)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="SESSION_REVOCATION_CHECK_UNAVAILABLE") from exc
        if blocked:
            raise HTTPException(status_code=401, detail="Session signed out")
    finally:
        await redis.aclose()


async def revoke_session(token: str) -> None:
    key, ttl = _token_expiry_and_key(token)
    try:
        redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="SESSION_REVOCATION_UNAVAILABLE") from exc
    try:
        try:
            success = await redis.set(key, "1", ex=ttl)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="SESSION_REVOCATION_UNAVAILABLE") from exc
        if not success:
            raise HTTPException(status_code=503, detail="SESSION_REVOCATION_UNAVAILABLE")
    finally:
        await redis.aclose()
