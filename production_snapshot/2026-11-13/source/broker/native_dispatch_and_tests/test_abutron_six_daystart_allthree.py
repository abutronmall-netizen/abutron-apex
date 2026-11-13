#!/usr/bin/python3
"""Three Deriv DEMO funded UTC cash daystart proof and fail-closed tests."""
import unittest,runpy
from unittest.mock import patch

FILE='/var/lib/abutron-mcp/abutron-six-daystart-broker-cash-allthree-candidate.py'
m=runpy.run_path(FILE,run_name='_test')
class Tests(unittest.TestCase):
 def test_all_three_deriv_deposit_included(self):
  x=m['inspect']()
  self.assertEqual(x['deriv_fullrange_daystart_cash_balances_reconstructed'],3)
  self.assertEqual(x['deriv_trade_only_daystart_balance_estimated'],0)
  d={a['account_suffix']:a for a in x['accounts']}
  for suffix,balance in [('6207',9577.61),('7593',9712.11),('9244',9879.23)]:
   self.assertTrue(d[suffix]['verified_daystart_cash_balance'])
   self.assertEqual(d[suffix]['funding_in_native_history_usd'],10000.0)
   self.assertAlmostEqual(d[suffix]['utc_daystart_reconstructed_cash_balance_usd'],balance,2)
   self.assertFalse(d[suffix]['verified_native_intraday_peak_equity'])
  self.assertFalse(x['native_true_daystart_equity_certified'])
  self.assertFalse(x['current_broker_order_ack_certified'])
 def test_fullrange_proof_false_denied(self):
  orig=m['native_deriv'].__globals__['load']
  alltime=m['native_deriv'].__globals__['DERIV_THREE_ALLTIME']
  def bad(path,ttl=205):
   d=orig(path,ttl)
   if path==alltime:
    d=dict(d);d['three_native_select_from_zero_fullrange_proved']=False
   return d
  with patch.dict(m['native_deriv'].__globals__,{'load':bad}):
   with self.assertRaisesRegex(ValueError,'DERIV_THREE_FULLRANGE_PROOF_INVALID'):
    m['inspect']()
 def test_live_no_history_no_auth(self):
  x=m['inspect']()
  live=[a for a in x['accounts'] if a.get('environment')=='LIVE']
  self.assertEqual(len(live),1)
  self.assertFalse(live[0]['execution_authorized'])
  self.assertFalse(x['execution_enabled'])
if __name__=='__main__':unittest.main(verbosity=2)
