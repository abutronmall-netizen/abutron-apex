#!/usr/bin/python3
"""Independent fail-closed tests for root-only read-only V4 supervisor."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

P = "/var/lib/abutron-mcp/abutron-v4-broker-crm-supervisor-6207.py"
spec=importlib.util.spec_from_file_location("abutron_v4_supervisor_under_test",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SecureEvidenceTests(unittest.TestCase):
    def test_read_protects_against_symlinks_permissions_and_races(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            data=root/"proof.json"
            data.write_text('{"status":"CONNECTED"}')
            os.chmod(data,0o600)
            self.assertEqual(json.loads(m.stable_file(data)[0])["status"],"CONNECTED")
            sym=root/"linked.json"
            sym.symlink_to(data)
            with self.assertRaises(ValueError):
                m.stable_file(sym)
            os.chmod(data,0o666)
            with self.assertRaises(ValueError):
                m.stable_file(data)

    def test_stale_broker_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/"broker.json"
            file.write_text('{"broker":"Deriv"}')
            os.chmod(file,0o600)
            os.utime(file,(500.0,500.0))
            with self.assertRaises(ValueError):
                m.fresh_json(file,1000.0,30)

    def test_currency_validates_strictly(self):
        self.assertEqual(m.positive("9577.61"),"9577.61")
        for val in ["0","-1","NaN","Infinity","bad"]:
            with self.assertRaises(ValueError):
                m.positive(val)

    def test_report_cannot_grant_order_authority(self):
        actual=m.inspect()
        self.assertTrue(actual["read_only_evidence_only"])
        self.assertFalse(actual["order_authorized"])
        self.assertFalse(actual["production_release_certified"])
        self.assertEqual(actual["orders_submitted"],0)
        self.assertFalse(actual["checks"]["crm_revision_fenced_and_broker_ack"])
        self.assertFalse(actual["checks"]["v4_chart_independently_attached"])
        self.assertFalse(actual["checks"]["customer_cashflow_adjusted_portfolio_risk"])
        self.assertFalse(actual["checks"]["broker_receipts_stops_and_exit_history_reconciled"])

    def test_missing_live_apis_fail_closed(self):
        with patch.object(m,"CRM",Path("/no-such-root-crm.db")):
            r=m.inspect()
        self.assertFalse(r["checks"]["apex_crm_owner_mfa_account_binding"])
        self.assertFalse(r["order_authorized"])

    def test_missing_broker_session_fail_closed(self):
        with patch.object(m,"SIDE",Path("/no-such-broker-evidence")):
            r=m.inspect()
        self.assertFalse(r["checks"]["deriv_independent_readonly_broker_session"])
        self.assertFalse(r["order_authorized"])


if __name__=="__main__":
    unittest.main(verbosity=2)
