"""V7 account-withdrawal suppression. Staged review candidate; no live approval.
No plain-text email stored. Every registry/key error fails CLOSED.
HMAC identity lock shared with independently reviewed suppression operator.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

from fastapi import HTTPException
from sqlalchemy import text

DOMAIN = b"abutron-v7-customer-optout-v1\x00"
KEY_ENV = "ABUTRON_V7_PRIVACY_OPTOUT_KEY"
FAIL = "REGISTRATION_POLICY_UNAVAILABLE"


def normalize(email: str) -> str:
    return email.strip().casefold()


def fingerprint(email: str) -> str:
    key_hex = os.environ.get(KEY_ENV, "")
    if re.fullmatch(r"[0-9a-fA-F]{64}", key_hex) is None:
        raise HTTPException(status_code=503, detail=FAIL)
    key = bytes.fromhex(key_hex)
    if not any(key):
        raise HTTPException(status_code=503, detail=FAIL)
    return hmac.new(key, DOMAIN + normalize(email).encode("utf8"), hashlib.sha256).hexdigest()


def advisory_key(digest: str) -> int:
    # Same deterministic 64-bit signed PostgreSQL transaction lock for signup and
    # owner-approved opt-out INSERT. Operators MUST take this lock before inserting.
    return int.from_bytes(bytes.fromhex(digest)[:8], "big", signed=True)


async def lock_and_check_optout(db, email: str) -> bool:
    digest = fingerprint(email)
    try:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": advisory_key(digest)},
        )
        value = await db.scalar(
            text("SELECT EXISTS (SELECT 1 FROM public.customer_email_optouts WHERE email_hmac = :digest)"),
            {"digest": digest},
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=FAIL) from exc
    if value is not True and value is not False:
        raise HTTPException(status_code=503, detail=FAIL)
    return value


async def require_not_opted_out(db, email: str, *, denial=409, detail="Account action unavailable") -> None:
    if await lock_and_check_optout(db, email):
        raise HTTPException(status_code=denial, detail=detail)
