"""FP native parser -> APEX account-bound shadow journal contract tests."""
from datetime import datetime, timezone
import pytest
from abutron_replacement.account_bound_publisher import DecisionJournal, publish_native_m5
from abutron_replacement.fp_partial_native import read_fp_partial_or_complete_m5
from abutron_replacement.production_contracts import FeedRefused
import abutron_replacement.account_bound_publisher as publisher
from test_mt5_native_interface_integration import fp_fixture, fp_file, CID, OWNER, NOW

class FakeSignalBridge:
    def __init__(self, instruments):
        assert len(instruments) == 1
    def on_closed_candle(self, bar, observed_at=None):
        return dict(status='HOLD', engine='APEX_1_1_0', broker='fp_markets',
                    symbol=bar['symbol'], timeframe='M5',
                    bar_closed_ts=int(bar['ts']), decision_id='a'*64,
                    order=None, ts=NOW)

@pytest.mark.parametrize('schema,kind', [
    ('abutron.fpmarkets.native.partial.readonly.v1','fp_collector_partial_v1'),
    ('abutron.fpmarkets.native.candles.v1','fp_collector_complete_v1')])
def test_native_fp_to_journal(tmp_path, monkeypatch, schema, kind):
    feed=read_fp_partial_or_complete_m5(path=fp_file(tmp_path,fp_fixture(schema=schema)),
                    connection_id=CID,now=NOW)['EURUSD']
    assert feed.source_kind==kind
    manifest=dict(symbol='EURUSD',broker='fp_markets',asset_class='fx_index',
                  tick_size=.00001,spread_bps=1,commission_bps=0,
                  annual_vol=.08,max_weight=.1,timeframe_seconds=300)
    monkeypatch.setattr(publisher,'AbutronApex11SignalBridge',FakeSignalBridge)
    journal=DecisionJournal(tmp_path/'journal.sqlite')
    kw=dict(feed=feed,instrument=manifest,customer_id=OWNER,
            account_id=CID,journal=journal,now=datetime.fromtimestamp(NOW,timezone.utc),
            supervisor_attested=True)
    result=publish_native_m5(**kw)
    assert result.status=='PUBLISHED_SHADOW_ONLY'
    assert result.orders_submitted==0 and not result.broker_order_authorized
    assert journal.read(result.publication_id)['source_kind']==kind
    assert publish_native_m5(**kw).status=='ALREADY_PUBLISHED_SHADOW_ONLY'

def test_fp_publication_rejects_missing_supervisor(tmp_path,monkeypatch):
    feed=read_fp_partial_or_complete_m5(path=fp_file(tmp_path,
                    fp_fixture(schema='abutron.fpmarkets.native.candles.v1')),
                    connection_id=CID,now=NOW)['EURUSD']
    manifest=dict(symbol='EURUSD',broker='fp_markets',asset_class='fx_index',
                  tick_size=.00001,spread_bps=1,commission_bps=0,
                  annual_vol=.08,max_weight=.1,timeframe_seconds=300)
    monkeypatch.setattr(publisher,'AbutronApex11SignalBridge',FakeSignalBridge)
    with pytest.raises(FeedRefused,match='INDEPENDENT_NATIVE_SUPERVISOR'):
        publish_native_m5(feed=feed,instrument=manifest,customer_id=OWNER,
            account_id=CID,journal=DecisionJournal(tmp_path/'journal.sqlite'),
            now=datetime.fromtimestamp(NOW,timezone.utc))
