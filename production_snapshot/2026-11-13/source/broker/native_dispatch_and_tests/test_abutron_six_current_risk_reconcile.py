#!/usr/bin/python3
"""Deterministic negative tests for read-only customer-wide native exposure."""
from __future__ import annotations
import copy
import datetime as dt
import json
import os
import pathlib
import tempfile
import types
import unittest
from unittest.mock import patch

SRC="/var/lib/abutron-mcp/abutron-six-current-exposure-risk-readonly-candidate.py"
mod=types.ModuleType("abutron_six_risk_test")
exec(compile(pathlib.Path(SRC).read_text(),SRC,"exec"),mod.__dict__)

class CurrentRiskTests(unittest.TestCase):
    def test_deriv_demo_zero_exposure_is_supported(self):
        a={"broker":"Deriv","environment":"DEMO","connection_status":"CONNECTED",
           "broker_position_reconciliation_status":"ZERO_EXPOSURE_DUAL_NATIVE_VERIFIED",
           "snapshot":{"positions_count":0,"pending_orders_count":0,
                       "all_current_position_counts_verified":True,
                       "all_current_positions_sl_tp_usd_risk_verified":True,
                       "open_position_usd_stop_risk":0.0}}
        self.assertTrue(mod.verified_current_flat_exposure(a))
        for field in ("positions_count","pending_orders_count"):
            x=copy.deepcopy(a);x["snapshot"][field]=1
            self.assertFalse(mod.verified_current_flat_exposure(x))
        x=copy.deepcopy(a);x["snapshot"]["all_current_position_counts_verified"]=False
        self.assertFalse(mod.verified_current_flat_exposure(x))
        x=copy.deepcopy(a);x["connection_status"]="ERROR"
        self.assertFalse(mod.verified_current_flat_exposure(x))

    def test_fp_zero_requires_independent_native_receipts(self):
        a={"broker":"FP Markets","environment":"DEMO","connection_status":"CONNECTED",
           "broker_position_reconciliation_status":"POSITIONS_COUNT_VERIFIED_READONLY",
           "snapshot":{"positions_count":0,"pending_orders_count":0,
                       "native_receipt_reconciliation_verified":True,
                       "all_position_usd_stop_risk_proved":True}}
        self.assertTrue(mod.verified_current_flat_exposure(a))
        for key in ("native_receipt_reconciliation_verified","all_position_usd_stop_risk_proved"):
            x=copy.deepcopy(a);x["snapshot"][key]=False
            self.assertFalse(mod.verified_current_flat_exposure(x))
        x=copy.deepcopy(a);x["snapshot"]["positions_count"]=6
        self.assertFalse(mod.verified_current_flat_exposure(x))

    def test_live_readonly_zero_does_not_authorize(self):
        a={"broker":"Deriv","environment":"LIVE","connection_status":"CONNECTED",
           "broker_position_reconciliation_status":"SIGNED_LIVE_NO_ORDER_POSITION_COUNTS_VERIFIED",
           "snapshot":{"positions_count":0,"pending_orders_count":0,
                       "positions_count_verified_from_live_broker":True,
                       "account_execution_authorized":False,"broker_trade_allowed":False}}
        self.assertTrue(mod.verified_current_flat_exposure(a))
        x=copy.deepcopy(a);x["snapshot"]["broker_trade_allowed"]=True
        self.assertFalse(mod.verified_current_flat_exposure(x))
        x=copy.deepcopy(a);x["snapshot"]["positions_count"]=1
        self.assertFalse(mod.verified_current_flat_exposure(x))

    def test_no_snapshot_is_not_evidence(self):
        self.assertFalse(mod.verified_current_flat_exposure({"connection_status":"CONNECTED"}))

    def test_fp_receipts_exact_owner_symbol_count_equity(self):
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root)/"dual.json"
            now=dt.datetime.now(dt.timezone.utc)
            doc={"schema":"abutron.fpmarkets.dual_demo_native_reconciliation.readonly.v1",
                 "state":"RECONCILED_READONLY","broker_order_authorized":False,
                 "orders_submitted_by_job":0,"client_switches_modified":False,
                 "at_utc":now.isoformat(),
                 "accounts":[
                    {"connection_suffix":"135e6c","account_suffix":"0512",
                     "state":"RECONCILED_READONLY","connected":True,"effective_on":False,
                     "unresolved_receipts":0,"historical_broker_ack":46,
                     "historical_trade_deals":98,"positions":0,"pending":0,
                     "equity_usd":99023.85},
                    {"connection_suffix":"1c46c6","account_suffix":"1636",
                     "state":"RECONCILED_READONLY","connected":True,"effective_on":False,
                     "unresolved_receipts":0,"historical_broker_ack":0,
                     "historical_trade_deals":0,"positions":0,"pending":0,
                     "equity_usd":100000.00}]}
            with patch.object(mod,"FP_DUAL_RECONCILIATION",path):
                def write():
                    path.write_text(json.dumps(doc));os.chmod(path,0o600)
                write()
                proof=mod.independently_verify_fp_native_receipts(
                    "35b81a287b6a030f2f46ff426b135e6c",
                    "7410512",0,0,99023.85,now.timestamp())
                self.assertEqual(proof["historical_broker_ack_count"],46)
                self.assertIs(proof["current_execution_ack_granted"],False)
                doc["accounts"][0]["unresolved_receipts"]=1;write()
                with self.assertRaises(ValueError):
                    mod.independently_verify_fp_native_receipts(
                        "35b81a287b6a030f2f46ff426b135e6c",
                        "7410512",0,0,99023.85,now.timestamp())
                doc["accounts"][0]["unresolved_receipts"]=0
                doc["accounts"][0]["positions"]=1;write()
                with self.assertRaises(ValueError):
                    mod.independently_verify_fp_native_receipts(
                        "35b81a287b6a030f2f46ff426b135e6c",
                        "7410512",0,0,99023.85,now.timestamp())
                doc["accounts"][0]["positions"]=0
                doc["accounts"][0]["equity_usd"]=0;write()
                with self.assertRaises(ValueError):
                    mod.independently_verify_fp_native_receipts(
                        "35b81a287b6a030f2f46ff426b135e6c",
                        "7410512",0,0,99023.85,now.timestamp())
                doc["accounts"][0]["equity_usd"]=99023.85
                doc["broker_order_authorized"]=True;write()
                with self.assertRaises(ValueError):
                    mod.independently_verify_fp_native_receipts(
                        "35b81a287b6a030f2f46ff426b135e6c",
                        "7410512",0,0,99023.85,now.timestamp())

if __name__=="__main__":
    unittest.main(verbosity=2)
