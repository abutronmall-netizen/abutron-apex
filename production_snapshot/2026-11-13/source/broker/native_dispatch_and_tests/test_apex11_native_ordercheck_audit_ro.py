#!/usr/bin/python3
import importlib.util,unittest
from decimal import Decimal
spec=importlib.util.spec_from_file_location('audit','/var/lib/abutron-mcp/abutron-apex11-6207-native-ordercheck-audit-ro.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=1794262020
NONCE='a'*32
ID='b'*64
DEC='c'*64
D={'source_decision_id':DEC,'signal_id':ID,'symbol':'Volatility 75 Index.0',
   'side':'SELL','risk_budget_usd':'8.14','expires_utc':NOW+5,
   'order':{'volume':'0.032','price':'39687.86','sl':'39700.15','tp':'39662.40',
            'type':'ORDER_TYPE_SELL','magic':73113011}}
L=['ABUTRON_APEX11_EXACT_CHECK_NATIVE_NO_SEND_V1',NONCE,'32456207','Deriv-Demo',
   DEC,ID,'Volatility 75 Index.0','SELL','0.032','39687.86','39700.15',
   '39662.40',str(NOW),'CHECK_PASS_NO_SEND','BROKER_NATIVE_EXACT_CHECK_ONLY',
   'ORDER_CHECK_CALLED','0','0','-5.20','11.30','0.50','39687.86',
   '39687.86','NO_ORDER_SEND;NO_CRM_CHANGE;NO_BROKER_ACK']
class T(unittest.TestCase):
 def test_exact_positive_fixture_is_parser_only(self):
  self.assertEqual(m.verify_receipt(L,D,NONCE,NOW),'NATIVE_EXACT_ORDERCHECK_PROVEN_NO_SEND')
 def test_missing_native_ordercheck_call(self):
  a=L.copy();a[15]='ORDER_CHECK_NOT_CALLED'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'NATIVE_ORDERCHECK_NOT_CALLED')
 def test_bad_broker_retcode(self):
  a=L.copy();a[16]='10016'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'NATIVE_ORDERCHECK_RETCODE_OR_PROFIT_INVALID')
 def test_broker_rejection(self):
  a=L.copy();a[13]='DENY';a[14]='MT5_ORDERCHECK_BROKER_REJECTED'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'NATIVE_ORDERCHECK_NOT_PASSED')
 def test_stale_receipt(self):
  a=L.copy();a[12]=str(NOW-60)
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'NATIVE_PROOF_STALE_OR_EXPIRED')
 def test_wrong_broker_account(self):
  a=L.copy();a[2]='32456208'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'APEX_ORDER_NATIVE_RECEIPT_IDENTITY_MISMATCH')
 def test_manual_magic(self):
  b=dict(D,order=dict(D['order'],magic=0))
  self.assertEqual(m.verify_receipt(L,b,NONCE,NOW),'APEX_ORDER_NATIVE_RECEIPT_IDENTITY_MISMATCH')
 def test_different_order_lots(self):
  a=L.copy();a[8]='0.3'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'APEX_ORDER_NATIVE_RECEIPT_IDENTITY_MISMATCH')
 def test_native_requote_matching_bid_is_attributed(self):
  a=L.copy();a[9]='39688.20';a[21]='39688.20';a[22]='39688.20'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'NATIVE_EXACT_ORDERCHECK_PROVEN_NO_SEND')
 def test_native_requote_without_matching_bid_is_rejected(self):
  a=L.copy();a[9]='39688.20'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'APEX_ORDER_NATIVE_RECEIPT_IDENTITY_MISMATCH')
 def test_different_stop(self):
  a=L.copy();a[10]='39750.15'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'APEX_ORDER_NATIVE_RECEIPT_IDENTITY_MISMATCH')
 def test_excessive_native_stop(self):
  a=L.copy();a[18]='-9.40'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'NATIVE_STOP_EXCEEDS_DRAFT_BUDGET')
 def test_no_send_declaration_required(self):
  a=L.copy();a[-1]='ORDER_SEND'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'APEX_ORDER_NATIVE_RECEIPT_IDENTITY_MISMATCH')
 def test_invalid_negative_margin(self):
  a=L.copy();a[20]='-1'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'NATIVE_RISK_RR_INVALID')
 def test_nonfinite_native_profit(self):
  a=L.copy();a[19]='NaN'
  self.assertEqual(m.verify_receipt(a,D,NONCE,NOW),'NATIVE_ORDERCHECK_RETCODE_OR_PROFIT_INVALID')
if __name__=='__main__':unittest.main(verbosity=2)
