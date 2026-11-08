import pytest
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from abutron_replacement.transactional_activation import ActivationStore

NOW=datetime(2026,11,8,tzinfo=timezone.utc)

@pytest.fixture
def store(tmp_path):
    st=ActivationStore(tmp_path/'activation.sqlite3')
    st.provision(account_id='deriv6207',customer_id='ownerA',broker='deriv',now=NOW)
    return st


def attested(st, account='deriv6207', customer='ownerA'):
    s=st.snapshot(account_id=account,customer_id=customer,now=NOW)
    return st.update_attestation(account_id=account,customer_id=customer,
        expected_revision=s.revision,entitlement_ok=True,connected=True,
        writer_verified=True,kill_switch=False,now=NOW)


def test_new_account_is_effectively_off(store):
    s=store.snapshot(account_id='deriv6207',customer_id='ownerA',now=NOW)
    assert s.revision==1 and not s.desired_on and not s.effective_on and s.kill_switch


def test_on_requires_attestation_then_matching_ack(store):
    t=store.request(account_id='deriv6207',customer_id='ownerA',expected_revision=1,desired_on=True,now=NOW)
    assert t.desired_on and not t.effective_on
    with pytest.raises(PermissionError):
        store.acknowledge(account_id='deriv6207',customer_id='ownerA',expected_revision=t.revision,now=NOW)
    t=attested(store)
    assert store.acknowledge(account_id='deriv6207',customer_id='ownerA',expected_revision=t.revision,now=NOW).effective_on


def test_off_revokes_effective_on_and_stale_ack(store):
    on=store.request(account_id='deriv6207',customer_id='ownerA',expected_revision=1,desired_on=True,now=NOW)
    t=attested(store)
    store.acknowledge(account_id='deriv6207',customer_id='ownerA',expected_revision=t.revision,now=NOW)
    off=store.request(account_id='deriv6207',customer_id='ownerA',expected_revision=t.revision,desired_on=False,now=NOW)
    assert not off.effective_on and not off.desired_on
    with pytest.raises(ValueError, match='STALE'):
        store.acknowledge(account_id='deriv6207',customer_id='ownerA',expected_revision=t.revision,now=NOW)


def test_kill_switch_attestation_revokes_effective(store):
    store.request(account_id='deriv6207',customer_id='ownerA',expected_revision=1,desired_on=True,now=NOW)
    t=attested(store)
    store.acknowledge(account_id='deriv6207',customer_id='ownerA',expected_revision=t.revision,now=NOW)
    revoked=store.update_attestation(account_id='deriv6207',customer_id='ownerA',
        expected_revision=t.revision,entitlement_ok=True,connected=True,
        writer_verified=True,kill_switch=True,now=NOW)
    assert not revoked.effective_on
    with pytest.raises(PermissionError):
        store.acknowledge(account_id='deriv6207',customer_id='ownerA',expected_revision=revoked.revision,now=NOW)


def test_wrong_customer_cannot_edit(store):
    with pytest.raises(PermissionError):
        store.request(account_id='deriv6207',customer_id='attacker',expected_revision=1,desired_on=True,now=NOW)


def test_second_account_off_does_not_affect_first(store):
    store.provision(account_id='fp0512',customer_id='ownerA',broker='fp_markets',now=NOW)
    store.request(account_id='deriv6207',customer_id='ownerA',expected_revision=1,desired_on=True,now=NOW)
    t=attested(store)
    store.acknowledge(account_id='deriv6207',customer_id='ownerA',expected_revision=t.revision,now=NOW)
    assert not store.snapshot(account_id='fp0512',customer_id='ownerA',now=NOW).effective_on
    assert store.snapshot(account_id='deriv6207',customer_id='ownerA',now=NOW).effective_on


def test_concurrent_portal_changes_only_one_revision_wins(store):
    def request(_):
        try:
            store.request(account_id='deriv6207',customer_id='ownerA',expected_revision=1,desired_on=True,now=NOW)
            return 'ok'
        except ValueError:
            return 'stale'
    with ThreadPoolExecutor(max_workers=8) as pool:
        r=list(pool.map(request,range(20)))
    assert r.count('ok')==1 and r.count('stale')==19


def test_restart_persists_effective_state_and_revision(store):
    store.request(account_id='deriv6207',customer_id='ownerA',expected_revision=1,desired_on=True,now=NOW)
    t=attested(store)
    store.acknowledge(account_id='deriv6207',customer_id='ownerA',expected_revision=t.revision,now=NOW)
    another=ActivationStore(store.db_path)
    state=another.snapshot(account_id='deriv6207',customer_id='ownerA',now=NOW)
    assert state.revision==t.revision and state.effective_on
    expired=another.snapshot(account_id='deriv6207',customer_id='ownerA',now=NOW+timedelta(seconds=16))
    assert not expired.effective_on


def test_reprovision_does_not_override_existing_off(store):
    assert not store.provision(account_id='deriv6207',customer_id='ownerA',broker='deriv',now=NOW).effective_on
    with pytest.raises(PermissionError):
        store.provision(account_id='deriv6207',customer_id='other',broker='deriv',now=NOW)
    with pytest.raises(PermissionError):
        store.provision(account_id='deriv6207',customer_id='ownerA',broker='fp_markets',now=NOW)

def test_ledger_is_private_and_repeat_attestation_does_not_churn_revision(store):
    import os
    assert os.stat(store.db_path).st_mode & 0o077 == 0
    first=attested(store)
    second=store.update_attestation(account_id='deriv6207',customer_id='ownerA',
        expected_revision=first.revision,entitlement_ok=True,connected=True,
        writer_verified=True,kill_switch=False,now=NOW)
    assert second.revision==first.revision
