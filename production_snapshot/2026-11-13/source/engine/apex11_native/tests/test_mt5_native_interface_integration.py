"""APEX11 to ABUTRON MT5 interface contracts, without touching any MT5 files."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import time
import pytest

from abutron_replacement.fp_partial_native import read_fp_partial_or_complete_m5
from abutron_replacement.mt5_native_protocol import (
    NativeTarget, NativeRequestRefused, render_native_demo_intent,
)
from abutron_replacement.production_contracts import FeedRefused
from abutron_replacement.native_integration_probe import _manifest, select_demo_rows, run

CID='a'*32
OWNER='b'*32
NONCE='c'*32
NOW=1794099600  # M5-aligned source timestamp


def fp_fixture(*,schema='abutron.fpmarkets.native.partial.readonly.v1', now=NOW):
    bars=[]
    for i in range(6):
        t=now-2100+i*300
        bars.append({'time':t,'open':1.1,'high':1.11,'low':1.09,'close':1.101})
    d={'schema':schema,'checked_at_utc':'2026-11-08T00:00:00+00:00',
       'source':'FP Markets DEMO MT5 native' if 'partial' in schema else 'FP Markets DEMO MT5',
       'status':'PARTIAL_NOT_CERTIFIED',
       'connection_id':CID,'account_mode':'DEMO','broker_server':'FPMarketsSC-Demo',
       'mapping':{'EURUSD':{'actual':'EURUSD.r','status':'MAPPED','trade_mode':4}},
       'quotes':{'EURUSD':{'symbol':'EURUSD.r','time':now-20,'bid':1.1,'ask':1.101}},
       'bars':{'EURUSD':{'M5':bars}},'execution_enabled':False,'orders_submitted':0}
    from datetime import datetime,timezone
    d['checked_at_utc']=datetime.fromtimestamp(now-20,timezone.utc).isoformat()
    return d


def fp_file(tmp_path,doc,*,when=NOW):
    p=tmp_path/'partial.json';p.write_text(json.dumps(doc))
    import os
    os.utime(p,(when-20,when-20))
    return p


def native_target(broker='deriv'):
    return NativeTarget(broker,'DEMO',CID,OWNER,'6207' if broker=='deriv' else '0512',
        'Deriv-Demo' if broker=='deriv' else 'FPMarketsSC-Demo',
        NONCE,'Volatility 75 Index.0' if broker=='deriv' else 'EURUSD',
        'Volatility 75 Index.0' if broker=='deriv' else 'EURUSD.r')


def native_signal(target,side='BUY'):
    return {'engine':'APEX_1_1_0','broker':target.broker,
            'symbol':target.canonical_symbol,'timeframe':'M5',
            'bar_closed_ts':NOW,'status':side,
            'decision_id':'d'*64,'order':None}


def review(target, signal):
    if target.broker=='deriv':
        key=hashlib.sha256(
            f'{target.owner}|{target.connection_id}|{target.canonical_symbol}|M5|{NOW-300}|{signal["status"]}'.encode()
        ).hexdigest()
    else:key='e'*64
    return {'schema':'abutron.apex11.broker.candidate.review.v1',
      'broker':target.broker,'environment':'DEMO',
      'engineering_gates_passed':True,'blockers':[],
      'orders_submitted':0,'source_decision_id':signal['decision_id'],
      'signal_id_for_separate_ledger':key,
      'order_candidate':{'connection_id':CID,'symbol':target.canonical_symbol,
        'side':signal['status'],'signal_id':key}}


def test_fp_partial_allows_published_subset_without_13_symbol_research_gate(tmp_path):
    d=fp_fixture()
    p=fp_file(tmp_path,d)
    out=read_fp_partial_or_complete_m5(path=p,connection_id=CID,now=NOW)
    assert sorted(out)==['EURUSD']
    assert out['EURUSD'].source_kind=='fp_collector_partial_v1'
    assert len(out['EURUSD'].bars)==6
    assert out['EURUSD'].broker_authenticated_by_this_code is False


def test_fp_full_schema_also_supported(tmp_path):
    d=fp_fixture(schema='abutron.fpmarkets.native.candles.v1')
    p=fp_file(tmp_path,d)
    out=read_fp_partial_or_complete_m5(path=p,connection_id=CID,now=NOW)
    assert out['EURUSD'].source_kind=='fp_collector_complete_v1'

@pytest.mark.parametrize('field,value',[
    ('account_mode','LIVE'),('broker_server','FPMarketsSC-Live'),
    ('connection_id','0'*32),('execution_enabled',True),('orders_submitted',1),
    ('source','FP Markets LIVE MT5 native'),
])
def test_fp_rejects_untrusted_binding_and_authority(tmp_path,field,value):
    d=fp_fixture();d[field]=value
    with pytest.raises(FeedRefused):
        read_fp_partial_or_complete_m5(path=fp_file(tmp_path,d),connection_id=CID,now=NOW)


def test_fp_rejects_stale_broker_quote(tmp_path):
    d=fp_fixture();d['quotes']['EURUSD']['time']=NOW-5000
    with pytest.raises(FeedRefused,match='STALE'):
        read_fp_partial_or_complete_m5(path=fp_file(tmp_path,d),connection_id=CID,now=NOW)


def test_fp_rejects_candle_duplicate_and_bad_geometry(tmp_path):
    d=fp_fixture()
    d['bars']['EURUSD']['M5'][-1]['time']=d['bars']['EURUSD']['M5'][-2]['time']
    with pytest.raises(FeedRefused,match='DUPLICATED'):
        read_fp_partial_or_complete_m5(path=fp_file(tmp_path,d),connection_id=CID,now=NOW)
    d=fp_fixture();d['bars']['EURUSD']['M5'][-1]['high']=1.0
    with pytest.raises(FeedRefused,match='GEOMETRY'):
        read_fp_partial_or_complete_m5(path=fp_file(tmp_path,d),connection_id=CID,now=NOW)


def test_fp_rejects_mismatched_native_symbol_mapping(tmp_path):
    d=fp_fixture();d['mapping']['EURUSD']['actual']='EURUSD.fake'
    with pytest.raises(FeedRefused,match='MAPPING'):
        read_fp_partial_or_complete_m5(path=fp_file(tmp_path,d),connection_id=CID,now=NOW)


def test_deriv_packet_matches_existing_native_bridge_protocol_without_sending():
    target=native_target();signal=native_signal(target);r=review(target,signal)
    intent=render_native_demo_intent(target=target,signal=signal,review=r,now=NOW+10)
    assert intent['broker']=='deriv'
    assert intent['native_order_request_published'] is False
    assert intent['orders_submitted']==0
    fields=intent['packet_bytes'].decode().splitlines()
    assert len(fields)==12
    assert fields[0]=='APEX_NATIVE_ADAPTIVE_ORDER_V3'
    assert fields[-1]=='SEND_DEMO_ONLY'
    assert fields[7:10]==['AUTO','0.10','STRUCTURE_M5']
    assert fields[2]==r['signal_id_for_separate_ledger']


def test_fp_packet_uses_existing_fp_ledger_key_not_apex_decision_id():
    target=native_target('fp_markets');signal=native_signal(target);r=review(target,signal)
    intent=render_native_demo_intent(target=target,signal=signal,review=r,now=NOW+10,
                                      fp_legacy_m5_bar_time=NOW)
    fields=intent['packet_bytes'].decode().splitlines()
    assert fields[0]=='APEX_FP_NATIVE_ADAPTIVE_ORDER_V2'
    assert fields[5]=='EURUSD.r'
    assert fields[2]==hashlib.sha256(f'{CID}|EURUSD|{NOW}'.encode()).hexdigest()
    assert fields[2]!=r['signal_id_for_separate_ledger']
    assert intent['native_order_request_published'] is False


def test_native_intent_rejects_live_account():
    t=replace(native_target('fp_markets'),environment='LIVE')
    s=native_signal(t)
    with pytest.raises(NativeRequestRefused,match='DEMO_ONLY'):
        render_native_demo_intent(target=t,signal=s,review=review(t,s),now=NOW+10)


def test_native_intent_rejects_not_reviewed_account():
    t=native_target();s=native_signal(t);r=review(t,s)
    r['engineering_gates_passed']=False
    with pytest.raises(NativeRequestRefused,match='RISK_REVIEW'):
        render_native_demo_intent(target=t,signal=s,review=r,now=NOW+10)


def test_native_intent_rejects_forged_deriv_ledger_key():
    t=native_target();s=native_signal(t);r=review(t,s)
    r['signal_id_for_separate_ledger']='f'*64
    with pytest.raises(NativeRequestRefused,match='LEDGER_IDENTITY'):
        render_native_demo_intent(target=t,signal=s,review=r,now=NOW+10)


def test_native_intent_rejects_hold_and_future_bar():
    t=native_target();s=native_signal(t,side='HOLD')
    with pytest.raises(NativeRequestRefused,match='DIRECTIONAL'):
        render_native_demo_intent(target=t,signal=s,review=review(t,s),now=NOW+10)
    s=native_signal(t)
    with pytest.raises(NativeRequestRefused,match='FUTURE'):
        render_native_demo_intent(target=t,signal=s,review=review(t,s),now=NOW-10)


def test_manifest_rejects_hypothetical_example(tmp_path):
    p=tmp_path/'manifest.json';p.write_text(json.dumps({'WARNING':'test values only','universe':[{'symbol':'EURUSD'}]}))
    with pytest.raises(FeedRefused,match='HYPOTHETICAL'):
        _manifest(p)


def test_probe_only_reads_demo_accounts(tmp_path):
    import sqlite3
    p=tmp_path/'accounts.sqlite3'
    c=sqlite3.connect(p)
    c.executescript('''CREATE TABLE apex_mt5_connections (
       id TEXT,account_id TEXT,broker TEXT,environment TEXT,broker_server TEXT,status TEXT,worker_binding TEXT,account_reference TEXT);
       CREATE TABLE apex_trade_controls (connection_id TEXT,desired_enabled INTEGER,effective_enabled INTEGER);
    ''')
    c.execute('INSERT INTO apex_mt5_connections VALUES(?,?,?,?,?,?,?,?)',
              (CID,OWNER,'FP Markets','LIVE','FPMarketsSC-Live','CONNECTED','abutron-client-mt5-'+CID,'0512'))
    c.commit();c.close()
    assert select_demo_rows(p)==[]
    d=run(db=p)
    assert d['orders_submitted']==0 and d['native_order_writes']==0
    assert d['accounts']==[]


def test_fp_packet_requires_verified_old_ledger_bar_timestamp():
    t=native_target('fp_markets');s=native_signal(t);r=review(t,s)
    with pytest.raises(NativeRequestRefused,match='CONVENTION_UNVERIFIED'):
        render_native_demo_intent(target=t,signal=s,review=r,now=NOW+10)
    with pytest.raises(NativeRequestRefused,match='CONVENTION_UNVERIFIED'):
        render_native_demo_intent(target=t,signal=s,review=r,now=NOW+10,
                                  fp_legacy_m5_bar_time=NOW-600)

def test_fp_open_bar_native_ledger_timestamp_variant():
    t=native_target('fp_markets');s=native_signal(t);r=review(t,s)
    doc=render_native_demo_intent(target=t,signal=s,review=r,now=NOW+10,
                                  fp_legacy_m5_bar_time=NOW-300)
    assert doc['native_receipt_key']==hashlib.sha256(f'{CID}|EURUSD|{NOW-300}'.encode()).hexdigest()


def test_native_probe_runs_real_apex_engine_with_single_instrument(tmp_path):
    from abutron_replacement.native_integration_probe import evaluate_native
    from abutron_replacement.production_contracts import BrokerBoundBars
    src=BrokerBoundBars(connection_id=CID,broker='deriv',environment='DEMO',
         server='Deriv-Demo',symbol='Volatility 75 Index.0',
         source_sha256='0'*64,source_kind='deriv_native_mt5_v2',
         bars=tuple({'symbol':'Volatility 75 Index.0',
             'ts':NOW-600+i*300,'open':101.,'high':102.,'low':100.,
             'close':101.,'volume':0.,'is_closed':True,
             'provenance':'authenticated_mt5'} for i in range(2)),
         checked_at=NOW)
    measured={'symbol':'Volatility 75 Index.0','broker':'deriv',
       'asset_class':'deriv_synthetic','tick_size':0.01,'spread_bps':2.,
       'commission_bps':0.,'annual_vol':0.2,'max_weight':0.2,'timeframe_seconds':300}
    # Synthetic test data are confined to this unit test; not a production manifest.
    result=evaluate_native({'Volatility 75 Index.0':src},[measured])
    assert result['Volatility 75 Index.0']['status'] in ('BUY','SELL','HOLD')
    assert result['Volatility 75 Index.0']['closed_bars']==2
