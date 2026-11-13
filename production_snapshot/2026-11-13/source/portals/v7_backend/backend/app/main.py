from __future__ import annotations

import hashlib
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.api import router
from app.customer_mt5_proof_routes import router as mt5_link_stepup_router
from app.owner_deriv_claim_routes import router as owner_deriv_claim_router
from app.mt5_customer_demo_routes import router as simple_mt5_demo_router
from app.deriv_market_readonly import router as deriv_public_router
from app.kronos_research_readonly import router as kronos_readonly_router
from app.deriv_candle_research_v1 import router as deriv_closed_candle_router
from app.profile_routes import router as customer_profile_router
from app.deriv_demo_status_readonly import router as deriv_demo_status_router
from app.deriv_options_multiplier_research import router as deriv_options_research_router
from app.trades_prop_verified import router as verified_history_router
from app.owner_deriv_snapshot_routes import router as owner_demo_snapshot_router
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
        "X-Abutron-MT5-CSRF",
    ],
    expose_headers=["X-Request-ID"],
)

app.include_router(router)
app.include_router(mt5_link_stepup_router)
app.include_router(owner_deriv_claim_router)
app.include_router(simple_mt5_demo_router)
app.include_router(deriv_public_router)
app.include_router(kronos_readonly_router)
app.include_router(deriv_closed_candle_router)
app.include_router(customer_profile_router)
app.include_router(deriv_demo_status_router)
app.include_router(deriv_options_research_router)
app.include_router(verified_history_router)
app.include_router(owner_demo_snapshot_router)


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
    "/api/v1/auth/forgot-password": (3, 900),
    "/api/v1/auth/reset-password": (6, 900),
    "/api/v1/auth/admin-mfa/verify": (5, 600),
    "/api/v1/auth/mt5-link/stepup/start": (3, 900),
    "/api/v1/auth/mt5-link/stepup/verify": (5, 600),
    "/api/v1/auth/mt5-link/enrollment/prepare": (3, 900),
    "/api/v1/auth/mt5-link/owner-deriv/claim": (3, 900),
    "/api/v1/auth/mt5-link/owner-deriv/unlink": (3, 900),
    "/api/v1/auth/mt5-link/native-demo/connect": (3, 900),
    "/api/v1/auth/mt5-link/native-demo/disconnect": (6, 600),
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


# The first public V7 customer portal is AUTHENTICATION + OBSERVATION ONLY.
# Block every other API mutation BEFORE route/business logic or database access.
# Do not infer permission from a JWT, role, path parameter, or UI button.
# Recovery sandbox keeps its independent private fixture operations intact.
PUBLIC_READ_ONLY_AUTH_MUTATIONS = frozenset({
    "/api/v1/auth/register",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/resend-verification",
    "/api/v1/auth/login",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/logout",
    "/api/v1/auth/admin-mfa/verify",
    "/api/v1/auth/mt5-link/stepup/start",
    "/api/v1/auth/mt5-link/stepup/verify",
    "/api/v1/auth/mt5-link/enrollment/prepare",
    "/api/v1/auth/mt5-link/owner-deriv/claim",
    "/api/v1/auth/mt5-link/owner-deriv/unlink",
    "/api/v1/auth/mt5-link/native-demo/connect",
    "/api/v1/auth/mt5-link/native-demo/disconnect",
})


def permitted_customer_notification_ack(method: str, path: str) -> bool:
    """The sole nonfinancial public V7 write: signed-in user marks own notice read.

    Matching a canonical UUID path is deliberate: no '*' or arbitrary custom
    payload paths may bypass the release-wide fail-closed mutation lock.
    Authentication + record ownership remain enforced inside the API route.
    """
    prefix = "/api/v1/notifications/"
    suffix = "/read"
    if method != "PATCH" or not path.startswith(prefix) or not path.endswith(suffix):
        return False
    segment = path[len(prefix):-len(suffix)]
    if not segment or "/" in segment or len(segment) != 36:
        return False
    try:
        return str(uuid.UUID(segment)) == segment.lower()
    except ValueError:
        return False


@app.middleware("http")
async def public_read_only_mutation_guard(request: Request, call_next):
    if (settings.env.strip().lower() in {"production", "prod", "staging"}
            and request.url.path.startswith("/api/v1/")
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path not in PUBLIC_READ_ONLY_AUTH_MUTATIONS
            and not permitted_customer_notification_ack(request.method, request.url.path)
            and not (request.method == "PUT" and request.url.path == "/api/v1/me/profile")):
        return JSONResponse(
            status_code=423,
            content={"detail": "V7_PUBLIC_READ_ONLY_MUTATION_DISABLED"},
            headers={"Cache-Control": "no-store"},
        )
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
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
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
