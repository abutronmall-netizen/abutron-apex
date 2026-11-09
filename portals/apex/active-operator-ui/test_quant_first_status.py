#!/usr/bin/env python3
import unittest
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("quant_status",str(Path(__file__).with_name("quant_first_status.py")))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=1793980000.0
def quant():
    return {"schema":"abutron.apex.quant_first.shadow.v1",
            "checked_at_utc":__import__("datetime").datetime.fromtimestamp(NOW,__import__("datetime").timezone.utc).isoformat(),
            "orders_enabled":False,"execution_authorized":False,"smc_ict_mandatory":False,
            "brokers":{"Deriv":{"status":"READONLY_RESEARCH","instruments":[
                {"execution_authorized":False,"research_bias":"BUY"},
                {"execution_authorized":False,"research_bias":"HOLD"},
                {"execution_authorized":False,"research_bias":"SELL"}
            ]}}}
def fp():
    return {"schema":"abutron.fpmarkets.quant.multi_account.readonly.v1",
            "checked_at_utc":quant()["checked_at_utc"],
            "orders_enabled":False,"execution_authorized":False,
            "accounts":[{"status":"PARTIAL_BROKER_DATA_RESEARCH_ONLY","verified_symbols":11},
                        {"status":"PARTIAL_BROKER_DATA_RESEARCH_ONLY","verified_symbols":11}]}
def replay():
    return {"schema":"abutron.apex.quant_deriv.replay.v1",
            "checked_at_utc":quant()["checked_at_utc"],"orders_enabled":False,
            "net_profitability_verified":False,"holdout_edge_verified":False,
            "history_source_integrity":{"mismatched_candles":0,"native_candles_crosschecked":1800},
            "symbols":{"Volatility 75 Index.0":{"m5_history_bars":1151,"status":"EXPLORATORY",
                "strategies":{"quant":{"raw_signal_candles":1}}}}}
class QuantDashboardTests(unittest.TestCase):
    def test_initial_fail_closed(self):
        r=m.build(now=NOW)
        self.assertFalse(r["execution_authorized"])
        self.assertEqual(r["deriv"]["status"],"UNVERIFIED")
    def test_valid_broker_reports(self):
        r=m.build(quant(),fp(),replay(),NOW)
        self.assertEqual(r["deriv"]["symbols"],3)
        self.assertEqual(r["deriv"]["research_candidates"],2)
        self.assertEqual(r["fp_markets"]["accounts"],2)
        self.assertEqual(r["fp_markets"]["coverage"][0]["verified"],11)
        self.assertFalse(r["validation"]["net_profitability_verified"])
    def test_fake_authorized_quant_rejected(self):
        q=quant();q["execution_authorized"]=True
        self.assertEqual(m.build(q,now=NOW)["deriv"]["status"],"UNVERIFIED")
    def test_fake_order_authorized_fp_rejected(self):
        f=fp();f["orders_enabled"]=True
        self.assertEqual(m.build(fp=f,now=NOW)["fp_markets"]["status"],"UNVERIFIED")
    def test_stale_feed_rejected(self):
        self.assertEqual(m.build(quant(),fp(),replay(),NOW+1000)["deriv"]["status"],"UNVERIFIED")
    def test_fake_profitability_rejected(self):
        a=replay();a["net_profitability_verified"]=True
        self.assertEqual(m.build(replay=a,now=NOW)["validation"]["status"],"UNVERIFIED")
    def test_account_identifiers_never_released(self):
        f=fp();f["accounts"][0]["connection_id"]="a"*32
        self.assertNotIn("a"*32,str(m.build(fp=f,now=NOW)))
    def test_true_order_flow_remains_unverified(self):
        r=m.build(quant(),fp(),replay(),NOW)
        self.assertFalse(r["verified_institutional_order_flow"])
        self.assertTrue(r["price_quote_flow_proxy_only"])

if __name__=="__main__":unittest.main()
