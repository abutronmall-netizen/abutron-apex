from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Customer, Role

settings = get_settings()
bearer = HTTPBearer(auto_error=False)
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def create_access_token(customer: Customer) -> tuple[str, int]:
    expires = timedelta(minutes=settings.access_token_minutes)
    now = datetime.now(UTC)
    payload = {
        "sub": str(customer.id),
        "role": customer.role.value,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + expires,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(expires.total_seconds())


async def get_current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
        )
        customer_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    customer = await db.get(Customer, customer_id)
    if customer is None or not customer.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    return customer


async def require_admin(customer: Customer = Depends(get_current_customer)) -> Customer:
    if customer.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return customer


async def require_service_token(
    x_abutron_service_token: str | None = Header(default=None),
) -> None:
    if not x_abutron_service_token or not hmac.compare_digest(
        x_abutron_service_token, settings.service_token
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token")
