#!/usr/bin/env python3
"""No-broker, deterministic regression tests for read-only prospective research."""
import datetime as dt
import unittest
import abutron_prospective_v25_v50_v75_v1 as research
import abutron_prospective_execution_audit_contract_v1 as audit

def synthetic(i,day="2026-11-06"):
 return {"entry":1800000000+i*3600,"observed_day":day,
         "net_0bps":12.,"net_1bps":11.,"net_5bps":7.,"net_10bps":2.}

def full_audit_event():
 return dict(signal_key="a"*64,broker="Deriv",environment="DEMO",account_suffix="6207",
             symbol="Volatility 75 Index.0",side="BUY",
             client_request_created_at_utc="2026-11-06T22:00:00.001Z",
             mt5_order_send_called_at_utc="2026-11-06T22:00:00.100Z",
             broker_ack_recorded_at_utc="2026-11-06T22:00:00.701Z",
             broker_protection_verified_at_utc="2026-11-06T22:00:00.901Z",
             raw_mql5_request_price=100.1,execution_mode="REQUEST_PRICE",
             send_quote_bid=100.0,send_quote_ask=100.1,send_quote_time_msc=1794002400100,
             mt5_request_id=123,broker_retcode=10009,broker_order_ticket=124,
             broker_deal_ticket=125,broker_fill_price=100.2,broker_fill_time_msc=1794002400701,
             broker_position_id=126,broker_sl_price=98.9,broker_tp_price=102.3,
             broker_protection_source="BROKER_POSITION_REQUERY",
             broker_position_status="OPEN_PROTECTED")

class ResearchTests(unittest.TestCase):
 def test_reject_overlapping_hypothetical_positions(self):
  rows=[synthetic(0),synthetic(0),synthetic(1)]
  rows[1]["entry"]+=300
  self.assertEqual(len(research.select_nonoverlap(rows)),2)
 def test_small_positive_sample_is_never_sufficient(self):
  rows=[synthetic(i) for i in range(25)]
  self.assertFalse(research.summarize(rows)["hypothetical_5_and_10bps_stress_pass"])
 def test_drawdown_tracks_peak_to_trough(self):
  self.assertEqual(research.max_dd([1,-2,-3,4]),5)
 def test_noncausal_time_rejected(self):
  with self.assertRaises(ValueError):research.iso("2026-11-06T22:00:00")
 def test_no_day_bootstrap_if_one_day(self):
  self.assertIsNone(research.ci_day_block([synthetic(1)],"net_10bps"))
 def test_positive_synthetic_not_order_authority(self):
  rows=[synthetic(i,day=(dt.date(2026,11,1)+dt.timedelta(days=i//20)).isoformat()) for i in range(280)]
  self.assertTrue(research.summarize(rows)["hypothetical_5_and_10bps_stress_pass"])
  self.assertFalse(audit.validate_event(full_audit_event()))
 def test_reject_missing_original_request_price(self):
  e=full_audit_event();e.pop("raw_mql5_request_price")
  self.assertIn("MISSING_FIELDS",audit.validate_event(e)[0])
 def test_reject_wrong_account(self):
  e=full_audit_event();e["account_suffix"]="7593"
  self.assertIn("OTHER_ACCOUNT_OR_LIVE_DENIED",audit.validate_event(e))
 def test_reject_unprotected_sl_tp(self):
  e=full_audit_event();e["broker_sl_price"]=105
  self.assertIn("BROKER_STOP_GEOMETRY_INVALID",audit.validate_event(e))
 def test_reject_fake_protection_source(self):
  e=full_audit_event();e["broker_protection_source"]="SIMULATED"
  self.assertIn("NO_INDEPENDENT_BROKER_POSITION_PROTECTION",audit.validate_event(e))
 def test_reject_incomplete_broker_ack(self):
  e=full_audit_event();e["broker_deal_ticket"]=0
  self.assertIn("INVALID_ID:broker_deal_ticket",audit.validate_event(e))
 def test_zero_request_price_needs_market_mode(self):
  e=full_audit_event();e["raw_mql5_request_price"]=0
  self.assertIn("ZERO_REQUEST_PRICE_NOT_EXPLAINED",audit.validate_event(e))
if __name__=="__main__":unittest.main()
