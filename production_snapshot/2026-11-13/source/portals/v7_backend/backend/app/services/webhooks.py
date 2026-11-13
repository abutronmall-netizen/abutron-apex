from __future__ import annotations

import hashlib
import hmac


def sign_payload(secret: str, payload: bytes) -> str:
    if not secret:
        raise ValueError("Webhook secret is required")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(secret: str, payload: bytes, provided_signature: str | None) -> bool:
    if not secret or not provided_signature:
        return False

    signature = provided_signature.strip()
    if signature.lower().startswith("sha256="):
        signature = signature.split("=", 1)[1]

    expected = sign_payload(secret, payload)
    return hmac.compare_digest(expected, signature.lower())
