"""Read-only contract tests against the observed Deriv / FP native formats."""
import json
import os
from pathlib import Path
from hashlib import sha256
import pytest
from abutron_replacement.production_contracts import (
    read_deriv_native_m5, read_fp_published_m5, FeedRefused,
    inert_native_compatibility_proposal,
)
from abutron_replacement import AbutronApex11SignalBridge

C='1'*32; O='2'*32; N='3'*32
M='Volatility 75 Index.0'


def build_deriv(tmp_path, *, count=101, nonce=N, health_nonce=N, status='CONNECTED', server='Deriv-Demo'):
    health=tmp_path/'worker-health.json'
    health.write_text(json.dumps(dict(id=C,broker='Deriv',mode='DEMO',server=server,
        status=status,heartbeat_fresh=True,nonce=health_nonce)))
    account=tmp_path/f'ABUTRON_NATIVE_ACCOUNT_V2_{nonce}.txt'
    account.write_text('\n'.join(['ABUTRON_NATIVE_ACCOUNT_V2',nonce,'6207','1000','999','USD','0']))
    bars=tmp_path/f'ABUTRON_NATIVE_BARS_V2_{nonce}.txt'
    rows=['ABUTRON_NATIVE_BARS_V2',nonce]
    for i in range(count):
        x=1794000000+300*i
        p=36000+3*i
        rows.append(f'{M}\tM5\t{x}\t{p}\t{p+20}\t{p-5}\t{p+15}')
    bars.write_text('\n'.join(rows))
    fixture_now=1794000000+300*count+1
    for item in (health,account,bars):
        os.utime(item,(fixture_now,fixture_now))
    return dict(connection_id=C, health_path=health,bars_path=bars,account_path=account,
                login='6207',now=1794000000+300*count+1)


def test_deriv_native_enforces_nonce_account_and_closed_timestamp(tmp_path):
    a=build_deriv(tmp_path)
    out=read_deriv_native_m5(**a)
    assert len(out[M].bars)==101
    assert out[M].bars[0]['ts']==1794000300
    assert out[M].broker_authenticated_by_this_code is False
    assert out[M].source_kind=='deriv_native_mt5_v2'
    assert all(b['is_closed'] and b['provenance']=='authenticated_mt5' for b in out[M].bars)


def test_deriv_rejects_nonce_mismatch(tmp_path):
    a=build_deriv(tmp_path,health_nonce='4'*32)
    with pytest.raises(FeedRefused,match='NONCE'):
        read_deriv_native_m5(**a)


def test_deriv_rejects_live_or_not_connected(tmp_path):
    a=build_deriv(tmp_path,status='CONNECTING')
    with pytest.raises(FeedRefused,match='WORKER_NOT_ATTESTED'):
        read_deriv_native_m5(**a)
    a=build_deriv(tmp_path,server='Deriv-Server')
    with pytest.raises(FeedRefused,match='BINDING_INVALID'):
        read_deriv_native_m5(**a,server='Deriv-Server')


def test_deriv_rejects_unclosed_bar(tmp_path):
    a=build_deriv(tmp_path)
    with pytest.raises(FeedRefused,match='CANDLE_NOT_CLOSED'):
        read_deriv_native_m5(**dict(a,now=1794000000+300*100+100,historical=True))


def test_deriv_symlink_denied(tmp_path):
    a=build_deriv(tmp_path)
    symlink=tmp_path/'symlink'
    symlink.symlink_to(a['health_path'])
    with pytest.raises(FeedRefused,match='UNSAFE_NATIVE_FILE'):
        read_deriv_native_m5(**dict(a,health_path=symlink))


def test_deriv_current_100_m5_bars_do_not_trigger_arbitrary_300_bar_gate(tmp_path):
    a=build_deriv(tmp_path,count=100)
    broker=read_deriv_native_m5(**a)[M]
    metadata={'symbol':M,'broker':'deriv','asset_class':'deriv_synthetic',
              'tick_size':0.01,'spread_bps':5.0,'commission_bps':0.0,
              'annual_vol':0.75,'max_weight':0.2}
    bridge=AbutronApex11SignalBridge([metadata])
    statuses=[bridge.on_closed_candle(bar)['status'] for bar in broker.bars]
    assert 'WARMUP' not in statuses
    assert any(x in {'BUY','SELL'} for x in statuses)


def test_fp_verified_schema_accepted_but_partial_rejected(tmp_path):
    path=tmp_path/'fp.json'
    base={'schema':'abutron.fpmarkets.native.candles.v1','connection_id':C,
          'source':'FP Markets DEMO MT5','account_mode':'DEMO',
          'broker_server':'FPMarketsSC-Demo', 'execution_enabled':False,
          'orders_submitted':0,
          'bars':{'EURUSD':{'M5':[dict(time=1794000000,open=1.12,high=1.121,low=1.119,close=1.1205)]}}}
    path.write_text(json.dumps(base))
    os.utime(path,(1794000301,1794000301))
    r=read_fp_published_m5(path=path,connection_id=C,now=1794000301)
    assert len(r['EURUSD'].bars)==1
    base['schema']='abutron.fpmarkets.native.partial.readonly.v1'
    path.write_text(json.dumps(base))
    with pytest.raises(FeedRefused,match='NOT_COMPLETE'):
        read_fp_published_m5(path=path,connection_id=C,now=1794000301)


def test_fp_rejects_cross_account_and_live(tmp_path):
    p=tmp_path/'fp.json'
    d={'schema':'abutron.fpmarkets.native.candles.v1','connection_id':C,
       'source':'FP Markets DEMO MT5','account_mode':'LIVE',
       'broker_server':'FPMarketsSC-Demo','execution_enabled':False,
       'orders_submitted':0,'bars':{'EURUSD':{'M5':[]}}}
    p.write_text(json.dumps(d))
    with pytest.raises(FeedRefused,match='ACCOUNT_OR_AUTHORITY'):
        read_fp_published_m5(path=p,connection_id=C,now=1794000301)
    d['account_mode']='DEMO';p.write_text(json.dumps(d))
    with pytest.raises(FeedRefused,match='ACCOUNT_OR_AUTHORITY'):
        read_fp_published_m5(path=p,connection_id=O,now=1794000301)


def test_ledger_identity_exact_and_inert(tmp_path):
    ts=1794000300
    sig={'broker':'deriv','symbol':M,'status':'BUY','bar_closed_ts':ts,
         'decision_id':'abc'}
    r=inert_native_compatibility_proposal(owner=O,connection_id=C,signal=sig)
    assert r['m5_bar_time']==ts-300
    assert r['signal_key']==sha256((O+'|'+C+'|'+M+'|M5|'+str(ts-300)+'|BUY').encode()).hexdigest()
    assert 'execution_authorized' not in r and r['order_request'] is None
    assert r['compatible_with_current_router'] is False


def test_inert_compatibility_rejects_fp(tmp_path):
    with pytest.raises(FeedRefused,match='NO_APPROVED_ORDER_ROUTE'):
        inert_native_compatibility_proposal(owner=O,connection_id=C,
            signal={'broker':'fp_markets','symbol':'EURUSD','status':'BUY','bar_closed_ts':1794000300})


def test_shadow_runner_refuses_cross_broker_sources(tmp_path):
    from dataclasses import replace
    from abutron_replacement.offline_shadow_runner import evaluate_bars
    a=build_deriv(tmp_path)
    native=read_deriv_native_m5(**a)[M]
    mixed={'Volatility 75 Index.0':native,
           'EURUSD':replace(native,symbol='EURUSD',broker='fp_markets')}
    manifest=[{'symbol':k,'broker':v.broker,'asset_class':'deriv_synthetic' if v.broker=='deriv' else 'fx_index',
               'tick_size':0.01,'spread_bps':5.0,'commission_bps':0.0,
               'annual_vol':0.75,'max_weight':0.2} for k,v in mixed.items()]
    with pytest.raises(FeedRefused,match='CROSS_ACCOUNT_OR_CROSS_BROKER'):
        evaluate_bars(mixed,manifest)


def test_shadow_runner_never_calls_order_authority(tmp_path):
    from abutron_replacement.offline_shadow_runner import evaluate_bars
    a=build_deriv(tmp_path,count=101)
    feed=read_deriv_native_m5(**a)
    manifest=[{'symbol':M,'broker':'deriv','asset_class':'deriv_synthetic',
               'tick_size':0.01,'spread_bps':5.0,'commission_bps':0.0,
               'annual_vol':0.75,'max_weight':0.2}]
    result=evaluate_bars(feed,manifest)
    assert result['orders_submitted']==0
    assert 'execution_authorized' not in result
    assert result['results'][M]['total_closed_m5_bars']==101
    assert result['results'][M]['state_counts'].get('WARMUP',0)==0


def test_observed_nov7_deriv_v75_native_values_parse_without_prices_changes(tmp_path):
    """Only a three-bar schema sample from the read-only native worker inspection.

    Values came from the protected Deriv DEMO MT5 export inspected on 8 Nov 2026;
    the wrapper account/nonce fields below are synthetic test fixtures.
    This test is NOT an independent broker authentication or profitable backtest.
    """
    a=build_deriv(tmp_path,count=3)
    observed=[
      ['1794094500','37352.86000000','37352.86000000','37239.64000000','37284.99000000'],
      ['1794094800','37270.24000000','37433.04000000','37254.78000000','37432.52000000'],
      ['1794095100','37429.18000000','37502.07000000','37367.06000000','37486.27000000'],
    ]
    a['bars_path'].write_text('\n'.join(['ABUTRON_NATIVE_BARS_V2',N]+[
      '\t'.join([M,'M5']+row) for row in observed]))
    r=read_deriv_native_m5(**dict(a,now=1794095402,historical=True))
    assert len(r[M].bars)==3
    assert [b['ts'] for b in r[M].bars]==[1794094800,1794095100,1794095400]
    assert r[M].bars[2]['close']==37486.27
    assert r[M].bars[1]['high']==37433.04


def test_deriv_native_m15_h1_are_closed_from_same_export(tmp_path):
    a=build_deriv(tmp_path)
    now=int(a['now'])
    with a['bars_path'].open('a') as f:
        for tf, seconds in (('M15',900),('H1',3600)):
            last_close=now//seconds*seconds
            for i in range(3):
                opening=last_close-(3-i)*seconds
                price=37000-10*i
                f.write(f'\n{M}\t{tf}\t{opening}\t{price}\t{price+15}\t{price-20}\t{price-5}')
            # Current incomplete candle is not evidence.
            f.write(f'\n{M}\t{tf}\t{last_close}\t40000\t40050\t39950\t40020')
    os.utime(a['bars_path'],(a['now'],a['now']))
    feed=read_deriv_native_m5(**a)[M]
    assert len(feed.bars)==101
    assert len(feed.higher_timeframes['M15'])==3
    assert len(feed.higher_timeframes['H1'])==3
    assert all(b['ts']<=a['now'] and b['is_closed'] for tf in ('M15','H1')
               for b in feed.higher_timeframes[tf])
