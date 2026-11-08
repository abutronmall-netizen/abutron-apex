"""Isolated account-bound publisher tests (mock native snapshots only)."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import pytest

from abutron_replacement.account_bound_publisher import (
    DecisionJournal, publish_native_m5,
)
from abutron_replacement.production_contracts import FeedRefused, BrokerBoundBars

NOW=datetime(2026, 11, 8, 3, 30, tzinfo=timezone.utc)
C='1'*32
O='2'*32
M='Volatility 75 Index.0'


def native_bars():
    end=int(NOW.timestamp()) // 300*300
    return tuple(dict(symbol=M,ts=end-300*(n-1),open=35000.0+n,
            high=35015.0+n,low=34995.0+n,close=35010.0+n,
            volume=0.0,is_closed=True,provenance='authenticated_mt5',
            native_open_ts=end-300*(n-1)-300) for n in range(100,0,-1))


def make_fixture(tmp_path):
    feed=BrokerBoundBars(connection_id=C,broker='deriv',environment='DEMO',
        server='Deriv-Demo',symbol=M,source_sha256='e'*64,
        source_kind='deriv_native_mt5_v2',bars=native_bars(),
        checked_at=NOW.timestamp(),broker_authenticated_by_this_code=False)
    instrument=dict(symbol=M,broker='deriv',asset_class='deriv_synthetic',
                    tick_size=0.01,spread_bps=5.0,commission_bps=0.0,
                    annual_vol=0.75,max_weight=0.2)
    journal=DecisionJournal(tmp_path/'shadow.sqlite')
    return dict(feed=feed,instrument=instrument,customer_id=O,account_id=C,
                journal=journal,now=NOW,supervisor_attested=True)


def test_untrusted_native_file_cannot_publish(tmp_path):
    x=make_fixture(tmp_path)
    x.pop('supervisor_attested')
    with pytest.raises(FeedRefused,match='ATTESTATION'):
        publish_native_m5(**x)


def test_publish_is_shadow_only_and_can_be_read_back(tmp_path):
    x=make_fixture(tmp_path)
    result=publish_native_m5(**x)
    assert result.status=='PUBLISHED_SHADOW_ONLY'
    assert result.proposal['broker_order_authorized'] is False
    assert result.orders_submitted==0
    assert result.proposal['order'] is None
    assert result.proposal['connection_id']==C
    assert x['journal'].read(result.publication_id)==result.proposal


def test_duplicates_after_restart_do_not_republish(tmp_path):
    x=make_fixture(tmp_path)
    first=publish_native_m5(**x)
    x['journal']=DecisionJournal(tmp_path/'shadow.sqlite')
    second=publish_native_m5(**x)
    assert second.status=='ALREADY_PUBLISHED_SHADOW_ONLY'
    assert second.proposal is None
    assert second.publication_id==first.publication_id


def test_same_closed_bar_changed_price_is_refused(tmp_path):
    x=make_fixture(tmp_path)
    publish_native_m5(**x)
    bars=list(x['feed'].bars)
    last=dict(bars[-1])
    last['high']+=5
    bars[-1]=last
    x['feed']=replace(x['feed'],bars=tuple(bars))
    with pytest.raises(FeedRefused,match='CHANGED'):
        publish_native_m5(**x)


def test_unrelated_native_file_rollover_is_duplicate_not_tampering(tmp_path):
    x=make_fixture(tmp_path)
    r1=publish_native_m5(**x)
    # Worker file checksum changes due to unrelated symbols or older bars.
    x['feed']=replace(x['feed'],source_sha256='a'*64)
    r2=publish_native_m5(**x)
    assert r2.status=='ALREADY_PUBLISHED_SHADOW_ONLY'
    assert x['journal'].read(r1.publication_id)['source_sha256']=='e'*64


def test_same_closed_bar_changed_manifest_is_refused(tmp_path):
    x=make_fixture(tmp_path)
    publish_native_m5(**x)
    x['instrument']=dict(x['instrument'],commission_bps=1.0)
    with pytest.raises(FeedRefused,match='CHANGED'):
        publish_native_m5(**x)


def test_same_bar_separates_customer_accounts(tmp_path):
    x=make_fixture(tmp_path)
    r1=publish_native_m5(**x)
    other='3'*32
    x['account_id']=other
    x['feed']=replace(x['feed'],connection_id=other)
    r2=publish_native_m5(**x)
    assert r2.status=='PUBLISHED_SHADOW_ONLY'
    assert r2.publication_id!=r1.publication_id


def test_stale_feed_and_bar_both_fail_closed(tmp_path):
    x=make_fixture(tmp_path)
    x['feed']=replace(x['feed'],checked_at=NOW.timestamp()-25)
    with pytest.raises(FeedRefused,match='VERIFICATION_STALE'):
        publish_native_m5(**x)
    x=make_fixture(tmp_path)
    oldbars=tuple(dict(b,ts=b['ts']-900) for b in x['feed'].bars)
    x['feed']=replace(x['feed'],bars=oldbars)
    with pytest.raises(FeedRefused,match='NOT_FRESH'):
        publish_native_m5(**x)


def test_live_and_cross_account_refused(tmp_path):
    x=make_fixture(tmp_path)
    x['feed']=replace(x['feed'],environment='LIVE')
    with pytest.raises(FeedRefused,match='MISMATCH'):
        publish_native_m5(**x)
    x=make_fixture(tmp_path)
    x['account_id']='f'*32
    with pytest.raises(FeedRefused,match='MISMATCH'):
        publish_native_m5(**x)


def test_malformed_stream_and_wrong_manifest_refused(tmp_path):
    x=make_fixture(tmp_path)
    b=list(x['feed'].bars)
    b[1]['ts']=b[0]['ts']
    x['feed']=replace(x['feed'],bars=tuple(b))
    with pytest.raises(FeedRefused,match='MONOTONIC'):
        publish_native_m5(**x)
    x=make_fixture(tmp_path)
    x['instrument']=dict(x['instrument'],broker='fp_markets',asset_class='fx_index')
    with pytest.raises(FeedRefused,match='MISMATCH'):
        publish_native_m5(**x)


def test_journal_permissions(tmp_path):
    path=tmp_path/'shadow.sqlite'
    j=DecisionJournal(path)
    assert os.stat(path).st_mode & 0o077==0
    os.chmod(path,0o644)
    with pytest.raises(PermissionError,match='PERMISSIONS'):
        DecisionJournal(path)