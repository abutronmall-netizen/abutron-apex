import datetime as dt
import importlib.util
import unittest
from pathlib import Path
p=Path(__file__).with_name('fp_execution_preflight.py')
spec=importlib.util.spec_from_file_location('fp_execution_preflight',p)
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
NOW=1793817600.0
TS=dt.datetime.fromtimestamp(NOW,dt.timezone.utc).isoformat()

def fixture():
 c={'broker':'FP Markets','environment':'DEMO','server':'FPMarketsSC-Demo','connected':True,'desired':False,'effective':False}
 feed={'broker':'FP Markets','native_feeds_complete':1,'execution_enabled':False,'orders_submitted':0,'checked_at_utc':TS}
 signals=[{'symbol':'XAUUSD','proposal':'BUY','m5_closed_bar':1793817300,'smc':{'status':'PASS'},'ict':{'status':'PASS'}}]
 scanner={'schema':'abutron.fpmarkets.apex.scanner.readonly.v1','symbols':13,'orders_enabled':False,'checked_at_utc':TS,'instruments':signals}
 review={'symbol':'XAUUSD','m5_closed_bar':1793817300,'scanner_proposal':'BUY','llm_direction':'BUY','evidence_status':'MODEL_REVIEW_COMPLETED','reviewed_at_utc':TS}
 ai={'schema':'abutron.fpmarkets.apex.ai_smc_ict.readonly.v1','status':'FP_AI_RESEARCH_ONLY','orders_enabled':False,'reviewed_at_utc':TS,'reviews':[review]}
 history={'available':True,'history_verified_from_mt5':True,'broker':'FP Markets','environment':'DEMO','generated_at_utc':TS,'positions':[],'pending_orders':[],'equity_usd':1000.0}
 bridge={'broker':'FP Markets','mode':'DEMO','account_bound':True,'pending_orders':0,'native_demo_orders_enabled':True,'protocol_version':3,'usd_policy':(50,100),'compiled_sha256_verified':True,'broker_ordercheck_verified':True}
 return c,feed,scanner,ai,history,bridge

class TestFailClosedFPPreflight(unittest.TestCase):
 def run_case(self,*values):return f.evidence_decision(*values,NOW)
 def test_even_all_positive_no_unwired_execution(self):
  c,feed,s,a,h,b=fixture();c.update(desired=True,effective=True)
  d=self.run_case(c,feed,s,a,h,b)
  self.assertEqual(d['status'],'BLOCKED');self.assertFalse(d['orders_enabled'])
  self.assertEqual(d['trade_attempts'],0)
  self.assertIn('FP_BROKER_NATIVE_ORDER_ROUTER_NOT_CONNECTED',d['blockers'])
  self.assertIn('FP_BROKER_RECONCILIATION_LEDGER_NOT_CONNECTED',d['blockers'])
 def test_account_switch_off_blocks(self):
  d=self.run_case(*fixture());self.assertIn('FP_ACCOUNT_AUTOTRADING_OFF',d['blockers'])
 def test_wrong_broker_or_live_blocks(self):
  values=list(fixture());values[0]['environment']='LIVE';self.assertIn('FP_DEMO_ACCOUNT_NOT_ATTESTED',self.run_case(*values)['blockers'])
 def test_stale_feed_blocks(self):
  values=list(fixture());values[1]['checked_at_utc']='2026-10-01T00:00:00+00:00'
  self.assertIn('FP_NATIVE_MARKET_FEED_UNAVAILABLE',self.run_case(*values)['blockers'])
 def test_no_three_way_match_blocks(self):
  values=list(fixture());values[3]['reviews'][0]['llm_direction']='SELL'
  self.assertIn('NO_QWEN_SMC_ICT_THREE_WAY_MATCH',self.run_case(*values)['blockers'])
 def test_candle_mismatch_blocks(self):
  values=list(fixture());values[3]['reviews'][0]['m5_closed_bar']-=300
  self.assertIn('NO_QWEN_SMC_ICT_THREE_WAY_MATCH',self.run_case(*values)['blockers'])
 def test_smc_veto_blocks(self):
  values=list(fixture());values[2]['instruments'][0]['smc']['status']='VETO'
  self.assertIn('NO_FRESH_SMC_AND_ICT_CONFIRMED_FP_SIGNAL',self.run_case(*values)['blockers'])
 def test_native_history_missing_blocks(self):
  values=list(fixture());values[4]={}
  self.assertIn('FP_BROKER_NATIVE_POSITIONS_ORDERS_DEALS_PROOF_MISSING',self.run_case(*values)['blockers'])
 def test_pending_orders_blocks(self):
  values=list(fixture());values[4]['pending_orders']=[{'ticket':'1'}]
  self.assertIn('FP_PENDING_BROKER_ORDERS',self.run_case(*values)['blockers'])
 def test_unprotected_open_position_blocks(self):
  values=list(fixture());values[4]['positions']=[{'ticket':'1','stop_loss':None,'take_profit':None}]
  self.assertIn('FP_POSITION_PROTECTION_UNVERIFIED',self.run_case(*values)['blockers'])
 def test_low_equity_blocks(self):
  values=list(fixture());values[4]['equity_usd']=30
  self.assertIn('FP_20_PERCENT_EQUITY_CEILING_NOT_VERIFIED',self.run_case(*values)['blockers'])
 def test_native_ea_missing_blocks(self):
  values=list(fixture());values[5]['compiled_sha256_verified']=False
  self.assertIn('FP_NATIVE_ORDER_EA_AND_BROKER_ORDERCHECK_UNVERIFIED',self.run_case(*values)['blockers'])
 def test_no_side_effect_reporting(self):
  result=f.inspect();self.assertIs(result['orders_enabled'],False)
  self.assertEqual(result['trade_attempts'],0)
  self.assertEqual(result['status'],'BLOCKED')

if __name__=='__main__': unittest.main(verbosity=2)
