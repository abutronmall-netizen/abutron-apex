#!/usr/bin/env python3
"""Regression tests for isolated, non-trading ABUTRON quant-first v1."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import time
import unittest

spec=importlib.util.spec_from_file_location("abutron_quant_first_v1",str(Path(__file__).with_name("abutron_quant_first_v1.py")))
quant=importlib.util.module_from_spec(spec)
spec.loader.exec_module(quant)

NOW=1_800_000_000

def candles(n=80,seconds=300,step=0.001,now=NOW,initial=100.0):
    start=now-(n+2)*seconds
    out=[]
    for i in range(n):
        o=initial*math.exp(step*i)
        c=o*math.exp(step*(1.0+0.1*math.sin(i)))
        h=max(o,c)*1.0005
        l=min(o,c)*0.9995
        out.append({"time":start+i*seconds,"open":o,"high":h,"low":l,"close":c})
    return out

def frames():
    return {"M5":candles(90,300),
            "M15":candles(90,900),
            "H1":candles(90,3600)}

def fp_partial(cid="a"*32):
    return {"schema":"abutron.fpmarkets.native.partial.readonly.v1",
        "account_mode":"DEMO","connection_id":cid,
        "bars":{"EURUSD":frames()},
        "quotes":{"EURUSD":{"bid":99.9,"ask":100.0,"time":NOW-20}}}

def deriv_doc():
    return {"schema":"apex.mt5.market.v1","source":"Deriv DEMO MT5",
            "data":{sym:{**frames(),"H4":candles(90,14400)} for sym in quant.DERIV_SCOPE}}

class QuantFirstTests(unittest.TestCase):
    def test_deriv_scope_five_no_order_authority(self):
        out=quant.build(deriv_doc(),None,[],NOW)
        self.assertEqual(len(out["brokers"]["Deriv"]["instruments"]),5)
        self.assertFalse(out["orders_enabled"])
        self.assertFalse(out["execution_authorized"])
        self.assertFalse(out["smc_ict_mandatory"])
        self.assertFalse(out["out_of_sample_edge_verified"])
        self.assertNotIn("candidate_orders",out)

    def test_v10_v100_explicitly_researched_without_order_authority(self):
        out=quant.build(deriv_doc(),None,[],NOW)
        rows={r["symbol"]:r for r in out["brokers"]["Deriv"]["instruments"]}
        for sym in ("Volatility 10 Index.0","Volatility 100 Index.0"):
            self.assertIn(sym,rows)
            self.assertFalse(rows[sym]["execution_authorized"])
            self.assertFalse(rows[sym]["orders_enabled"])
            self.assertIn("m5_entry_quality",rows[sym])
            self.assertIn("h4_direction_confirmed",rows[sym])
        self.assertNotIn("candidate_orders",out)

    def test_v10_v100_quality_gate_is_fail_closed(self):
        baseline=[(i,100.0,100.1,99.9,100.0) for i in range(80)]
        for side in ("BUY","SELL"):
            self.assertEqual(quant.deriv_reentry_m5_quality(baseline,"HOLD",2),"NO_DIRECTION")
            self.assertEqual(quant.deriv_reentry_m5_quality(baseline,side,0),"INVALID_ENTRY_EVIDENCE")
        over=baseline[:-1]+[(80,100.0,104.0,99.0,103.0)]
        weak=baseline[:-1]+[(80,100.0,100.3,99.8,100.2)]
        opposite=baseline[:-1]+[(80,100.0,100.2,99.3,99.5)]
        valid=baseline[:-1]+[(80,100.0,100.9,99.9,100.8)]
        self.assertEqual(quant.deriv_reentry_m5_quality(over,"BUY",2),"OVEREXTENDED_EMA9")
        self.assertEqual(quant.deriv_reentry_m5_quality(weak,"BUY",2),"WEAK_M5_BODY")
        self.assertEqual(quant.deriv_reentry_m5_quality(opposite,"BUY",1),"BUY_CANDLE_NOT_CONFIRMED")
        self.assertEqual(quant.deriv_reentry_m5_quality(valid,"BUY",2),"PASS")

    def test_reentry_missing_h4_is_blocked(self):
        d=deriv_doc()
        del d["data"]["Volatility 10 Index.0"]["H4"]
        out=quant.build(d,None,[],NOW)
        row=next(x for x in out["brokers"]["Deriv"]["instruments"] if x["symbol"]=="Volatility 10 Index.0")
        self.assertEqual(row["research_bias"],"HOLD")
        self.assertEqual(row["source_status"],"BLOCKED")
        self.assertFalse(row["execution_authorized"])

    def test_deriv_does_not_fabricate_orderflow(self):
        row=quant.assess("Volatility 75 Index.0",frames(),"Deriv",now=NOW)
        self.assertEqual(row["flow_evidence"],"CANDLE_BODY_PRICE_FLOW_PROXY_NOT_ORDER_BOOK")
        self.assertFalse(row["institutional_order_flow_verified"])
        self.assertFalse(row["execution_authorized"])

    def test_fp_requires_verified_quote(self):
        row=quant.assess("EURUSD",frames(),"FP Markets",now=NOW)
        self.assertEqual(row["research_bias"],"HOLD")
        self.assertEqual(row["source_status"],"BLOCKED")
        self.assertIn("QUOTE",row["reason"])

    def test_fp_quote_does_not_claim_trade_flow(self):
        row=quant.assess("EURUSD",frames(),"FP Markets",
                         quote={"bid":100.0,"ask":100.01,"time":NOW-10},now=NOW)
        self.assertEqual(row["flow_evidence"],"BROKER_BID_ASK_SPREAD_ONLY_NO_TRADE_FLOW")
        self.assertFalse(row["institutional_order_flow_verified"])

    def test_spread_filter(self):
        row=quant.assess("EURUSD",frames(),"FP Markets",
                         quote={"bid":90.0,"ask":100.0,"time":NOW-10},now=NOW)
        self.assertEqual(row["research_bias"],"HOLD")
        self.assertEqual(row["source_status"],"BLOCKED")

    def test_future_bar_invalid(self):
        f=frames()
        f["M5"][-1]["time"]=NOW+3600
        self.assertEqual(quant.assess("X",f,"Deriv",now=NOW)["source_status"],"BLOCKED")

    def test_non_chronological_bars_invalid(self):
        f=frames()
        f["M5"][-1]["time"]=f["M5"][-2]["time"]
        self.assertEqual(quant.assess("X",f,"Deriv",now=NOW)["source_status"],"BLOCKED")

    def test_fake_or_negative_prices_invalid(self):
        f=frames()
        f["M5"][-1]["close"]=-3
        self.assertEqual(quant.assess("X",f,"Deriv",now=NOW)["source_status"],"BLOCKED")

    def test_stale_feed_is_not_eligible(self):
        self.assertEqual(quant.assess("X",frames(),"Deriv",now=NOW+2*86400)["source_status"],"BLOCKED")

    def test_partial_fp_accounts_not_combined(self):
        summary={"schema":"abutron.fpmarkets.feed.readonly.v1",
                 "native_feeds_complete":0,"fp_accounts_linked":6}
        result=quant.build(None,summary,[fp_partial("a"*32),fp_partial("b"*32)],NOW)
        fp=result["brokers"]["FP Markets"]
        self.assertEqual(fp["status"],"FP_PARTIAL_OR_MULTI_ACCOUNT_UNVERIFIED")
        self.assertEqual(len(fp["instruments"]),2)
        self.assertNotEqual(fp["instruments"][0]["account_fingerprint"],
                            fp["instruments"][1]["account_fingerprint"])
        self.assertTrue(all(not x["fp_feed_certified"] for x in fp["instruments"]))
        self.assertFalse(fp["orders_enabled"])

    def test_live_fp_source_not_accepted(self):
        summary={"schema":"abutron.fpmarkets.feed.readonly.v1",
                 "native_feeds_complete":0,"fp_accounts_linked":6}
        doc=fp_partial()
        doc["account_mode"]="LIVE"
        self.assertEqual(quant.build(None,summary,[doc],NOW)["brokers"]["FP Markets"]["instruments"],[])

    def test_untrusted_deriv_source_blocked(self):
        doc=deriv_doc()
        doc["source"]="unverified vendor"
        self.assertEqual(quant.build(doc,None,[],NOW)["brokers"]["Deriv"]["instruments"],[])

    def test_output_contains_no_order_or_private_id(self):
        result=quant.build(deriv_doc(),{"schema":"abutron.fpmarkets.feed.readonly.v1",
            "native_feeds_complete":0,"fp_accounts_linked":6},[fp_partial()],NOW)
        with tempfile.TemporaryDirectory() as directory:
            quant.atomic_write(result,Path(directory))
            text=(Path(directory)/"latest.json").read_text()
            self.assertNotIn("a"*32,text)
            self.assertFalse(json.loads(text)["orders_enabled"])
            self.assertFalse(json.loads(text)["position_state_modified"])

if __name__=="__main__":
    unittest.main()
