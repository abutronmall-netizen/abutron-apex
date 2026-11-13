#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import math
import unittest

spec=importlib.util.spec_from_file_location("replay",str(Path(__file__).with_name("abutron_quant_replay_v1.py")))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

def candles(n=100,period=300,base=1800000000):
    out=[]
    for i in range(n):
        o=100.0+i*.01
        out.append({"time":base+i*period,"open":o,"high":o+.2,"low":o-.2,"close":o+.1})
    return out

class ReplayTests(unittest.TestCase):
    def test_point_in_time_excludes_future_h1(self):
        start=1800000000
        data={"M1":candles(100,60,start-86400),
              "M5":candles(100,300,start),
              "M15":candles(100,900,start-86400),
              "H1":candles(100,3600,start-2*86400),
              "H4":candles(100,14400,start-10*86400),
              "D1":candles(100,86400,start-100*86400)}
        for i in (80,85,99):
            snap,end=r.history_asof(data,i)
            self.assertEqual(snap["M5"][-1]["time"],data["M5"][i]["time"])
            for tf,seconds in r.FRAMES.items():
                self.assertTrue(all(x["time"]+seconds<=end for x in snap[tf]))

    def test_research_trade_nonoverlap(self):
        data=candles(110)
        raw=[(80,"BUY"),(81,"SELL"),(82,"BUY"),(83,"BUY"),(90,"SELL")]
        trades=r.select_trades(raw,data,80,100)
        self.assertEqual([x["index"] for x in trades],[80,83,90])
        self.assertTrue(all(math.isfinite(x["gross_directional_move_bps"]) for x in trades))

    def test_cannot_score_trade_costs(self):
        stats=r.score([])
        self.assertIsNone(stats["gross_direction_hit_rate"])
        self.assertFalse(stats["net_expectancy_verified"])
        self.assertFalse(stats["cost_adjusted"])

    def test_wrong_side_does_not_trade(self):
        data=candles(100)
        self.assertFalse(r.select_trades([(80,"HOLD"),(82,"UNKNOWN")],data,80,90))

    def test_missing_history_blocks(self):
        data={tf:candles(85,period) for tf,period in r.FRAMES.items()}
        out=r.replay(data,None,None)
        self.assertEqual(out["status"],"HOLD_INSUFFICIENT_HISTORY")
        self.assertFalse(out["strategies"])

    def test_static_schema_requires_no_order(self):
        self.assertEqual(r.HOLD_BARS,3)
        self.assertEqual(len(r.SYMBOLS),3)
        self.assertNotIn("Kronos",str(r.SYMBOLS))

if __name__=="__main__":
    unittest.main()
