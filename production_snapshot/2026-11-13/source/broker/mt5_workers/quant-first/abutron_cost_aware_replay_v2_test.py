import importlib.util, pathlib, unittest, math, tempfile
ROOT=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('risk_replay',ROOT/'abutron_cost_aware_replay_v2.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def bar(t, o=100., hi=100.5, lo=99.5, cl=100.):
    return dict(time=t,open=o,high=hi,low=lo,close=cl)

class EntryAndRiskTests(unittest.TestCase):
    def test_buy_same_bar_hits_both_stop_is_loss(self):
        seq=[bar(i*300) for i in range(14)]
        seq[1]=bar(300,100.,103.,97.,101.)
        x=r.stop_first(seq,0,'BUY',1)
        self.assertEqual(x['exit_reason'],'STOP')
        self.assertLess(x['gross_bps'],0)
    def test_sell_same_bar_hits_both_stop_is_loss(self):
        seq=[bar(i*300) for i in range(14)]
        seq[1]=bar(300,100.,103.,97.,99.)
        x=r.stop_first(seq,0,'SELL',1)
        self.assertEqual(x['exit_reason'],'STOP')
        self.assertLess(x['gross_bps'],0)
    def test_buy_gap_through_stop_fills_worse_than_stop(self):
        seq=[bar(i*300) for i in range(14)]
        seq[1]=bar(300,100.,100.4,99.7,100.)
        seq[2]=bar(600,95.,95.5,94.9,95.)
        x=r.stop_first(seq,0,'BUY',1)
        self.assertEqual(x['exit_reason'],'STOP_GAP')
        self.assertLess(x['gross_bps'],10000*math.log(98.8/100))
    def test_sell_gap_through_stop_fills_worse_than_stop(self):
        seq=[bar(i*300) for i in range(14)]
        seq[1]=bar(300,100.,100.4,99.7,100.)
        seq[2]=bar(600,105.,106.,104.,105.)
        x=r.stop_first(seq,0,'SELL',1)
        self.assertEqual(x['exit_reason'],'STOP_GAP')
        self.assertLess(x['gross_bps'],10000*math.log(100/101.2))
    def test_gap_rejected(self):
        seq=[bar(i*300) for i in range(14)]
        seq[8]['time']+=300
        self.assertIsNone(r.stop_first(seq,0,'BUY',1))
    def test_no_negative_prices(self):
        seq=[bar(i*300) for i in range(14)]
        self.assertIsNone(r.stop_first(seq,0,'BUY',120))
    def test_invalid_stop_direction(self):
        seq=[bar(i*300) for i in range(14)]
        self.assertIsNone(r.stop_first(seq,0,'HOLD',1))
    def test_target_buy(self):
        seq=[bar(i*300) for i in range(14)]
        seq[1]=bar(300,100.,102.5,99.9,102.)
        x=r.stop_first(seq,0,'BUY',1)
        self.assertEqual(x['exit_reason'],'TP')
        self.assertGreater(x['gross_bps'],0)
    def test_time_exit_uses_complete_window(self):
        seq=[bar(i*300) for i in range(14)]
        x=r.stop_first(seq,0,'BUY',1)
        self.assertEqual(x['exit_reason'],'TIME')
        self.assertAlmostEqual(x['gross_bps'],0)
    def test_histogram_no_fills_for_empty(self):
        x=r.summary([])
        self.assertEqual(x['n'],0)
        self.assertIsNone(x['hypothetical_cost_scenarios']['20']['mean_net_bps'])
    def test_negative_after_cost(self):
        x=r.summary([{'gross_bps':8.,'exit_reason':'TIME'},{'gross_bps':-2.,'exit_reason':'STOP'}])
        self.assertEqual(x['hypothetical_cost_scenarios']['10']['mean_net_bps'],-7.)
    def test_point_in_time_cannot_use_open_h1(self):
        tf={}
        ends={}
        for frame,duration in r.TF.items():
            tf[frame]=[bar(i*duration) for i in range(162)]
            ends[frame]=[x['time']+duration for x in tf[frame]]
        self.assertIsNone(r.point_in_time(tf,ends,160*300))
        ref=r.point_in_time(tf,ends,162*14400)
        self.assertIsNotNone(ref)
        self.assertTrue(all(ref[k][-1]['time']+v<=162*14400 for k,v in r.TF.items()))
    def test_missing_heldout_score_is_not_profit_claim(self):
        x=r.summary([{'gross_bps':2.,'exit_reason':'TIME'}])
        self.assertIsNone(x['hypothetical_cost_scenarios']['10']['lower_95_normal_approx_bps'])

if __name__=='__main__':unittest.main()
