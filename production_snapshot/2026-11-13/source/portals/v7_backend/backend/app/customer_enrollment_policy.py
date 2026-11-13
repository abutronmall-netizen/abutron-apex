"""Release gate for stage-one existing-customer-only enrollment.

This gate does not certify a recovered customer roster or authorize public
deployment. It prevents creation of unverified production identities until
authoritative customer provenance and onboarding are independently reviewed.
"""
from fastapi import HTTPException, status


def require_reconciled_customer_onboarding(environment: str) -> None:
    if environment.strip().lower() in {"production", "prod", "staging"}:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="NEW_CUSTOMER_ENROLLMENT_REQUIRES_VERIFIED_IDENTITY_SOURCE",
        )
