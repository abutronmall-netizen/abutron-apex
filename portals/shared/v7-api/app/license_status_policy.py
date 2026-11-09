"""Fail-closed policy for the V7 licensing admin endpoint.

Administrative deactivation is permissible, but reactivation must never
turn on broker execution without independent billing and broker certification.
The route's require_admin dependency and database audit are mandatory.
"""
from fastapi import HTTPException, status
from app.models import LicenseStatus


def require_certified_license_transition(target: LicenseStatus) -> None:
    if target == LicenseStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="LICENSE_ACTIVATION_REQUIRES_INDEPENDENT_CERTIFICATION",
        )
    if target not in {
        LicenseStatus.SUSPENDED,
        LicenseStatus.EXPIRED,
        LicenseStatus.REVOKED,
        LicenseStatus.PENDING,
    }:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="LICENSE_MUTATIONS_DISABLED_PENDING_REVIEW",
        )
