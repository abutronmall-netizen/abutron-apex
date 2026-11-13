import importlib.util,pathlib,unittest,math
P=pathlib.Path(__file__).parent/'abutron_entry_model_v1.py'
spec=importlib.util.spec_from_file_location('entrycandidate',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def b(i,o=100.,hi=100.3,lo=99.7,close=100.):
 return (i*300,o,hi,lo,close)
class ModelSafety(unittest.TestCase):
 def test_stop_is_loss_when_both_hit(self):
  r=[b(i) for i in range(16)]
  r[1]=b(1,100,105,95,100)
  x=m.price_outcome(r,0,'BUY',1,.2)
  self.assertEqual(x['reason'],'STOP')
  self.assertLess(x['gross_bps'],0)
 def test_adverse_gap_uses_worse_open(self):
  r=[b(i) for i in range(16)]
  r[2]=b(2,94,95,92,94)
  x=m.price_outcome(r,0,'BUY',1,.2)
  self.assertEqual(x['reason'],'STOP_GAP')
  self.assertLess(x['exit'],98.8)
 def test_missing_candle_rejected(self):
  r=[b(i) for i in range(16)]
  x=list(r[4]);x[0]+=3600;r[4]=tuple(x)
  self.assertIsNone(m.price_outcome(r,0,'BUY',1,.2))
 def test_min_stop_can_invalidate_setups(self):
  r=[b(i) for i in range(16)]
  self.assertIsNone(m.price_outcome(r,0,'BUY',1,107.7))
 def test_insufficient_forward_bars_rejected(self):
  self.assertIsNone(m.price_outcome([b(i) for i in range(8)],0,'BUY',1,0))
 def test_invalid_direction_refused(self):
  self.assertIsNone(m.price_outcome([b(i) for i in range(16)],0,'HOLD',1,.2))
 def test_contract_cost_depresses_expectancy(self):
  x=[{'gross_bps':20.,'entry':100.,'reason':'TP'}]
  z=m.score(x,0.10,1.0)
  self.assertAlmostEqual(z['cost_scenarios']['10']['mean_net_bps'],0.)
  self.assertLess(z['cost_scenarios']['20']['mean_net_bps'],0.)
 def test_no_false_edge_with_single_trade(self):
  x=[{'gross_bps':100.,'entry':100.,'reason':'TP'}]
  z=m.score(x,.01,1.0)
  self.assertEqual(z['trades'],1)
  self.assertIsNone(z['cost_scenarios']['10']['normal_95_lower_bps'])
 def test_flat_completed_bars_cannot_generate_signals(self):
  rows=[b(i) for i in range(200)]
  feats=m.features(rows)
  self.assertEqual(m.decide(199,rows,feats,0),{})
 def test_h1_regime_is_causal(self):
  rows=[(i*3600,100,101,99,100+i*.001) for i in range(160)]
  ends,trend=m.h1_regime(rows)
  self.assertTrue(all(t==i*3600+3600 for i,t in enumerate(ends)))
  self.assertEqual(trend[0],0)
if __name__=='__main__':unittest.main()
