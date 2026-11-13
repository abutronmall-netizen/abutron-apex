#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
import abutron_prospective_execution_audit_v2 as a

K='a'*64
NONCE='b'*32
LOGIN='88886207'
BASE=1794000000

def bundle(root):
    root=Path(root)
    request=[
      'ABUTRON_NATIVE_REQUEST_AUDIT_V1',K,NONCE,LOGIN,'Deriv-Demo',
      'Volatility 75 Index.0','BUY','0.02500000','100.1','99.1','102.1',
      '100.0','100.1',str(BASE*1000),str(BASE),'1000','2','15']
    result=[
      'ABUTRON_NATIVE_RESULT_AUDIT_V1',K,NONCE,LOGIN,'Deriv-Demo',
      str(BASE),'1002',str(BASE+1),'1050','1','10009','99',
      '200','201','100.15','100.05','100.16']
    protected=[
      'ABUTRON_NATIVE_PROTECTED_AUDIT_V1',K,NONCE,LOGIN,'Deriv-Demo',
      'Volatility 75 Index.0','BUY','200','201','300','0.02500000',
      '100.2',str(BASE*1000+600),'100.2','99.1','102.1',
      str(BASE*1000+100),str(BASE*1000+700),
      '-0.14','0.0','0.0',str(BASE+2),'OPEN_PROTECTED']
    client=['ABUTRON_NATIVE_CLIENT_CONTEXT_V1',K,NONCE,LOGIN,'Deriv-Demo',
      'Volatility 75 Index.0','BUY',str(BASE*1_000_000_000-250_000_000),'500']
    files={'.client.txt':client,'.request.txt':request,'.result.txt':result,'.protected.txt':protected}
    for suffix,rows in files.items():
        (root/(K+suffix)).write_text('\n'.join(rows)+'\n')
    return {suffix:root/(K+suffix) for suffix in files}

class NativeAuditTests(unittest.TestCase):
 def test_complete_simulated_contract_accepts_only_matching_ids_and_protection(self):
    with tempfile.TemporaryDirectory() as d:
      r=a.validate_capture(bundle(d),NONCE,LOGIN)
      self.assertTrue(r.get('position_protected'),r)
      self.assertGreater(r['adverse_slippage_bps'],0)
 def test_missing_client_creation_fails_closed(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);p['.client.txt'].unlink()
      self.assertIn('rejected_reason',a.validate_capture(p,NONCE,LOGIN))
 def test_identity_mismatch_rejected(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);r=a.validate_capture(p,NONCE,'00006207')
      self.assertIn('NATIVE_ACCOUNT_NONCE_MISMATCH',r['rejected_reason'])
 def test_missing_original_price_rejected(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);f=p['.request.txt'];s=f.read_text().splitlines();s[8]='0.0';f.write_text('\n'.join(s)+'\n')
      self.assertIn('BROKER_PRICE_INVALID',a.validate_capture(p,NONCE,LOGIN)['rejected_reason'])
 def test_mismatched_deal_rejected(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);f=p['.protected.txt'];s=f.read_text().splitlines();s[8]='401';f.write_text('\n'.join(s)+'\n')
      self.assertIn('BROKER_ORDER_DEAL_MISMATCH',a.validate_capture(p,NONCE,LOGIN)['rejected_reason'])
 def test_unprotected_position_rejected(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);f=p['.protected.txt'];s=f.read_text().splitlines();s[-1]='NOT_YET_VISIBLE';f.write_text('\n'.join(s)+'\n')
      self.assertIn('NO_AUTHENTICATED_OPEN_PROTECTED_POSITION',a.validate_capture(p,NONCE,LOGIN)['rejected_reason'])
 def test_broker_stop_geometry_rejected(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);f=p['.protected.txt'];s=f.read_text().splitlines();s[14]='103';f.write_text('\n'.join(s)+'\n')
      self.assertIn('BROKER_PROTECTION_GEOMETRY_INVALID',a.validate_capture(p,NONCE,LOGIN)['rejected_reason'])
 def test_utc_broker_timings_rejected(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);f=p['.result.txt'];s=f.read_text().splitlines();s[7]=str(BASE-1);f.write_text('\n'.join(s)+'\n')
      self.assertIn('INCONSISTENT_CAUSAL_TIMING',a.validate_capture(p,NONCE,LOGIN)['rejected_reason'])
 def test_synthetic_quote_samples_labeled_as_samples(self):
    with tempfile.TemporaryDirectory() as d:
      f=Path(d)/'broker-spread-20261107.tsv'
      f.write_text(str(BASE)+'\t123\tVolatility 25 Index.0\t'+str(BASE*1000)+'\t100.0\t100.2\t19.98001998\r\n')
      r,n=a.quote_summary(Path(d))
      self.assertEqual(n,1);self.assertEqual(r['Volatility 25 Index.0']['quote_samples'],1)
 def test_no_fake_slippage_from_no_proof(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);p['.protected.txt'].unlink()
      self.assertFalse(a.validate_capture(p,NONCE,LOGIN).get('position_protected',False))
 def test_bad_header_fails(self):
    with tempfile.TemporaryDirectory() as d:
      p=bundle(d);f=p['.client.txt'];f.write_text(f.read_text().replace('ABUTRON_NATIVE_CLIENT_CONTEXT_V1','BAD'))
      self.assertIn('NATIVE_FORMAT',a.validate_capture(p,NONCE,LOGIN)['rejected_reason'])
if __name__=='__main__':unittest.main()
