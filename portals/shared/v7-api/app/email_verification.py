"""New-customer onboarding with email ownership proof (no broker entitlements).

Release environments fail closed if outbound verification mail is unavailable.
Tokens are bound to one email/customer, short-lived, and cannot be used as JWT
bearer login tokens. A customer is activated only after proof of email control.
"""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
import uuid

import httpx
import jwt
from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings


class VerificationRequest(BaseModel):
    token: str = Field(min_length=32, max_length=4096)


def requires_email_verification(env: str) -> bool:
    return env.strip().lower() in {"production", "prod", "staging"}


def ensure_mail_ready() -> None:
    s = get_settings()
    if (not s.resend_api_key or not s.verification_from_email
            or not s.public_base_url.startswith("https://")):
        raise HTTPException(status_code=503, detail="REGISTRATION_EMAIL_VERIFICATION_UNAVAILABLE")


def make_email_proof(customer_id: uuid.UUID, email: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    return jwt.encode({
        "sub": str(customer_id),
        "email": email.strip().lower(),
        "purpose": "abutron_email_verification_v1",
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }, s.jwt_secret, algorithm="HS256")


def parse_email_proof(token: str) -> tuple[uuid.UUID, str]:
    try:
        data = jwt.decode(
            token, get_settings().jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "purpose", "email"]},
        )
        if data["purpose"] != "abutron_email_verification_v1":
            raise ValueError("wrong token purpose")
        identity = uuid.UUID(data["sub"])
        email = str(data["email"]).strip().lower()
        if not email or "@" not in email:
            raise ValueError("invalid verification email")
        return identity, email
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=400, detail="INVALID_OR_EXPIRED_VERIFICATION") from exc


async def send_email_proof(email: str, customer_id: uuid.UUID) -> None:
    """Email only the confirmation link; never log the token or recipient."""
    ensure_mail_ready()
    s = get_settings()
    token = make_email_proof(customer_id, email)
    link = s.public_base_url.rstrip("/") + "/#verify-email=" + quote(token, safe="")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            result = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + s.resend_api_key},
                json={
                    "from": s.verification_from_email,
                    "to": [email],
                    "subject": "Confirm your Abutron portal email",
                    "html": '<p>Confirm your email to activate your read-only Abutron portal account.</p>'
                            + '<p><a href="' + link + '">Verify email</a></p>'
                            + '<p>Expires in 30 minutes. This does not enable trading.</p>',
                },
            )
            result.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="REGISTRATION_EMAIL_DELIVERY_FAILED"
        ) from exc
