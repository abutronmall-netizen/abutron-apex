#!/usr/bin/python3
"""Deriv 3 DEMO native full-range signed deal and funding negative tests."""
import runpy,unittest,time
m=runpy.run_path('/var/lib/abutron-mcp/abutron-deriv-three-native-fullrange-ro.py',run_name='_test')
class NativeThreeHistoryTests(unittest.TestCase):
 def test_three_live_broker_native_full_range(self):
  r=m["inspect"]()
  self.assertTrue(r["three_native_select_from_zero_fullrange_proved"])
  self.assertEqual(r["native_deals_total"],363)
  self.assertEqual(r["matched_closed_position_ids"],180)
  self.assertEqual(r["all_native_funding_total_usd"],30000.0)
  self.assertFalse(r["full_customer_lifetime_history_certified"])
  self.assertFalse(r["broker_order_ack_certified"])
  self.assertFalse(r["automatic_execution_enabled"])
 def test_identity_mismatch_denied(self):
  from tempfile import TemporaryDirectory
  from pathlib import Path
  with TemporaryDirectory() as t:
   p=Path(t)/"invalid.txt"
   p.write_text("WRONG_HEADER\n")
   with self.assertRaisesRegex(ValueError,"NATIVE_BROKER_LOGIN_SOURCE_CONFLICT"):
    m["parse"](p,"a"*32,"32456207",True)
 def test_numeric_nonfinite_rejected(self):
  for t in ["NaN","Infinity"]:
   with self.assertRaises(ValueError):m["num"](t)
 def test_real_account_range_contains_prior_trade_window(self):
  r=m["inspect"]()
  self.assertEqual([a["native_broker_fullrange_deals"] for a in r["accounts"]],[153,113,97])
  self.assertTrue(all(a["all_returned_deals_cashflow_to_balance_proved"] for a in r["accounts"]))
  self.assertTrue(all(a["fullrange_contains_exact_prior_window"] for a in r["accounts"]))
  self.assertTrue(all(a["native_broker_true_intraday_equity_peak_proved"] is False for a in r["accounts"]))

if __name__=="__main__":unittest.main(verbosity=2)
