"""Customer MT5 linking enrollment PREPARE only: real owner-bound MFA proof
plus shared multi-process reservation. Never accepts or stores broker credentials,
never invokes MT5, and never authorizes order execution or public enrollment.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import pathlib
import secrets
import stat

from app.mt5_shared_enrollment_gate import SharedEnrollmentGate, EnrollmentBlocked

STORAGE = pathlib.Path("/var/lib/abutron-v7-mt5-enrollment-gate")
PROOF_PREFIX = "abutron:mt5:enroll:proof:v1:"

class PrepareUnavailable(Exception):
    pass

def _digest(secret: bytes, token: str) -> str:
    return hmac.new(secret, ("mt5:customer:enroll:proof:v1|" + token).encode(), hashlib.sha256).hexdigest()

async def issue_verified_ticket(*, redis, secret: bytes, owner: str, auth_version: str) -> str:
    """Only call immediately after the actual second-factor verifier succeeds."""
    token = secrets.token_urlsafe(32)
    key = PROOF_PREFIX + _digest(secret, token)
    try:
        created = await redis.set(key, owner + "|" + auth_version, ex=120, nx=True)
    except Exception:
        raise PrepareUnavailable("PROOF_SERVICE_UNAVAILABLE") from None
    if not created:
        raise PrepareUnavailable("PROOF_COLLISION")
    return token

async def consume_verified_ticket(*, redis, secret: bytes, owner: str, auth_version: str, token: str) -> None:
    if not isinstance(token, str) or len(token) != 43:
        raise PrepareUnavailable("INVALID_PROOF")
    try:
        saved = await redis.getdel(PROOF_PREFIX + _digest(secret, token))
    except Exception:
        raise PrepareUnavailable("PROOF_SERVICE_UNAVAILABLE") from None
    if not isinstance(saved, str) or not hmac.compare_digest(saved, owner + "|" + auth_version):
        raise PrepareUnavailable("INVALID_PROOF")

def _private_key() -> bytes:
    path = STORAGE / "owner-gate.key"
    try:
        d = STORAGE.lstat()
        s = path.lstat()
        if (not stat.S_ISDIR(d.st_mode) or stat.S_IMODE(d.st_mode) != 0o700
            or d.st_uid != os.getuid() or not stat.S_ISREG(s.st_mode)
            or stat.S_IMODE(s.st_mode) != 0o400 or s.st_uid != os.getuid()
            or path.is_symlink()):
            raise PrepareUnavailable("UNSAFE_GATE_STORAGE")
        key = path.read_bytes()
        if len(key) != 32:
            raise PrepareUnavailable("INVALID_GATE_KEY")
        return key
    except OSError:
        raise PrepareUnavailable("GATE_STORAGE_UNAVAILABLE") from None

def reserve_customer_attempt(*, owner: str, validated_client_ip: str) -> dict:
    """No broker password fields. Claims zero broker authentication."""
    try:
        gate = SharedEnrollmentGate(str(STORAGE), _private_key())
        nonce = gate.issue_challenge(owner)
        result = gate.consume(owner, validated_client_ip, nonce)
    except EnrollmentBlocked:
        raise PrepareUnavailable("SHARED_ENROLLMENT_GATE_DENIED") from None
    except Exception:
        raise PrepareUnavailable("SHARED_ENROLLMENT_GATE_UNAVAILABLE") from None
    if result != {
        "reserved": True, "broker_verified": False, "password_collected": False,
        "can_execute_orders": False, "enrollment_publicly_enabled": False
    }:
        raise PrepareUnavailable("UNEXPECTED_RESERVATION_STATE")
    return {
        "security_reservation_accepted": True,
        "broker_password_collection_enabled": False,
        "broker_connected": False,
        "order_execution_enabled": False,
        "enrollment_publicly_enabled": False
    }
