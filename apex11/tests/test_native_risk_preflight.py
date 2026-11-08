"""Offline cross-component preflight tests. No broker/MT5 transport."""
from dataclasses import replace
from datetime import datetime, timezone

from abutron_replacement.candidate_contract import review_candidate
from abutron_replacement.native_risk_preflight import reserve_apex11_demo_candidate
from risk_guard.abutron_risk_guard import Account, CustomerRisk, Proposal, D
from risk_guard.reservation_store import ReservationStore
from test_hardening_4_blockers import gate, native, signal, OWNER, CID, M


def inputs(tmp_path, *, lag_seconds=5):
    s, g, n = signal(), gate(), native()
    now = datetime.fromtimestamp(s['bar_closed_ts'] + lag_seconds, tz=timezone.utc)
    a = Account(account_id=CID, customer_id=OWNER, environment='DEMO',
                equity_ccy=D('10000'), usd_per_ccy=D('1'),
                day_start_equity_ccy=D('10000'), peak_equity_ccy=D('10000'),
                open_stop_risk_ccy=D('10'), broker_asof=now)
    customer = CustomerRisk(customer_id=OWNER, accounts=(a,),
                            day_start_equity_usd=D('10000'),peak_equity_usd=D('10000'))
    key = review_candidate(signal=s, gate=g, native=n, now=int(now.timestamp()))['signal_id_for_separate_ledger']
    p = Proposal(customer_id=OWNER,account_id=CID,symbol=M,environment='DEMO',
                 order_side='BUY',one_lot_stop_risk_ccy=D('20'),
                 one_lot_roundtrip_cost_ccy=D('0'), one_lot_slippage_buffer_ccy=D('3'),
                 volume_min=D('0.01'),volume_max=D('100'),volume_step=D('0.01'),
                 native_stop_validated=True,contract_spec_verified=True,signal_fresh=True,
                 signal_id=key)
    store = ReservationStore(tmp_path/'ledger.sqlite3')
    return dict(signal=s,gate=g,native=n,customer=customer,proposal=p,store=store,now=now)


def test_valid_verified_demo_candidate_reserves_without_order(tmp_path):
    kw=inputs(tmp_path)
    result=reserve_apex11_demo_candidate(**kw)
    assert result.risk_reserved
    assert not result.broker_order_authorized
    assert result.reason=='DEMO_RISK_RESERVED_NOT_SUBMITTED'
    assert result.reserved_volume==D('0.43')


def test_repeat_signal_never_reserves_twice(tmp_path):
    kw=inputs(tmp_path)
    assert reserve_apex11_demo_candidate(**kw).risk_reserved
    assert 'SIGNAL_ALREADY_RESERVED_OR_PROCESSED' in reserve_apex11_demo_candidate(**kw).reason


def test_2pct_aggregate_cap_stricter_than_old_20pct_candidate(tmp_path):
    kw=inputs(tmp_path)
    a=replace(kw['customer'].accounts[0],open_stop_risk_ccy=D('200'))
    kw['customer']=replace(kw['customer'],accounts=(a,))
    kw['gate']=replace(kw['gate'], current_verified_stop_risk_usd=200.)
    prior=review_candidate(signal=kw['signal'],gate=kw['gate'],native=kw['native'],now=int(kw['now'].timestamp()))
    assert prior['engineering_gates_passed']  # legacy accepts 20% open-risk
    result=reserve_apex11_demo_candidate(**kw)
    assert not result.risk_reserved
    assert 'OPEN_RISK_CAP_REACHED' in result.reason


def test_daily_three_percent_lock_and_no_rebound_reset(tmp_path):
    kw=inputs(tmp_path)
    a=replace(kw['customer'].accounts[0],equity_ccy=D('9700'))
    kw['customer']=replace(kw['customer'],accounts=(a,))
    kw['gate']=replace(kw['gate'],account_equity_usd=9700.)
    result=reserve_apex11_demo_candidate(**kw)
    assert not result.risk_reserved and 'DAILY_LOSS' in result.reason
    a=replace(a,equity_ccy=D('10000'))
    kw['customer']=replace(kw['customer'],accounts=(a,))
    kw['gate']=replace(kw['gate'],account_equity_usd=10000.)
    assert 'PERSISTENT_DAILY_LOSS_LOCK' in reserve_apex11_demo_candidate(**kw).reason


def test_twenty_percent_peak_drawdown_latches(tmp_path):
    kw=inputs(tmp_path)
    a=replace(kw['customer'].accounts[0],peak_equity_ccy=D('12500'))
    kw['customer']=replace(kw['customer'],accounts=(a,),peak_equity_usd=D('12500'))
    assert 'DRAWDOWN' in reserve_apex11_demo_candidate(**kw).reason


def test_foreign_customer_is_rejected(tmp_path):
    kw=inputs(tmp_path)
    kw['proposal']=replace(kw['proposal'],customer_id='some-other-owner')
    assert reserve_apex11_demo_candidate(**kw).reason=='CUSTOMER_OWNER_MISMATCH'


def test_client_off_is_not_implicitly_reenabled(tmp_path):
    kw=inputs(tmp_path)
    kw['gate']=replace(kw['gate'],customer_switch_effective=False)
    r=reserve_apex11_demo_candidate(**kw)
    assert not r.risk_reserved and 'CLIENT_AUTOMATIC_SWITCH_OFF' in r.reason


def test_missing_broker_equity_reconciliation_blocks(tmp_path):
    kw=inputs(tmp_path)
    kw['gate']=replace(kw['gate'],account_equity_usd=9999.)
    assert reserve_apex11_demo_candidate(**kw).reason=='EQUITY_SNAPSHOT_RECONCILIATION_MISMATCH'


def test_incorrect_broker_risk_quote_blocks(tmp_path):
    kw=inputs(tmp_path)
    kw['proposal']=replace(kw['proposal'],one_lot_stop_risk_ccy=D('1'))
    assert reserve_apex11_demo_candidate(**kw).reason=='RISK_QUOTE_BELOW_NATIVE_STRESS_ESTIMATE'


def test_old_closed_signal_has_no_arbitrary_100_second_expiry(tmp_path):
    kw=inputs(tmp_path,lag_seconds=7200)
    assert reserve_apex11_demo_candidate(**kw).risk_reserved


def test_unsupported_live_placement_refused(tmp_path):
    kw=inputs(tmp_path)
    kw['proposal']=replace(kw['proposal'],environment='LIVE')
    assert reserve_apex11_demo_candidate(**kw).reason=='NATIVE_ACCOUNT_IDENTITY_MISMATCH'