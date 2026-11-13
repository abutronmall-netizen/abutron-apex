#!/usr/bin/env python3
"""Negative safety tests for staged ABUTRON 6207 exact-draft builder."""
import importlib.util
from importlib.machinery import SourceFileLoader
import unittest
from copy import deepcopy
from decimal import Decimal

SPEC=importlib.util.spec_from_loader('exact',SourceFileLoader('exact','/usr/local/sbin/abutron-apex11-6207-exact-draft-ro'))
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
SYM='Volatility 25 Index.0'
NOW=1794261305
OWNER='4fd8991981000ffa4fa0b1c233c5195c'
TS=1794261300
SIGNAL={'engine':'APEX_1_1_0','broker':'deriv','symbol':SYM,'timeframe':'M5',
        'bar_closed_ts':TS,'status':'BUY','order':None,'connection_id':m.CID,
        'customer_id':OWNER,'decision_id':'a'*64}
NATIVE={'bid':2900.0,'ask':2900.0,'tick_size':.001,'point':.001,
       'tick_age_ms':120,'min_lots':.5,'max_lots':330,'volume_step':.01,
       'stops_level_points':400,'freeze_level_points':0,
       'broker_tick_value_loss':.001,'pnl_probe_displacement_ticks':10,
       'buy_probe_native_ordercalcprofit_usd':-.01,
       'sell_probe_native_ordercalcprofit_usd':-.01}
BARS=[{'symbol':SYM,'ts':TS-300*(19-i),'high':2901.5+i*.02,
       'low':2899.5+i*.02,'close':2900.+i*.02,'is_closed':True}
      for i in range(20)]

def valid():return m.construct(SIGNAL,NATIVE,BARS,9577.61,OWNER,NOW)
class Tests(unittest.TestCase):
    def deny(self,s=None,n=None,b=None,equity=9577.61,now=NOW,reason=None):
        with self.assertRaises(m.ProposalDenied) as e:
            m.construct(s or SIGNAL,n or NATIVE,b or BARS,equity,OWNER,now)
        if reason:self.assertIn(reason,str(e.exception))
    def test_complete_native_order_draft_no_order_auth(self):
        a=valid()
        self.assertEqual(a['order']['type'],'ORDER_TYPE_BUY')
        for f in ('volume','price','sl','tp','magic','symbol','deviation'):self.assertIn(f,a['order'])
        self.assertTrue(Decimal(a['order']['sl'])<Decimal(a['order']['price'])<Decimal(a['order']['tp']))
        self.assertLessEqual(Decimal(a['conservative_estimated_loss_usd']),
                             Decimal(a['risk_budget_usd']))
        for f in ('broker_exact_ordercheck_verified','crm_execution_ack_verified',
                  'broker_order_ack_verified','dispatch_authorized'):
            self.assertFalse(a[f])
        self.assertEqual(a['orders_submitted'],0)
        self.assertTrue(a['manual_trades_count_as_exposure_not_apex_signals'])
    def test_sell_geometry(self):
        s=dict(SIGNAL,status='SELL')
        a=m.construct(s,NATIVE,BARS,9577.61,OWNER,NOW)
        self.assertTrue(Decimal(a['order']['tp'])<Decimal(a['order']['price'])<Decimal(a['order']['sl']))
    def test_hold_rejected(self):self.deny(s=dict(SIGNAL,status='HOLD'),reason='NOT_APPROVED_DIRECTIONAL')
    def test_manual_order_cannot_be_publisher(self):
        self.deny(s=dict(SIGNAL,engine='MANUAL_MT5'),reason='NOT_ORIGINAL_APEX')
    def test_existing_order_not_accepted_as_signal(self):
        self.deny(s=dict(SIGNAL,order={'manual':True}),reason='NOT_ORIGINAL_APEX')
    def test_wrong_broker(self):self.deny(s=dict(SIGNAL,broker='fp_markets'),reason='NOT_ORIGINAL_APEX')
    def test_wrong_account(self):self.deny(s=dict(SIGNAL,connection_id='a'*32),reason='NOT_ORIGINAL_APEX')
    def test_stale_decision(self):self.deny(now=NOW+360,reason='EXPIRED')
    def test_stale_quote(self):self.deny(n=dict(NATIVE,tick_age_ms=6000),reason='STALE')
    def test_minlot_risk_denied(self):self.deny(equity=20,reason='MIN_LOT')
    def test_inverted_spread(self):self.deny(n=dict(NATIVE,bid=3001,ask=2999),reason='STALE')
    def test_invalid_lot_step(self):self.deny(n=dict(NATIVE,volume_step=.03),reason='INVALID_VOLUME')
    def test_stale_candle_identity(self):
        b=deepcopy(BARS);b[-1]['ts']-=300
        self.deny(b=b,reason='UNMATCHED_NATIVE')
    def test_existing_mtf_vote_controls_position_size(self):
        baseline=valid()
        split=deepcopy(SIGNAL)
        split['directional_context']={'direction_score':0.25,'m5_original_side':'BUY'}
        result=m.construct(split,NATIVE,BARS,9577.61,OWNER,NOW)
        self.assertEqual(result['directional_risk_fraction'],'0.50')
        self.assertEqual(result['original_policy_risk_ceiling_pct'],'0.15')
        self.assertLess(Decimal(result['risk_budget_usd']),Decimal(baseline['risk_budget_usd']))
        self.assertLess(Decimal(result['order']['volume']),Decimal(baseline['order']['volume']))
        self.assertLessEqual(Decimal(result['conservative_estimated_loss_usd']),Decimal(result['risk_budget_usd']))

    def test_unanimous_mtf_vote_maintains_original_risk_policy(self):
        full=deepcopy(SIGNAL)
        full['directional_context']={'direction_score':1.0,'m5_original_side':'BUY'}
        self.assertEqual(m.construct(full,NATIVE,BARS,9577.61,OWNER,NOW)['order']['volume'],valid()['order']['volume'])

    def test_invalid_direction_vote_denied(self):
        for vote in (-0.5,0.0,1.2,float('nan')):
            s=deepcopy(SIGNAL)
            s['directional_context']={'direction_score':vote}
            self.deny(s=s,reason='APEX_DIRECTION')

if __name__=='__main__':unittest.main(verbosity=2)
