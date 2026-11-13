"""APEX 1.1 -> exact root-approved V4 native file port, DEMO 6207 only.

The APEX writer acquires the existing exclusive flock and performs native
broker/risk preflight before calling this port. Only a root-owned, revision-
matched approved intent may be queued. No legacy V2/V3 transport fallback.
"""
import os
import runpy
import stat
from pathlib import Path

from abutron_replacement.native_v4_file_port import NativeV4FilePort
from abutron_replacement.production_contracts import FeedRefused

DIRECT_AUTH=Path("/usr/local/sbin/abutron-v4-readonly-status-6207")

class RootCRMApprovedV4FilePort(NativeV4FilePort):
    def queue_once(self, request, evidence):
        # Require all native identity, stop geometry, expiry and V4 EA
        # capability checks BEFORE reserving the root CRM order intent.
        self.assert_ready(request,evidence)
        if os.geteuid()!=0:
            raise FeedRefused("DIRECT_CRM_APPROVAL_REQUIRES_ROOT_WRITER")
        source=DIRECT_AUTH
        if source.is_symlink():
            raise FeedRefused("DIRECT_CRM_APPROVAL_UNTRUSTED_AUTHORITY")
        st=source.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or
            stat.S_IMODE(st.st_mode)!=0o500 or st.st_nlink!=1):
            raise FeedRefused("DIRECT_CRM_APPROVAL_UNTRUSTED_AUTHORITY")
        contract=runpy.run_path(str(source),run_name="_v4_root_approved_intent")
        try:
            contract["direct_prepare"](request,evidence)
        except Exception as exc:
            raise FeedRefused("DIRECT_CRM_ROOT_APPROVED_INTENT_MISSING") from exc
        # Approval is deliberately recorded before the atomic native file
        # publication. Failed publications remain UNKNOWN with held risk;
        # never retry automatically or revive an expired approved intent.
        return super().queue_once(request,evidence)
