import importlib.util,json,sqlite3,datetime,pathlib,tempfile,unittest,os
STAGE=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('forwardshadow',STAGE/'abutron_forward_cost_shadow_v1.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def candle(t,o=100,hi=100.4,lo=99.6,cl=100):
 return {'time':t,'open':o,'high':hi,'low':lo,'close':cl}
def insert(c,side='BUY',atr=1,record=None):
 b=record or candle(0)
 c.execute("INSERT INTO observations(symbol,model,bar_time,recorded_utc,side,atr,bar_digest,status) VALUES(?,?,?,?,?,?,?,?)",
  ('Volatility 10 Index.0','apex',0,'2026-11-06T21:00:00+00:00',side,atr,f.digest(b),'PENDING'))
class ForwardTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');f.init_db(self.c)
  self.now=datetime.datetime.now(datetime.timezone.utc)
  self.frames={'Volatility 10 Index.0':{'M5':[candle(i*300) for i in range(14)]}}
 def tearDown(self):self.c.close()
 def test_sha_detects_changed_price(self):
  a=candle(0);b=candle(0);b['close']=101
  self.assertNotEqual(f.digest(a),f.digest(b))
 def test_outcome_rejects_future_insufficient(self):
  insert(self.c);self.frames['Volatility 10 Index.0']['M5']=self.frames['Volatility 10 Index.0']['M5'][:12]
  good,bad=f.evaluate_pending(self.c,self.frames,self.now)
  self.assertEqual((good,bad),(0,0))
  self.assertEqual(self.c.execute('SELECT status FROM observations').fetchone()[0],'PENDING')
 def test_stop_loss_reported_when_target_hit_same_bar(self):
  insert(self.c)
  self.frames['Volatility 10 Index.0']['M5'][1]=candle(300,100,103,97,100)
  good,bad=f.evaluate_pending(self.c,self.frames,self.now)
  self.assertEqual((good,bad),(1,0))
  status,why,pnl=self.c.execute('SELECT status,exit_reason,gross_bps FROM observations').fetchone()
  self.assertEqual((status,why),('EVALUATED','STOP'))
  self.assertLess(pnl,0)
 def test_revised_source_candle_is_never_measured(self):
  insert(self.c)
  self.frames['Volatility 10 Index.0']['M5'][0]['close']=101
  good,bad=f.evaluate_pending(self.c,self.frames,self.now)
  self.assertEqual((good,bad),(0,1))
  self.assertEqual(self.c.execute('SELECT status FROM observations').fetchone()[0],'SOURCE_CANDLE_REVISED')
 def test_gap_cannot_be_scored_as_real_outcome(self):
  insert(self.c)
  self.frames['Volatility 10 Index.0']['M5'][4]['time']+=20
  good,bad=f.evaluate_pending(self.c,self.frames,self.now)
  self.assertEqual((good,bad),(0,1))
  self.assertEqual(self.c.execute('SELECT status FROM observations').fetchone()[0],'UNVERIFIABLE_GAP')
 def test_observation_key_prevents_duplicates(self):
  insert(self.c)
  self.c.execute('INSERT OR IGNORE INTO observations(symbol,model,bar_time,recorded_utc,side,atr,bar_digest,status) VALUES(?,?,?,?,?,?,?,?)',
  ('Volatility 10 Index.0','apex',0,'now','SELL',1,'bad','PENDING'))
  self.assertEqual(self.c.execute('SELECT count(*) FROM observations').fetchone()[0],1)
 def test_summary_does_not_claim_broker_fills(self):
  insert(self.c);f.evaluate_pending(self.c,self.frames,self.now)
  report=f.stats(self.c)
  item=report['Volatility 10 Index.0']['apex']
  self.assertEqual(item['forward_outcomes_measured'],1)
  self.assertFalse(item['historical_or_forward_broker_execution_confirmed'])
 def test_invalid_source_cannot_create_signal(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'source.json';p.write_text('{}')
   with self.assertRaises(ValueError):f.source_data(p,self.now)
if __name__=='__main__':unittest.main()
