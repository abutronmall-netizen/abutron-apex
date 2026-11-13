import datetime as dt,importlib.util,pathlib,sqlite3,unittest
P=pathlib.Path(__file__).parent/'abutron_entry_forward_causal_v2.py'
spec=importlib.util.spec_from_file_location('causalfwd',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE=1800000000
SYMBOL='Volatility 25 Index.0'
MODEL='range_sweep'
def bar(t):return dict(time=t,open=100.,high=100.3,low=99.7,close=100.)
def cost(minlot=.5):
 return {'research_reference_equity_usd':9500,
   'instruments':{SYMBOL:{'bid':100,'minimum_broker_stop_price_distance':.4,
     'commission_usd_roundtrip_per_lot_median':.03,'ordercalcprofit_usd_per_price_point_per_lot':1,
     'minimum_volume':minlot}}}
def micro():
 return {'spreads':{SYMBOL:{'spread_bps_p95':.01}}}
def suggestions(start=BASE-300):
 return {SYMBOL:(bar(start),1.,{MODEL:'BUY'})}
class SafeCausalForwardTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:')
  m.init_db(self.c)
 def tearDown(self):self.c.close()
 def test_next_future_entry_is_after_capture(self):
  self.assertEqual(m.planned_entry_ts(BASE+34.5),BASE+300)
  self.assertEqual(m.planned_entry_ts(BASE+299.8),BASE+300)
  self.assertEqual(m.planned_entry_ts(BASE),BASE+300)
 def test_invalid_time_rejected(self):
  with self.assertRaises(ValueError):m.planned_entry_ts(float('nan'))
 def test_fresh_candidate_is_post_observation(self):
  now=dt.datetime.fromtimestamp(BASE+34,dt.timezone.utc)
  self.assertEqual(m.capture(self.c,now,suggestions(),cost(),micro(),'a'*64,'b'*64),(1,1,0))
  r=self.c.execute('select status,planned_entry_m5_start,first_observed_utc from observed').fetchone()
  self.assertEqual(r[0],'WAITING_FOR_GENUINELY_FUTURE_ENTRY')
  self.assertGreater(r[1],dt.datetime.fromisoformat(r[2]).timestamp())
 def test_legacy_late_candidate_is_excluded(self):
  now=dt.datetime.fromtimestamp(BASE+350,dt.timezone.utc)
  self.assertEqual(m.capture(self.c,now,suggestions(),cost(),micro(),'a'*64,'b'*64),(1,0,1))
  self.assertEqual(self.c.execute('select status from observed').fetchone()[0],'REJECTED_SOURCE_SIGNAL_TOO_OLD')
 def test_oversized_minimum_lot_fails_risk(self):
  now=dt.datetime.fromtimestamp(BASE+34,dt.timezone.utc)
  m.capture(self.c,now,suggestions(),cost(minlot=100),micro(),'a'*64,'b'*64)
  self.assertEqual(self.c.execute('select status from observed').fetchone()[0],'REJECTED_MIN_VOLUME_RISK_GT_POINT_ONE_PERCENT')
 def test_duplicate_signal_not_double_counted(self):
  now=dt.datetime.fromtimestamp(BASE+34,dt.timezone.utc)
  m.capture(self.c,now,suggestions(),cost(),micro(),'a'*64,'b'*64)
  m.capture(self.c,now,suggestions(),cost(),micro(),'a'*64,'b'*64)
  self.assertEqual(self.c.execute('select count(*) from observed').fetchone()[0],1)
 def test_no_future_entry_candle_does_not_settle(self):
  now=dt.datetime.fromtimestamp(BASE+34,dt.timezone.utc)
  m.capture(self.c,now,suggestions(),cost(),micro(),'a'*64,'b'*64)
  rows=[bar(BASE+i*300) for i in range(-10,1)]
  self.assertEqual(m.settle(self.c,now,{SYMBOL:{'M5':rows}},'a'*64,'b'*64),(0,0))
 def test_only_after_12_future_candles_can_measure(self):
  now=dt.datetime.fromtimestamp(BASE+34,dt.timezone.utc)
  m.capture(self.c,now,suggestions(),cost(),micro(),'a'*64,'b'*64)
  no=[bar(BASE+i*300) for i in range(-10,12)]
  self.assertEqual(m.settle(self.c,now,{SYMBOL:{'M5':no}},'a'*64,'b'*64),(0,0))
  full=no+[bar(BASE+12*300)]
  d=dt.datetime.fromtimestamp(BASE+13*300,dt.timezone.utc)
  self.assertEqual(m.settle(self.c,d,{SYMBOL:{'M5':full}},'a'*64,'b'*64),(1,0))
  status,net=self.c.execute('select status,net_10bps from observed').fetchone()
  self.assertEqual(status,'PROSPECTIVE_MARKET_OUTCOME_MEASURED')
  self.assertLess(net,0)
 def test_revised_model_invalidated(self):
  now=dt.datetime.fromtimestamp(BASE+34,dt.timezone.utc)
  m.capture(self.c,now,suggestions(),cost(),micro(),'a'*64,'b'*64)
  bars=[bar(BASE+i*300) for i in range(-10,15)]
  d=dt.datetime.fromtimestamp(BASE+15*300,dt.timezone.utc)
  self.assertEqual(m.settle(self.c,d,{SYMBOL:{'M5':bars}},'different','b'*64),(0,1))
  self.assertEqual(self.c.execute('select status from observed').fetchone()[0],'SOURCE_OR_COST_CHANGED_INVALID')
 def test_report_does_not_authorize_orders(self):
  now=dt.datetime.fromtimestamp(BASE+34,dt.timezone.utc)
  r=m.report(self.c,now,(0,0,0),0,0,'a'*64,'b'*64)
  self.assertEqual(r['new_orders_submitted'],0)
  self.assertFalse(r['can_promote_to_trading'])
  self.assertFalse(r['historical_model_not_identical_to_this_delayed_execution_variant'] is False)
if __name__=='__main__':unittest.main()
