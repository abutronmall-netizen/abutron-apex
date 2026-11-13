#!/usr/bin/env python3
"""Account-isolated FP Markets quant research security and data-lineage tests."""
import copy
import hashlib
import importlib.util
import pathlib
import unittest
import time

BASE=pathlib.Path(__file__).parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path))
    x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x);return x
m=load("fp_account_quant",BASE/"abutron_fp_account_quant_v1.py")
original=load("fp_native_reader",m.FMOD)
quant=load("fp_quant",m.QMOD)

class AccountIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sqlite3
        with sqlite3.connect("file:"+str(m.DB)+"?mode=ro",uri=True) as c:
            rows=c.execute("SELECT id FROM apex_mt5_connections WHERE broker='FP Markets' AND environment='DEMO' AND broker_server='FPMarketsSC-Demo' AND status='CONNECTED'").fetchall()
        assert len(rows)>=2
        cls.cids=[x[0] for x in rows]
        cls.source=original.read(m.FEED/"partial"/(cls.cids[0]+".json"))
        cls.summary=original.read(m.FEED/"summary.json")
        cls.now=time.time()
    def report(self,d=None,summary=None,cid=None,now=None):
        return m.make_account_report(d if d is not None else copy.deepcopy(self.source),
              summary if summary is not None else copy.deepcopy(self.summary),
              cid or self.cids[0],original,quant,self.now if now is None else now)
    def test_legitimate_source_no_order_authority(self):
        r=self.report()
        self.assertEqual(r["symbols_total"],13)
        self.assertFalse(r["orders_enabled"])
        self.assertFalse(r["execution_authorized"])
        self.assertFalse(r["smc_ict_mandatory"])
        self.assertFalse(r["true_orderflow_connected"])
    def test_missing_and_ambiguous_symbols_remain_hold(self):
        r=self.report()
        missing={x["symbol"]:x for x in r["instruments"] if not x["available"]}
        # Broker mapping is dynamic; do not hard-code formerly unavailable symbols.
        expected={symbol for symbol,entry in self.source["mapping"].items()
                  if entry["status"] in ("MISSING","AMBIGUOUS")}
        self.assertEqual(set(missing),expected)
        self.assertEqual(set(r["symbols_unavailable"]),expected)
        self.assertTrue(all(x["research_bias"]=="HOLD" and not x["orders_enabled"]
                            and not x["execution_authorized"] for x in missing.values()))
    def test_account_spoof_blocked(self):
        with self.assertRaises(ValueError):
            self.report(cid=self.cids[1])
    def test_stale_feed_blocked(self):
        with self.assertRaises(ValueError):
            self.report(now=self.now+900)
    def test_fake_complete_feed_denied(self):
        d=copy.deepcopy(self.source);d["status"]="BROKER_NATIVE_DATA_COMPLETE"
        with self.assertRaises(ValueError):self.report(d=d)
    def test_false_order_enabled_denied(self):
        d=copy.deepcopy(self.source);d["execution_enabled"]=True
        with self.assertRaises(ValueError):self.report(d=d)
    def test_unverified_symbol_denied(self):
        d=copy.deepcopy(self.source)
        target=next(iter(d["bars"]))
        d["mapping"][target]["actual"]="UNVERIFIED-TICKER"
        with self.assertRaises(ValueError):self.report(d=d)
    def test_missing_quote_denied(self):
        d=copy.deepcopy(self.source)
        d["quotes"].pop(next(iter(d["quotes"])))
        with self.assertRaises(ValueError):self.report(d=d)
    def test_all_account_rows_research_only(self):
        r=self.report()
        self.assertTrue(all(x["execution_authorized"] is False and x["orders_enabled"] is False for x in r["instruments"]))
    def test_private_connection_id_not_published(self):
        r=self.report()
        self.assertNotIn(self.cids[0],str(r))
        self.assertEqual(r["account_fingerprint"],hashlib.sha256(self.cids[0].encode()).hexdigest()[:24])

if __name__=="__main__":
    unittest.main()
