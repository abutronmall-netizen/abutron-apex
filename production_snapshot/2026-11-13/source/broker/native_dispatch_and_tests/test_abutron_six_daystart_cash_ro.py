#!/usr/bin/python3
"""ABUTRON broker-native UTC daystart balance validation tests."""
import runpy
import unittest
from unittest.mock import patch

FILE="/var/lib/abutron-mcp/abutron-six-daystart-broker-cash-ro.py"
m=runpy.run_path(FILE,run_name="_unit_test")
class HistoricalBalanceTests(unittest.TestCase):
 def test_authentic_native_daystart_is_account_bound(self):
  r=m["inspect"]()
  self.assertEqual(r["fp_native_daystart_cash_reconstructed"],2)
  self.assertEqual(r["deriv_trade_only_daystart_balance_estimated"],3)
  self.assertFalse(r["native_true_daystart_equity_certified"])
  self.assertFalse(r["native_true_intraday_highwater_certified"])
  self.assertFalse(r["complete_account_lifetime_history_certified"])
  self.assertFalse(r["current_broker_order_ack_certified"])
  self.assertEqual(len(r["accounts"]),6)
  bysuffix={a["account_suffix"]:a for a in r["accounts"]}
  self.assertAlmostEqual(bysuffix["0512"]["current_broker_balance_usd"],99023.85,2)
  self.assertAlmostEqual(bysuffix["1636"]["utc_daystart_reconstructed_cash_balance_usd"],100000,2)
  self.assertFalse(bysuffix["6207"]["verified_daystart_cash_balance"])
 def test_negative_and_nan_denied(self):
  with self.assertRaises(Exception):m["money"]("NaN")
  with self.assertRaises(Exception):m["money"]("Infinity")
 def test_deriv_selected_window_identity_nonclaim(self):
  r=m["inspect"]()
  for x in r["accounts"]:
   self.assertFalse(x.get("verified_native_intraday_peak_equity",False))
  self.assertTrue(next(x for x in r["accounts"] if x["account_suffix"]=="6207")
                  ["missing_deposit_withdrawal_deals_possible"])
 def test_live_stays_no_history(self):
  r=m["inspect"]()
  live=next(x for x in r["accounts"] if x["account_suffix"]=="0178")
  self.assertEqual(live["state"],"NO_LIVE_FINANCIAL_DEAL_HISTORY")
  self.assertFalse(live["execution_authorized"])
 def test_fp_selected_window_requires_cash_balance_tie(self):
  r=m["inspect"]()
  for x in r["accounts"]:
   if x["broker"]=="FP Markets":
    self.assertTrue(x["cashflow_balance_ties_to_native_window"])
    self.assertFalse(x["verified_native_intraday_peak_equity"])

if __name__=="__main__":unittest.main(verbosity=2)
