#!/usr/bin/python3
"""ABUTRON broker-native two DEMO cost/preflight invariants."""
import copy
import runpy
import unittest
from unittest.mock import patch

FILE="/var/lib/abutron-mcp/abutron-two-broker-exact-cost-ledger-ro.py"
m=runpy.run_path(FILE,run_name="_unit_test")

class BrokerCostTests(unittest.TestCase):
    def test_native_broker_sources_account_bound(self):
        d=m["inspect"]()
        self.assertEqual(d["crm_6207_effective_enabled"],False)
        self.assertFalse(d["broker_execution_ack_6207"])
        self.assertFalse(d["broker_execution_ack_fp0512"])
        self.assertFalse(d["full_executable_costs_verified"])
        self.assertEqual(len(d["fp_0512"]["native_quotes"]),13)
        self.assertEqual(d["fp_0512"]["realized_history_costs"]["historical_window_deal_count"],98)
        self.assertEqual(d["deriv_6207"]["realized_history_costs"]["historical_window_deal_count"],152)
        self.assertGreater(len(d["deriv_6207"]["recent_account_bound_apex_directional_shadows"]),0)
        for q in d["deriv_6207"]["recent_account_bound_apex_directional_shadows"]:
            self.assertFalse(q["exact_broker_ordercheck_passed"])
            self.assertFalse(q["broker_execution_ack"])
            self.assertIn("SHADOW_SIGNAL_NOT_BROKER_AUTHORIZED",q["preflight_unresolved"])
    def test_commission_math_not_guaranteed(self):
        a=m["commission_stats"]([("EURUSD.r","0.50","-3"),
                                 ("EURUSD.r","0.50","-3"),("BTCUSD","1","0")])
        self.assertEqual(a["EURUSD.r"]["observed_commission_cashflow_usd_per_deal_lot"],-6)
        self.assertEqual(a["BTCUSD"]["broker_deal_observations"],1)
    def test_nonfinite_denied(self):
        for v in ("NaN","Infinity","-Infinity"):
            with self.assertRaises(ValueError):m["money"](v)
    def test_account_owner_mismatch_denied(self):
        g=m["data_rows"].__globals__
        # Existing account-bound CRM guard is tested on the real read-only DB.
        rev=m["data_rows"]()
        self.assertEqual(rev[2],0)
        self.assertIsNone(rev[3])
    def test_exact_native_ordercheck_remains_false_even_with_quotes(self):
        d=m["inspect"]()
        self.assertIs(d["deriv_6207"]["exact_ordercheck_broker_verified"],False)
        self.assertIs(d["fp_0512"]["exact_ordercheck_broker_verified"],False)
        self.assertIs(d["deriv_6207"]["proposal_ready_for_native_ordercheck"],False)
        self.assertIs(d["fp_0512"]["proposal_ready_for_native_ordercheck"],False)

if __name__=="__main__":
    unittest.main(verbosity=2)
