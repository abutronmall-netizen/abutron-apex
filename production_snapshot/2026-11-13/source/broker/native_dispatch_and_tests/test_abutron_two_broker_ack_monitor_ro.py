#!/usr/bin/python3
"""Native two-broker immutable receipt baseline and denial regression tests."""
import pathlib
import tempfile
import runpy
import unittest
from unittest.mock import patch

MODULE=runpy.run_path('/var/lib/abutron-mcp/abutron-two-broker-native-ack-monitor-ro.py',run_name='_test')

class ACKTests(unittest.TestCase):
 def test_current_history_and_no_new_execution_ack(self):
  d=MODULE["inspect"]()
  self.assertEqual(d["state"],"NO_NEW_BROKER_EXECUTION_ACK")
  self.assertEqual(d["fp_0512"]["historical_broker_deal_ack_matches"],46)
  self.assertEqual(d["fp_0512"]["historical_native_ack_count"],46)
  self.assertEqual(d["fp_0512"]["native_receipts_since_monitor_start"],0)
  self.assertEqual(d["deriv_6207"]["native_receipts_since_monitor_start"],0)
  self.assertFalse(d["crm_6207_revision_execution_ack"])
  self.assertFalse(d["broker_execution_ack_for_new_6207_order"])
  self.assertFalse(d["broker_execution_ack_for_new_fp0512_order"])
  self.assertFalse(d["new_order_submission_authorized"])
  self.assertFalse(d["any_new_broker_order_unexpected_with_crm_off"])
  self.assertFalse(d["reused_historical_fp_receipt_as_new_ack"])
 def test_wrong_receipt_nonce_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/('a'*64+'.txt')
   p.write_text('\n'.join(['APEX_NATIVE_V2','a'*64,'ACK','PROVISIONAL','123','456',
                          '1794260200','b'*32,'32456207','Deriv-Demo'])+'\n')
   with self.assertRaisesRegex(ValueError,'SCHEMA'):
    MODULE["receipt_lines"](p,'a'*32,'32456207','Deriv-Demo','APEX_NATIVE_V2')
 def test_ack_without_broker_ticket_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/('a'*64+'.txt')
   p.write_text('\n'.join(['APEX_NATIVE_V2','a'*64,'ACK','PROVISIONAL','0','0',
                         '1794260200','a'*32,'32456207','Deriv-Demo'])+'\n')
   with self.assertRaisesRegex(ValueError,'WITHOUT_BROKER'):
    MODULE["receipt_lines"](p,'a'*32,'32456207','Deriv-Demo','APEX_NATIVE_V2')
 def test_invalid_receipt_path_accepted_never(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/('b'*64+'.txt')
   p.write_text('MALFORMED')
   with self.assertRaises(ValueError):
    MODULE["receipt_lines"](p,'b'*32,'32456207','Deriv-Demo','APEX_NATIVE_V2')
 def test_fp_independent_deal_not_synthetic(self):
  trade={'ticket':'19','order_id':'12','entry':'IN'}
  rec={'status':'ACK','native_broker_deal':19,'native_broker_order':12}
  self.assertTrue(MODULE["fp_proof"]({'trade_deals':[trade]},rec))
  self.assertFalse(MODULE["fp_proof"]({'trade_deals':[]},rec))
  self.assertFalse(MODULE["fp_proof"]({'trade_deals':[trade]},dict(rec,native_broker_deal=20)))
 def test_deriv_receipt_without_all_native_audits_is_not_verified(self):
  with tempfile.TemporaryDirectory() as td:
   rec={'status':'ACK','signal_key':'a'*64}
   self.assertFalse(MODULE["deriv_proof"](pathlib.Path(td),'a'*32,rec))

if __name__=='__main__':unittest.main(verbosity=2)
