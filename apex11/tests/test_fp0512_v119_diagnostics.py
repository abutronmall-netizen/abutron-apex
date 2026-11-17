#!/usr/bin/env python3
"""Static regression contract for FP0512 V119 staged diagnostics.

These tests intentionally do not assert that native MT5 compile or broker OrderCalcProfit
succeeded. See Issue #17 for independent broker-native test requirements.
"""
import pathlib
import re
import unittest

HERE=pathlib.Path(__file__).resolve()
STAGED=HERE.parent/"AbutronFPNativeOrderBridgeV101.mq5"
REPO=HERE.parents[1]/"mql5"/"fp0512_v118"/"AbutronFPNativeOrderBridgeV101.mq5"
SOURCE=(STAGED if STAGED.exists() else REPO).read_text(encoding="utf-8")
START=SOURCE.index("string NativeAdaptivePlan(")
END=SOURCE.index("\nbool PortfolioCanAdd(",START)
PLAN=SOURCE[START:END]
CODES=(
"ACCOUNT_OR_PENDING_ORDERS","M5_UNAVAILABLE","M5_STALE",
"M5_INVALID_BAR","ATR_INVALID","TICK_INVALID","SL_GEOMETRY",
"TP_GEOMETRY","SPREAD","MINSTOP_FREEZE","POSITION_TICKET_INVALID",
"POSITION_DATA_INVALID","OPEN_POSITION_CALCPROFIT","BUDGET_INVALID",
"LOT_RULES_INVALID","MIN_LOT_CALCPROFIT","MIN_LOT_ABOVE_RISK_BUDGET",
"LOT_RANGE","PROJECTED_CALCPROFIT","STOP_RISK_BUDGET",
"REWARD_RISK","MARGIN_INVALID","MARGIN"
)
class V119DiagnosticContract(unittest.TestCase):
    def test_version_and_function_signature(self):
        self.assertIn('#property version "1.19"',SOURCE)
        self.assertIn("string NativeAdaptivePlan(",SOURCE)
        self.assertNotIn("bool NativeAdaptivePlan(",SOURCE)
        self.assertIn('return "";',PLAN)
    def test_unchanged_native_receipt_contract(self):
        self.assertIn('APEX_FP_NATIVE_V1',SOURCE)
        self.assertIn('status+"\\r\\n"+reason+"\\r\\n"',SOURCE)
        self.assertIn('IntegerToString((long)TimeGMT())',SOURCE)
        self.assertIn('gNonce+"\\r\\n"+gLogin+"\\r\\n"+gServer',SOURCE)
    def test_risk_and_protection_invariants(self):
        for token in ('equity*0.20-existing','equity*0.001',
                      'budget=.85*maxBudget','stopRisk>budget+0.005',
                      'targetCash/stopRisk<1.50',
                      'ACCOUNT_MARGIN_FREE)*0.10','OrderCheck(',
                      'req.sl=sl;req.tp=tp'):
            self.assertIn(token,SOURCE,token)
    def test_adaptive_diagnostics_only_and_legacy_unchanged(self):
        self.assertIn('if(adaptive)',SOURCE)
        self.assertIn('string stopFail=NativeAdaptivePlan(',SOURCE)
        self.assertIn('NATIVE_USD_STOP_CALCULATION_FAILED:"+stopFail',SOURCE)
        self.assertIn('Receipt(key,"BLOCKED","NATIVE_USD_STOP_CALCULATION_FAILED");return;',SOURCE)
        self.assertNotIn('return false;',PLAN)
        self.assertEqual(len(set(re.findall(r'return "([A-Z0-9_]+)";',PLAN))),23)

def _make_test(code):
    def test(self):
        self.assertIn('return "'+code+'";',PLAN)
    test.__name__="test_diagnostic_"+code.lower()
    return test

for _code in CODES:
    setattr(V119DiagnosticContract, "test_diagnostic_"+_code.lower(),_make_test(_code))

if __name__=="__main__":
    unittest.main(verbosity=1)
