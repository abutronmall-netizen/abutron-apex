"""Isolated tests for repaired research contracts. No access to ABUTRON or MT5."""
from dataclasses import replace
from pathlib import Path
from hashlib import sha256
import json, os, sqlite3
import pytest
from abutron_replacement.production_contracts import FeedRefused
from abutron_replacement.long_history import (
    load_deriv_archive_segments, archive_warmup_readiness, can_combine_archive_and_live)
from abutron_replacement.fp_clock import diagnose_fp_clock, read_native_quote_epoch_fields
from abutron_replacement.candidate_contract import (
    AccountGate, BrokerNativeRisk, review_candidate, make_canonical_id)
from abutron_replacement.cost_validation import CostEvidence,replay_signals

M='Volatility 75 Index.0'
CID='1'*32
OWNER='2'*32


def history_fixture(tmp_path,*,n=400,gap_at=None):
    db=tmp_path/'broker_long_candles.sqlite3'
    conn=sqlite3.connect(db)
    conn.execute('CREATE TABLE candles (symbol TEXT NOT NULL,timeframe TEXT NOT NULL,start_time_utc INTEGER NOT NULL,open REAL NOT NULL,high REAL NOT NULL,low REAL NOT NULL,close REAL NOT NULL,PRIMARY KEY(symbol,timeframe,start_time_utc))')
    for i in range(n):
        t=1793700000+300*(i+(1 if gap_at is not None and i>=gap_at else 0))
        v=35000+i
        conn.execute('INSERT INTO candles VALUES (?,?,?,?,?,?,?)',(M,'M5',t,v,v+2,v-2,v+1))
    conn.commit();conn.close()
    proof=tmp_path/'LONG_HISTORY_IMPORT_EVIDENCE.json'
    proof.write_text(json.dumps({'source':'DERIV_DEMO_MT5_READONLY_COPYRATES',
        'status':'VERIFIED_RESEARCH_ONLY','session_nonce_matched':True,
        'orders_submitted':0,'account_switches_modified':False,
        'positions_modified':False,'overlap_mismatches':0,
        'source_sha256':'a'*64,'source_account_suffix':'6207'}))
    return db,proof


def test_research_archive_has_contiguous_300_and_never_claims_live(tmp_path):
    d,p=history_fixture(tmp_path,n=710,gap_at=350)
    segments=load_deriv_archive_segments(database=d,proof_file=p,symbol=M,connection_id=CID)
    assert len(segments)==2 and [x.bars for x in segments]==[350,360]
    r=archive_warmup_readiness(segments)
    assert r['history_available_for_historical_replay'] is True
    assert r['live_warmup_proven'] is False
    assert r['longest_contiguous_m5']==360


def test_archive_source_cannot_be_rebranded_as_broker_verified(tmp_path):
    d,p=history_fixture(tmp_path)
    j=json.loads(p.read_text());j['overlap_mismatches']=1;p.write_text(json.dumps(j))
    with pytest.raises(FeedRefused,match='PROVENANCE'):
        load_deriv_archive_segments(database=d,proof_file=p,symbol=M,connection_id=CID)


def test_history_gap_without_300_after_it_not_promotable(tmp_path):
    d,p=history_fixture(tmp_path,n=400,gap_at=350)
    seg=load_deriv_archive_segments(database=d,proof_file=p,symbol=M,connection_id=CID)
    assert len(seg)==2 and seg[-1].bars==50


def test_archive_live_join_requires_overlap_and_current_account():
    a=tuple(dict(ts=i*300,open=100,high=101,low=99,close=100) for i in range(100,440))
    b=tuple(dict(ts=i*300,open=100,high=101,low=99,close=100) for i in range(400,470))
    r=can_combine_archive_and_live(archived=a,live=b,archived_connection_id=CID,live_connection_id=CID)
    assert r['overlap_verified']==40 and r['bars']==370
    assert r['contiguous_tail_bars']==370
    with pytest.raises(FeedRefused,match='ACCOUNT_MISMATCH'):
        can_combine_archive_and_live(archived=a,live=b,archived_connection_id=CID,live_connection_id=OWNER)


def test_archive_live_join_must_not_hide_gap_or_mutated_candles():
    a=tuple(dict(ts=i*300,open=100,high=101,low=99,close=100) for i in range(100,440))
    b=tuple(dict(ts=i*300,open=100,high=101,low=99,close=100) for i in range(400,470))
    changed=list(b);changed[2]={**changed[2],'close':100.01}
    with pytest.raises(FeedRefused,match='CANDLE_MISMATCH'):
        can_combine_archive_and_live(archived=a,live=tuple(changed),archived_connection_id=CID,live_connection_id=CID)
    disconnected=tuple(dict(ts=i*300,open=100,high=101,low=99,close=100) for i in range(800,880))
    joined=can_combine_archive_and_live(archived=a,live=disconnected,archived_connection_id=CID,live_connection_id=CID)
    assert joined['overlap_verified']==0
    assert joined['missing_interval_count']==1
    assert joined['contiguous_tail_bars']==80


def test_fp_weekend_native_quotes_stale_24h_not_timezone():
    emitted=1794096016
    times=[emitted-86418 for i in range(10)]+[emitted-90017]
    d=diagnose_fp_clock(emitted_epoch=emitted,broker_quote_epochs=times,observed_utc=emitted+32)
    assert d.status=='STALE_NATIVE_QUOTES_NOT_A_TIMEZONE_ERROR'
    assert d.candidate_offset_seconds is None and d.status.startswith('STALE')


def test_fp_fresh_broker_utc_offset_is_diagnostic_only():
    emitted=1794096016
    times=[emitted+7200-17+i for i in range(11)]
    d=diagnose_fp_clock(emitted_epoch=emitted,broker_quote_epochs=times,observed_utc=emitted)
    assert d.candidate_offset_seconds==7200
    assert d.fresh_quote_count==11
    assert 'execution_authorized' not in d.__dict__


def test_fp_future_quotes_and_invalid_cohort_fail_closed():
    emitted=1794096016
    d=diagnose_fp_clock(emitted_epoch=emitted,broker_quote_epochs=[emitted+3600+5000]*11,observed_utc=emitted)
    assert d.status!='FRESH_COHORT_CLOCK_OFFSET_VERIFIED'
    with pytest.raises(FeedRefused,match='INSUFFICIENT'):
        diagnose_fp_clock(emitted_epoch=emitted,broker_quote_epochs=[emitted]*3,observed_utc=emitted)


def gate():
    return AccountGate(broker='deriv',environment='DEMO',server='Deriv-Demo',
        owner=OWNER,connection_id=CID,account_bound=True,worker_nonce_bound=True,
        fresh_broker_session=True,native_ea_account_match=True,
        broker_trade_allowed=True,terminal_trade_allowed=True,
        customer_switch_desired=True,customer_switch_effective=True,
        crm_entitlement_approved=True,single_writer_exclusive=True,
        existing_pending_orders=0,broker_positions_protected=True,
        broker_exposure_reconciled=True,account_equity_usd=10000.0,
        current_verified_stop_risk_usd=10.0)


def native():
    return BrokerNativeRisk(tick_size=.01,tick_value_per_lot_usd=1.,
        min_lot=.01,max_lot=100.,lot_step=.01,min_stop_ticks=10,
        broker_verified=True,price=36000.,stop_price=35999.8,take_price=36000.4,
        slippage_budget_ticks=3,broker_calc_profit_verified=True,
        broker_order_check_verified=True)


def signal(ts=1794095400):
    return dict(engine='APEX_1_1_0',symbol=M,broker='deriv',timeframe='M5',
        bar_closed_ts=ts,status='BUY',decision_id='d'*64,
        order=None)


def test_new_candidate_contract_inert_even_all_gates_passing():
    s=signal();g=gate();r=review_candidate(signal=s,gate=g,native=native(),now=s['bar_closed_ts']+5)
    assert r['engineering_gates_passed'] and r['blockers']==[]
    assert 'execution_authorized' not in r and r['order_candidate'] is not None
    assert r['order_candidate']['volume_lots']>0
    assert r['signal_id_for_separate_ledger']==sha256((OWNER+'|'+CID+'|'+M+'|M5|'+str(s['bar_closed_ts']-300)+'|BUY').encode()).hexdigest()
    assert r['nominal_stop_risk_usd']<=10.0


@pytest.mark.parametrize('change,reason',[
    ({'customer_switch_effective':False},'CLIENT_AUTOMATIC_SWITCH_OFF'),
    ({'single_writer_exclusive':False},'EXCLUSIVE_ORDER_WRITER_UNVERIFIED'),
    ({'crm_entitlement_approved':False},'CRM_ENTITLEMENT_DENIED'),
    ({'broker_exposure_reconciled':False},'BROKER_OPEN_POSITIONS_NOT_RECONCILED'),
    ({'existing_pending_orders':1},'NATIVE_PENDING_ORDER_EXPOSURE'),
    ({'order_history_uncertain':True},'UNKNOWN_NATIVE_ORDER_OUTCOME_NO_RETRY'),
    ({'kill_switch_halted':True},'KILL_SWITCH_ACTIVE'),
])
def test_candidate_gate_missing_control_denied(change,reason):
    s=signal();r=review_candidate(signal=s,gate=replace(gate(),**change),native=native(),now=s['bar_closed_ts']+5)
    assert reason in r['blockers'] and not r['engineering_gates_passed']


def test_candidate_min_lot_risk_fails_closed():
    s=signal()
    n=replace(native(),tick_value_per_lot_usd=200.0, min_lot=.1)
    r=review_candidate(signal=s,gate=gate(),native=n,now=s['bar_closed_ts']+5)
    assert 'MINIMUM_LOT_EXCEEDS_010_PERCENT_RISK' in r['blockers']


def test_fp_ledger_namespace_separate_and_not_deriv_ledger():
    g=replace(gate(),broker='fp_markets',server='FPMarketsSC-Demo')
    s={**signal(),'broker':'fp_markets','symbol':'EURUSD'}
    k=make_canonical_id(gate=g,signal=s)
    assert k!=make_canonical_id(gate=gate(),signal=signal())
    r=review_candidate(signal=s,gate=g,native=replace(native(),tick_size=0.0001,price=1.1,stop_price=1.09,take_price=1.12),now=s['bar_closed_ts']+5)
    assert r['broker']=='fp_markets' and r['order_candidate'] is not None


def test_missing_native_ordercheck_never_approved():
    s=signal();r=review_candidate(signal=s,gate=gate(),native=replace(native(),broker_order_check_verified=False),now=s['bar_closed_ts']+5)
    assert 'BROKER_ORDER_CALC_PROFIT_AND_CHECK_MISSING' in r['blockers']


def test_portfolio_20pct_ceiling_blocks_candidate():
    s=signal();g=replace(gate(),current_verified_stop_risk_usd=1995)
    r=review_candidate(signal=s,gate=g,native=native(),now=s['bar_closed_ts']+5)
    assert 'PORTFOLIO_20_PERCENT_CEILING_EXCEEDED' in r['blockers']


def bars_for_cost(n=450):
    return [dict(ts=1793700300+300*i,open=100+i*.01,high=101+i*.01,low=99+i*.01,close=100+i*.01) for i in range(n)]


def costs(**kw):
    return CostEvidence(symbol=M,spread_p95_bps=.002810,
        historical_roundtrip_commission_bps=3.1236,
        hypothetical_slippage_each_side_bps=5,
        source_reference_sha256='c'*64,**kw)


def test_cost_sensitivity_is_not_certified_with_noncontemporaneous_data():
    bars=bars_for_cost()
    signals=[dict(symbol=M,bar_closed_ts=b['ts'],status='BUY') for b in bars[40:-2]]
    x=replay_signals(bars=bars,signals=signals,costs=costs(),horizon_bars=3)
    assert x['trades_nonoverlapping']>0
    assert x['real_broker_profitability_certified'] is False
    assert 'promotion_authorized' not in x
    assert x['mean_stressed_net_bps'] is not None
    assert x['actual_slippage_verified'] is False


def test_cost_evaluator_skips_gap_crossing_trade_without_global_veto():
    bars=bars_for_cost()
    for bar in bars[312:]:bar['ts']+=300
    out=replay_signals(bars=bars,signals=[dict(symbol=M,bar_closed_ts=bars[310]['ts'],status='BUY')],costs=costs())
    assert out['skipped_trades_crossing_missing_candles']==1


def test_cost_evaluator_does_not_require_extra_authorization_field():
    bars=bars_for_cost();t=bars[30]['ts']
    out=replay_signals(bars=bars,signals=[dict(symbol=M,bar_closed_ts=t,status='BUY')],costs=costs())
    assert out['trades_nonoverlapping']==1


def test_long_history_archive_reader_only_returns_last_contiguous(tmp_path):
    from abutron_replacement.long_history import read_archive_contiguous_tail
    db,proof=history_fixture(tmp_path,n=810,gap_at=400)
    rows=read_archive_contiguous_tail(database=db,proof_file=proof,symbol=M,
                                      connection_id=CID,rows_needed=380)
    assert len(rows)==380 and all(y['ts']-x['ts']==300 for x,y in zip(rows,rows[1:]))
    assert all(b['provenance']=='authenticated_mt5' and b['is_closed'] is True for b in rows)


def test_cost_model_repeated_buy_state_not_multiple_new_trades():
    bars=bars_for_cost()
    signals=[dict(symbol=M,bar_closed_ts=b['ts'],status='BUY') for b in bars[30:]]
    r=replay_signals(bars=bars,signals=signals,costs=costs(),horizon_bars=3)
    assert r['trades_nonoverlapping']==1


def test_true_apex_archive_backtest_runner_remains_no_order(tmp_path):
    from abutron_replacement.offline_archive_cost_replay import run
    db,proof=history_fixture(tmp_path,n=430)
    c={
      'schema':'abutron.deriv.microstructure_cost_deal_evidence.v1',
      'no_full_historical_spread_distribution':True,
      'actual_order_slippage_distribution_verified':False,
      'cost_reference_source_sha256':'e'*64,
      'spreads':{M: {'quote_records_passed':True,
                     'historical_slippage_verified':False,
                     'spread_bps_p95':0.00281,
                     'historical_broker_deal_roundtrip_commission_bps_at_prior_quote':3.1236}}}
    manifest={'symbol':M,'broker':'deriv','asset_class':'deriv_synthetic','tick_size':0.01,
              'annual_vol':0.75,'max_weight':0.2}
    result=run(database=db,proof_file=proof,manifest=manifest,cost_reference=c,
               connection_id=CID,symbol=M,rows=401)
    assert result['bars_used']==401
    assert 'execution_authorized' not in result and result['orders_submitted']==0
    assert 'promotion_authorized' not in result['cost_sensitive_nonoverlapping_research']
