from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.api import router
from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Base
from app.observability import RequestContextMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Abutron Kronos Platform",
    version="2.42.0",
    docs_url=None if settings.env.lower() in {"production", "prod", "staging"} else "/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Abutron-Service-Token",
        "X-Abutron-Signature",
        "X-Request-ID",
    ],
    expose_headers=["X-Request-ID"],
)

app.include_router(router)


@app.middleware("http")
async def portal_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'; object-src 'none'; "
        "connect-src 'self'; img-src 'self' data:; "
        "script-src 'self'; style-src 'self'"
    )
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
    # The public reverse proxy must also redirect HTTP and terminate genuine
    # domain-valid TLS; this header is NOT evidence that TLS is provisioned.
    if settings.env.lower() in {"production", "prod"}:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Fail-closed admission controls for external registration/login/verification.
# The proxy must preserve the connecting client IP, or supply a documented,
# trusted network identity. Never trust arbitrary X-Forwarded-For headers.
AUTH_WINDOWS = {
    "/api/v1/auth/register": (4, 900),
    "/api/v1/auth/login": (15, 600),
    "/api/v1/auth/verify-email": (12, 900),
    "/api/v1/auth/resend-verification": (4, 900),
}
AUTH_ATOMIC_THROTTLE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


@app.middleware("http")
async def release_auth_rate_limit(request: Request, call_next):
    if (settings.env.lower() in {"production", "prod", "staging"}
            and request.method == "POST"
            and request.url.path in AUTH_WINDOWS):
        if request.client is None or not request.client.host:
            return JSONResponse(status_code=503, content={"detail": "AUTH_CLIENT_ID_UNAVAILABLE"})
        count_limit, window = AUTH_WINDOWS[request.url.path]
        key = hashlib.sha256(
            (settings.jwt_secret + ":auth-ip:" + request.client.host
             + ":" + request.url.path).encode()
        ).hexdigest()
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            hits = int(await redis.eval(
                AUTH_ATOMIC_THROTTLE, 1, "abutron:auth:limit:" + key, window
            ))
        except Exception:  # noqa: BLE001 - fail closed for all throttle backend failures
            return JSONResponse(status_code=503, content={"detail": "AUTH_RATE_GATE_UNAVAILABLE"})
        finally:
            await redis.aclose()
        if hits > count_limit:
            return JSONResponse(status_code=429, content={"detail": "AUTH_RATE_LIMITED"},
                                headers={"Retry-After": str(window)})
    return await call_next(request)


@app.middleware("http")
async def recovery_financial_guard(request: Request, call_next):
    """Lock finance mutations in recovery and unverified public release modes."""
    locked = settings.env.startswith("recovery") or settings.env.lower() in {
        "production", "prod", "staging"
    }
    if locked and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        blocked_prefixes = (
            "/api/v1/billing/subscriptions",
            "/api/v1/internal/billing/",
            "/api/v1/webhooks/billing/",
            "/api/v1/admin/payments",
        )
        if request.url.path.startswith(blocked_prefixes):
            return JSONResponse(
                status_code=423,
                content={"detail": "RECOVERY_SANDBOX_FINANCIAL_MUTATION_DISABLED"},
            )
    return await call_next(request)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await redis.ping()
        finally:
            await redis.aclose()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Platform dependency unavailable") from exc

    return {"status": "ready"}
