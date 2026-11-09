"""Advertise only independently certified customer capabilities.

Private V7 recovery previews and the first portal-only public release are
observe-only.  Do not infer feature availability from a production environment
label or the presence of an integration URL.  Separate, reviewed certification
and deployment switches are required before any of these can be enabled.
"""
from __future__ import annotations

CAPABILITIES = (
    "android",
    "ios",
    "push_notifications",
    "billing",
    "live_kronos_assignment",
)


def mobile_feature_flags() -> dict[str, bool]:
    """Fail closed for all environments until feature-specific release gates exist."""
    return {name: False for name in CAPABILITIES}
