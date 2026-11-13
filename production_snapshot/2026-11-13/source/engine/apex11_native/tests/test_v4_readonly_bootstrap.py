"""The V4 bootstrap may prove attachment without granting order authority."""
from dataclasses import replace
from datetime import timedelta
import pytest

from abutron_replacement.native_v4_broker_authority import (
    NativeV4AttachmentEvidence, Verified6207NativeAuthority,
)
from abutron_replacement.production_contracts import FeedRefused
from test_native_v4_broker_authority import build
from test_exclusive_native_writer import OWNER, CID


def test_pre_ack_v4_status_only_with_real_independent_attachment_proof(tmp_path):
    x, identity, authority, fence, now = build(tmp_path)
    activation = x["activation"]
    old = activation.snapshot(account_id=CID, customer_id=OWNER, now=now)
    # ON requested at a new revision. The *effective* state must remain OFF.
    activation.request(account_id=CID, customer_id=OWNER,
                       desired_on=True, expected_revision=old.revision, now=now)
    pending = activation.snapshot(account_id=CID, customer_id=OWNER, now=now)
    assert pending.desired_on and not pending.effective_on
    with pytest.raises(FeedRefused, match="BOOTSTRAP_SUPERVISOR_UNAVAILABLE"):
        authority.attest_session(customer_id=OWNER, account_id=CID,
                                 worker_nonce=identity.worker_nonce,
                                 mt5_login=identity.login, now=now)

    verified = NativeV4AttachmentEvidence(
        customer_id=OWNER, account_id=CID, mt5_login=identity.login,
        worker_nonce=identity.worker_nonce, broker="deriv",
        environment="DEMO", server="Deriv-Demo",
        activation_revision=pending.revision, verified_at=now,
        crm_owner_mfa_verified=True, apex_v7_owner_verified=True,
        broker_session_authenticated=True, native_worker_verified=True,
        exact_v4_binary_attached=True, production_v4_release_certified=True,
        shared_writer_fenced=True, live_execution_disabled=True)
    x["supervisor"].attest_attachment = lambda **kw: verified
    assert authority.attest_session(customer_id=OWNER, account_id=CID,
                                    worker_nonce=identity.worker_nonce,
                                    mt5_login=identity.login, now=now) == pending.revision

    # A read-only capability/status is NEVER authorization for CLAIM or SEND.
    proposed = replace(identity, revision=pending.revision)
    with pytest.raises(FeedRefused, match="CLIENT_OFF_OR_REVISED"):
        authority.assert_eligible(identity=proposed, phase="CLAIM", now=now)
    with pytest.raises(FeedRefused, match="CLIENT_OFF_OR_REVISED"):
        authority.assert_eligible(identity=proposed, phase="SEND", now=now)

    for forged in (
        replace(verified, live_execution_disabled=False),
        replace(verified, production_v4_release_certified=False),
        replace(verified, broker_session_authenticated=False),
        replace(verified, exact_v4_binary_attached=False),
        replace(verified, apex_v7_owner_verified=False),
        replace(verified, shared_writer_fenced=False),
        replace(verified, activation_revision=old.revision),
        replace(verified, worker_nonce="0"*32),
    ):
        x["supervisor"].attest_attachment = lambda **kw: forged
        with pytest.raises(FeedRefused):
            authority.attest_session(customer_id=OWNER, account_id=CID,
                                     worker_nonce=identity.worker_nonce,
                                     mt5_login=identity.login, now=now)
    x["supervisor"].attest_attachment = lambda **kw: replace(
        verified, verified_at=now-timedelta(seconds=20))
    with pytest.raises(FeedRefused, match="EVIDENCE_STALE"):
        authority.attest_session(customer_id=OWNER, account_id=CID,
                                 worker_nonce=identity.worker_nonce,
                                 mt5_login=identity.login, now=now)

    current = activation.snapshot(account_id=CID, customer_id=OWNER, now=now)
    activation.request(account_id=CID, customer_id=OWNER, desired_on=False,
                       expected_revision=current.revision, now=now)
    x["supervisor"].attest_attachment = lambda **kw: verified
    with pytest.raises(FeedRefused, match="ACCOUNT_NOT_EFFECTIVE"):
        authority.attest_session(customer_id=OWNER, account_id=CID,
                                 worker_nonce=identity.worker_nonce,
                                 mt5_login=identity.login, now=now)
