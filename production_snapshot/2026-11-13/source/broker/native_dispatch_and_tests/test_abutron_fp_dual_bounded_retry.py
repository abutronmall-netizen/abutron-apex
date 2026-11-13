#!/usr/bin/python3
"""Read-only FP native report bounded retry regression checks."""
import runpy,unittest
from unittest.mock import patch

FILE="/var/lib/abutron-mcp/abutron-fp-dual-reconcile-bounded-retry-candidate.py"
mod=runpy.run_path(FILE,run_name="_fp_wrapper_test")
ins=mod["inspect"]
g=ins.__globals__
original=g["account"]

class RetryTests(unittest.TestCase):
    def test_transient_native_file_race_recovers_with_fresh_proof(self):
        count={}
        def flaky(cid,*args):
            count[cid]=count.get(cid,0)+1
            if cid.endswith("135e6c") and count[cid]<3:
                raise ValueError("FP_BRIDGE_V3_PROOF_STALE")
            return original(cid,*args)
        with patch.dict(g,{"account":flaky}):
            with patch.object(g["time"],"sleep",lambda _:None):
                report=ins()
        self.assertEqual(report["state"],"RECONCILED_READONLY")
        self.assertEqual(count["35b81a287b6a030f2f46ff426b135e6c"],3)
        self.assertFalse(report["broker_order_authorized"])
    def test_persistent_denial_stays_blocked(self):
        def blocked(cid,*args):
            if cid.endswith("135e6c"):
                raise ValueError("FP_NATIVE_BROKER_POSITION_UNVERIFIED")
            return original(cid,*args)
        with patch.dict(g,{"account":blocked}):
            with patch.object(g["time"],"sleep",lambda _:None):
                report=ins()
        self.assertEqual(report["state"],"BLOCKED")
        item=next(a for a in report["accounts"] if a["account_suffix"]=="0512")
        self.assertEqual(item["error_code"],"FP_NATIVE_BROKER_POSITION_UNVERIFIED")
        self.assertTrue(item["bounded_readonly_retries_exhausted"])
        self.assertFalse(report["broker_order_authorized"])

if __name__=="__main__":
    unittest.main(verbosity=2)
