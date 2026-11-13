#!/usr/bin/python3
"""ABUTRON six-account minute equity observer independent tests."""
import copy
import pathlib
import runpy
import sqlite3
import unittest
from decimal import Decimal
from unittest.mock import patch

SOURCE="/var/lib/abutron-mcp/abutron-six-equity-observer.py"
m=runpy.run_path(SOURCE,run_name="_equity_observer_test")
sample=m["source_samples"]
g=sample.__globals__

class EquityTests(unittest.TestCase):
    def test_full_six_native_samples(self):
        rows=sample()
        self.assertEqual(len(rows),6)
        self.assertEqual(len({(x[0],x[1]) for x in rows}),6)
    def test_nan_and_negative_rejected(self):
        for v in ["NaN","-0.01","Infinity",None]:
            with self.assertRaises(ValueError):m["amount"](v)
    def test_nonzero_position_denied(self):
        orig=g["trusted_json"]
        def altered(path,age_max=185):
            d,h=orig(path,age_max)
            if path==g["RISK"]:
                d=copy.deepcopy(d)
                any_owner=next(iter(d["owners"].values()))
                any_owner["connections"][0]["snapshot"]["positions_count"]=1
            return d,h
        with patch.dict(g,{"trusted_json":altered}):
            with self.assertRaisesRegex(ValueError,"FLAT"):
                sample()
    def test_live_trade_permission_denied(self):
        orig=g["trusted_json"]
        def altered(path,age_max=185):
            d,h=orig(path,age_max)
            if path==g["RISK"]:
                d=copy.deepcopy(d)
                for owner in d["owners"].values():
                    for a in owner["connections"]:
                        if a.get("environment")=="LIVE":
                            a["snapshot"]["broker_trade_allowed"]=True
            return d,h
        with patch.dict(g,{"trusted_json":altered}):
            with self.assertRaisesRegex(ValueError,"LIVE_TRADING"):
                sample()
    def test_sampled_highwater_is_not_certified_broker_peak(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("""CREATE TABLE equity_samples(
              minute_utc INTEGER,owner_hash TEXT,account_suffix TEXT,broker TEXT,
              environment TEXT,balance_usd TEXT,equity_usd TEXT,risk_report_sha256 TEXT)""")
            start=1794182400 # UTC date; deterministic arithmetic only
            day="2026-11-09"
            for mnt,values in [(0,[100,200]),(1,[105,195]),(2,[95,190])]:
                for suf,equity in zip(("6207","0512"),values):
                    db.execute("INSERT INTO equity_samples VALUES(?,?,?,?,?,?,?,?)",
                      (start+60*mnt,"0"*12,suf,"Deriv" if suf=="6207" else "FP Markets",
                       "DEMO",str(equity),str(equity),"0"*64))
            summary=m["day_summary"](db,day)
            assert summary
            v=summary["0"*12]
            self.assertEqual(v["sampled_minutes_complete_for_owner"],3)
            self.assertFalse(v["true_broker_daystart_or_peak_certified"])

if __name__=="__main__":
    unittest.main(verbosity=2)
