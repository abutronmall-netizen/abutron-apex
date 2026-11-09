"""Do not accept self-asserted broker ownership in an unverified release.

Until broker OAuth or equivalent ownership attestation is certified, public
accounts may authenticate and read only their own records. No new broker
account can be claimed by typing someone else's account identifier.
"""
from fastapi import HTTPException


def require_certified_broker_account_linking(environment: str) -> None:
    if environment.strip().lower() in {"production", "prod", "staging"}:
        raise HTTPException(
            status_code=423,
            detail="BROKER_ACCOUNT_LINKING_REQUIRES_OWNERSHIP_ATTESTATION",
        )
