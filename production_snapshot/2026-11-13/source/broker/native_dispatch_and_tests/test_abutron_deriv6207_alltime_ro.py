#!/usr/bin/python3
"""Independent tests of Deriv 6207 all-range native broker deal validator."""
import runpy,unittest
from unittest.mock import patch

m=runpy.run_path('/var/lib/abutron-mcp/abutron-deriv6207-native-alltime-verify-ro.py',run_name='_test')
class AlltimeTests(unittest.TestCase):
 def test_real_broker_native_full_range_balances(self):
  x=m["inspect"]()
  self.assertEqual(x["native_full_range_deals"],153)
  self.assertEqual(x["native_matched_closed_positions"],76)
  self.assertEqual(x["native_positive_deposits"],1)
  self.assertEqual(x["native_funding_cashflow_usd"],10000.0)
  self.assertAlmostEqual(x["native_trade_net_cashflow_usd"],-422.39,2)
  self.assertAlmostEqual(x["current_native_broker_balance_usd"],9577.61,2)
  self.assertTrue(x["full_range_cashflow_to_broker_balance_reconciled"])
  self.assertFalse(x["new_order_broker_ack_certified"])
  self.assertFalse(x["true_broker_intraday_equity_peak_verified"])
 def test_forged_account_identity_rejected(self):
  header=("ABUTRON_DERIV_NATIVE_ALLTIME_V1\n"+"a"*32+
          "\n00000000\nDeriv-Demo\nDEMO\nUSD\n1794258816\n0\n1\n"+"\t".join(m["HEAD"])+"\n")
  with self.assertRaisesRegex(ValueError,"HISTORY_SCHEMA"):
   m["parse"](header.encode(),"a"*32,"32456207",True)
 def test_cash_numeric_nonfinite_denied(self):
  for s in ("NaN","Infinity","not_num"):
   with self.assertRaises(ValueError):m["money"](s)
 def test_truncated_alltime_rejected(self):
  nonce="a"*32
  import time
  header=["ABUTRON_DERIV_NATIVE_ALLTIME_V1",nonce,"32456207",
          "Deriv-Demo","DEMO","USD",str(int(time.time())),"0","2","\t".join(m["HEAD"])]
  fake="\n".join(header+["END\t0\t2"]).encode()
  with self.assertRaisesRegex(ValueError,"FULLRANGE_BROKER_DEAL_TOTAL_MISMATCH"):
   m["parse"](fake,nonce,"32456207",True)
 def test_execution_never_enabled_by_report(self):
  x=m["inspect"]()
  self.assertFalse(x["automatic_trading_enabled"])
  self.assertEqual(x["orders_submitted"],0)

if __name__=="__main__":unittest.main(verbosity=2)
