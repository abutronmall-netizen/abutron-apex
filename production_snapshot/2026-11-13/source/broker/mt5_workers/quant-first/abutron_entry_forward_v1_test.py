import importlib.util,sqlite3,datetime,pathlib,unittest
P=pathlib.Path(__file__).parent/'abutron_entry_forward_v1.py'
S=importlib.util.spec_from_file_location('entryforward',P)
m=importlib.util.module_from_spec(S);S.loader.exec_module(m)
def bar(t,o=100.,hi=100.3,lo=99.7,cl=100.):
 return {'time':t,'open':o,'high':hi,'low':lo,'close':cl}
def observed(c,codehash='a'*64,costhash='b'*64,side='BUY',bar0=None):
 b=bar0 or bar(0)
 c.execute("""INSERT INTO observed(symbol,model,bar_time,side,atr,bar_digest,model_sha256,cost_sha256,
       stop_floor,commission_per_lot,usd_per_price_point_lot,spread_bps_snapshot,first_observed_utc,status)
       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",('Volatility 10 Index.0','trend_pullback',0,side,1,m.feed.digest(b),
       codehash,costhash,.1,.1,1,0,'2026-11-06T22:00:00+00:00','PENDING'))
class TestForward(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');m.install_schema(self.c)
  self.now=datetime.datetime.now(datetime.timezone.utc)
  self.source={'Volatility 10 Index.0':{'M5':[bar(i*300) for i in range(14)]}}
 def tearDown(self):self.c.close()
 def test_schema_pkey(self):
  observed(self.c)
  with self.assertRaises(sqlite3.IntegrityError):observed(self.c)
 def test_no_future_remains_pending(self):
  observed(self.c)
  self.source['Volatility 10 Index.0']['M5']=self.source['Volatility 10 Index.0']['M5'][:12]
  self.assertEqual(m.settle(self.c,self.now,self.source,'a'*64,'b'*64),(0,0))
 def test_future_broker_market_outcome_is_not_broker_fill(self):
  observed(self.c)
  self.source['Volatility 10 Index.0']['M5'][1]=bar(300,100,103,97,100)
  self.assertEqual(m.settle(self.c,self.now,self.source,'a'*64,'b'*64),(1,0))
  status,why,gross,net=self.c.execute('select status,exit_reason,gross_bps,net_10bps from observed').fetchone()
  self.assertEqual((status,why),('MARKET_OUTCOME_MEASURED','STOP'))
  self.assertLess(net,gross)
 def test_source_candle_revision_refused(self):
  observed(self.c)
  self.source['Volatility 10 Index.0']['M5'][0]['close']=102.
  self.assertEqual(m.settle(self.c,self.now,self.source,'a'*64,'b'*64),(0,1))
  self.assertEqual(self.c.execute('select status from observed').fetchone()[0],'EVIDENCE_REVISED')
 def test_model_change_invalidates_future(self):
  observed(self.c)
  self.assertEqual(m.settle(self.c,self.now,self.source,'different','b'*64),(0,1))
 def test_cost_change_invalidates_future(self):
  observed(self.c)
  self.assertEqual(m.settle(self.c,self.now,self.source,'a'*64,'different'),(0,1))
 def test_gap_refuses_outcome(self):
  observed(self.c)
  self.source['Volatility 10 Index.0']['M5'][8]['time']+=30
  self.assertEqual(m.settle(self.c,self.now,self.source,'a'*64,'b'*64),(0,1))
 def test_report_promotion_is_never_allowed(self):
  observed(self.c)
  r=m.build_report(self.c,self.now,1,1,0,0,'a'*64,'b'*64)
  self.assertFalse(r['promotion_permitted'])
  self.assertFalse(r['order_execution_authorized'])
  self.assertEqual(r['orders_submitted'],0)
if __name__=='__main__':unittest.main()
