"""Safety contract for ABUTRON APEX 1.1 offline bridge."""
import math
import pytest
from apex.config import load_config
from apex.core.models import Order, Quote, Side
from apex.brokers.paper import PaperBroker
from abutron_replacement import AbutronApex11SignalBridge, CandleRejected

M={"symbol":"R_75","broker":"deriv","asset_class":"deriv_synthetic",
   "tick_size":0.001,"spread_bps":3.0,"commission_bps":0.0,
   "annual_vol":0.75,"max_weight":0.2,"timeframe_seconds":300}

def bar(i, *, symbol="R_75"):
    p=1000+2*i+10*math.sin(i/8)
    return {"symbol":symbol,"ts":1600000000+i*300,"open":p-1,"high":p+4,
            "low":p-5,"close":p,"volume":1000,"is_closed":True,
            "provenance":"authenticated_mt5"}

def test_signal_only_no_real_or_paper_orders(monkeypatch):
    b=AbutronApex11SignalBridge([M])
    def bomb(*args,**kw):
        raise AssertionError('Order must never be submitted in signal_only mode')
    monkeypatch.setattr(b.engine.broker,'submit',bomb)
    for i in range(308):
        p=b.on_closed_candle(bar(i))
        assert p['order'] is None and 'execution_authorized' not in p
    assert p['engine']=='APEX_1_1_0'
    assert p['status'] in {'BUY','SELL','HOLD'}
    assert b.engine.execution_agent.orders==[]

def test_closed_bars_and_provenance_required():
    b=AbutronApex11SignalBridge([M])
    x=bar(0); x['is_closed']=False
    with pytest.raises(CandleRejected): b.on_closed_candle(x)
    x=bar(0); x['provenance']='synthetic'
    with pytest.raises(CandleRejected): b.on_closed_candle(x)
    b.on_closed_candle(bar(0))
    with pytest.raises(CandleRejected): b.on_closed_candle(bar(0))
    with pytest.raises(CandleRejected): b.on_closed_candle(bar(-1))
    x=bar(1);x['high']=1
    with pytest.raises(CandleRejected): b.on_closed_candle(x)

def test_realtime_staleness_guard():
    b=AbutronApex11SignalBridge([M])
    # Old, already-closed decisions are not rejected at 100 seconds.
    assert b.on_closed_candle(bar(0),observed_at=1600001000)['status']=='HOLD'
    with pytest.raises(CandleRejected): b.on_closed_candle(bar(1),observed_at=1599999990)

def test_reject_unknown_and_duplicate_symbols():
    with pytest.raises(ValueError): AbutronApex11SignalBridge([M,M])
    b=AbutronApex11SignalBridge([M])
    with pytest.raises(CandleRejected): b.on_closed_candle(bar(0,symbol='UNKNOWN'))

def test_no_legacy_research_enabled():
    b=AbutronApex11SignalBridge([M])
    assert b.engine.cfg['agents']['research']['enabled'] is False
    assert b.engine.cfg['agents']['carry']['enabled'] is False
    assert b.engine.cfg['llm']['enabled'] is False
    assert {x.name for x in b.engine.signal_agents} == {'trend','meanrev','breakout'}

def test_pending_orders_cancelled_on_emergency_flatten():
    cfg=load_config(overrides={'execution':{'latency_bars':1,'min_notional':1},
        'universe':[dict(M,asset_class='deriv_synthetic')]})
    broker=PaperBroker(cfg)
    broker.set_quote(Quote(symbol='R_75',ts=1,bid=99,ask=101,last=100,volume=10000))
    # establish position immediately; subsequent working order remains outstanding
    broker.latency_bars=0
    assert broker.submit(Order(symbol='R_75',side=Side.BUY,qty=20))
    broker.latency_bars=1
    broker.submit(Order(symbol='R_75',side=Side.BUY,qty=10))
    assert broker._working
    broker.flatten()
    assert broker.positions['R_75'].qty == 0
    assert not broker._working
    broker.begin_bar(ts=100)
    assert broker.positions['R_75'].qty == 0
    assert broker.submit(Order(symbol='R_75',side=Side.BUY,qty=10)) is None
    assert broker.positions['R_75'].qty == 0

def test_fp_markets_symbol_proposal_stays_nonexecuting():
    fp=dict(M, symbol='EURUSD.r', broker='fp_markets', asset_class='fx_index', annual_vol=0.08)
    b=AbutronApex11SignalBridge([fp])
    x=bar(0, symbol='EURUSD.r')
    p=b.on_closed_candle(x)
    assert p['broker']=='fp_markets' and p['status']=='HOLD'
    assert 'execution_authorized' not in p


def test_signal_mode_rejects_external_broker():
    from apex.engine import ApexEngine
    from apex.config import Cfg
    b=AbutronApex11SignalBridge([M])
    with pytest.raises(ValueError, match='external broker'):
        ApexEngine(Cfg(b.engine.cfg), mode='signal_only', broker=object())


def test_proposed_signal_has_no_quantity_or_protective_order():
    b=AbutronApex11SignalBridge([M])
    for i in range(310):
        p=b.on_closed_candle(bar(i))
    assert p['position_size'] is None and p['stop_loss'] is None
    assert p['take_profit'] is None and p['order'] is None
    assert p['status'] in ('BUY','SELL','HOLD')


def test_staged_direct_deriv_adapter_refuses_trade():
    from apex.brokers.adapters import DerivBroker
    from apex.core.models import Order, Side
    b=AbutronApex11SignalBridge([M])
    a=DerivBroker(b.engine.cfg, client=object())
    with pytest.raises(RuntimeError, match='disabled'):
        a.submit(Order(symbol='R_75',side=Side.BUY,qty=0.2))


def test_pause_cancels_pending_paper_orders():
    from apex.core.models import Order, Side, Quote
    b=AbutronApex11SignalBridge([M]); eng=b.engine
    eng.broker.set_quote(Quote(symbol='R_75',ts=1,bid=999,ask=1001,last=1000,volume=10000))
    eng.broker.submit(Order(symbol='R_75',side=Side.BUY,qty=1))
    assert eng.broker._working
    eng.pause(True)
    assert not eng.broker._working


def test_gap_in_m5_bars_resets_indicators_and_continues():
    b=AbutronApex11SignalBridge([M])
    b.on_closed_candle(bar(0))
    assert b.on_closed_candle(bar(2))['status']=='HOLD'
    assert b._n['R_75']==1
    assert b.engine.history.n('R_75')==1
