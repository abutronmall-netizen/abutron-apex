"""Explicit regression tests for the user's eight requested removals."""
from dataclasses import replace
import math
import sqlite3
from abutron_replacement.bridge import AbutronApex11SignalBridge
from abutron_replacement.candidate_contract import review_candidate
from abutron_replacement.cost_validation import CostEvidence, replay_signals
from abutron_replacement.long_history import can_combine_archive_and_live, read_archive_contiguous_tail
from abutron_replacement.fp_clock import diagnose_fp_clock
from test_hardening_4_blockers import (gate, native, signal, bars_for_cost, costs,
                                        history_fixture, CID, M)


def manifest():
    return {'symbol':'Volatility 75 Index.0','broker':'deriv',
            'asset_class':'deriv_synthetic','tick_size':0.01,'spread_bps':2.0,
            'commission_bps':1.0,'annual_vol':0.75,'max_weight':0.2}


def candle(i, ts=None):
    close=36000+2*i+10*math.sin(i/7)
    return {'symbol':M,'ts':(1794000300+300*i if ts is None else ts),
            'open':close-1,'high':close+2,'low':close-3,'close':close,
            'volume':0.0,'is_closed':True,'provenance':'authenticated_mt5'}


def test_no_forced_300_bar_warmup_while_running_real_apex_engine():
    bridge=AbutronApex11SignalBridge([manifest()])
    out=[bridge.on_closed_candle(candle(i)) for i in range(100)]
    assert bridge.warmup_bars==0
    assert len(out)==100
    assert all(p['status']!='WARMUP' for p in out)
    assert any(p['status'] in {'BUY','SELL'} for p in out)


def test_configurable_warmup_below_300_is_not_rejected():
    bridge=AbutronApex11SignalBridge([manifest()],warmup_bars=2)
    assert bridge.on_closed_candle(candle(0))['status']=='WARMUP'
    assert bridge.on_closed_candle(candle(1))['status']=='WARMUP'
    assert bridge.on_closed_candle(candle(2))['status']!='WARMUP'


def test_older_than_100_seconds_signal_still_eligible_without_handover_flag():
    s=signal()
    review=review_candidate(signal=s,gate=gate(),native=native(),
                            now=int(s['bar_closed_ts'])+7200)
    assert review['engineering_gates_passed']
    assert not review['blockers']
    assert review['order_candidate'] is not None
    assert 'execution_authorized' not in review
    assert not hasattr(gate(),'handover_approved')


def test_gap_resumes_on_next_real_candle_with_clean_indicator_window():
    b=AbutronApex11SignalBridge([manifest()])
    for i in range(80): b.on_closed_candle(candle(i))
    out=b.on_closed_candle(candle(84))
    assert out['status'] in ('BUY','SELL','HOLD')
    assert b.engine.history.n(M)==1
    assert b._n[M]==1


def test_disconnected_real_history_kept_as_separate_segments_not_vetoed():
    a=tuple(dict(ts=i*300,open=100,high=101,low=99,close=100) for i in range(100,200))
    b=tuple(dict(ts=i*300,open=100,high=101,low=99,close=100) for i in range(500,600))
    result=can_combine_archive_and_live(archived=a,live=b,
        archived_connection_id=CID,live_connection_id=CID)
    assert result['bars']==200 and result['missing_interval_count']==1
    assert result['contiguous_tail_bars']==100


def test_archive_tail_includes_actual_gap_without_inventing_bars(tmp_path):
    db,proof=history_fixture(tmp_path,n=25,gap_at=12)
    rows=read_archive_contiguous_tail(database=db,proof_file=proof,
        symbol=M,connection_id=CID,rows_needed=25)
    assert len(rows)==25
    intervals=[b['ts']-a['ts'] for a,b in zip(rows,rows[1:])]
    assert intervals.count(600)==1
    assert intervals.count(300)==23


def test_one_trade_one_day_no_200_observation_or_14_day_gate():
    bars=bars_for_cost(20)
    decisions=[{'symbol':M,'bar_closed_ts':bars[0]['ts'],'status':'BUY'}]
    result=replay_signals(bars=bars,signals=decisions,costs=costs(),horizon_bars=3)
    assert result['trades_nonoverlapping']==1
    assert result['days_observed']==1
    assert 'promotion_authorized' not in result
    assert 'day_block_multiple_test_lower_95_bps' not in result
    assert 'review_ready_hypothetical_only' not in result
    assert result['mean_stressed_net_bps'] is not None


def test_negative_mean_reported_without_an_approval_gate():
    bars=[{'ts':1794000300+i*300,'open':100-i*.1,'high':101-i*.1,
           'low':99-i*.1,'close':100-i*.1} for i in range(20)]
    result=replay_signals(bars=bars,
        signals=[{'symbol':M,'bar_closed_ts':bars[0]['ts'],'status':'BUY'}],
        costs=costs(),horizon_bars=3)
    assert result['trades_nonoverlapping']==1
    assert result['mean_stressed_net_bps']<0
    assert 'blockers' not in result and 'reasons' not in result


def test_fp_clock_diagnostic_does_not_issue_permanent_execution_denial():
    emitted=1794096016
    quotes=[emitted+7200-17+i for i in range(11)]
    result=diagnose_fp_clock(emitted_epoch=emitted,broker_quote_epochs=quotes,
                             observed_utc=emitted)
    assert result.status=='FRESH_COHORT_CLOCK_OFFSET_VERIFIED'
    assert result.candidate_offset_seconds==7200
    assert 'execution_authorized' not in result.__dict__
    assert 'permitted_for_feed' not in result.__dict__
