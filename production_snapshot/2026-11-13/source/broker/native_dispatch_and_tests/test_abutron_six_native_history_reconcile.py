#!/usr/bin/python3
"""ABUTRON selected-window broker ledger negative tests (no broker interaction)."""
import runpy
import unittest
from decimal import Decimal

SOURCE="/var/lib/abutron-mcp/abutron-six-broker-native-history-reconcile.py"
m=runpy.run_path(SOURCE,run_name="_six_broker_test")

def deal(ticket,position,entry,volume,kind="0"):
    return {"ticket":str(ticket),"position_id":str(position),"type":kind,
            "entry":str(entry),"volume":str(volume)}

class LedgerTests(unittest.TestCase):
    def pairs(self,rows):
        return m["trade_pairs"](rows,position_key="position_id",type_key="type",
                                entry_key="entry",volume_key="volume")
    def test_matched_entry_exit(self):
        self.assertEqual(self.pairs([deal(1,12,0,"0.30"),deal(2,12,1,"0.30")]),(2,1))
    def test_partial_exit_reconciliation(self):
        self.assertEqual(self.pairs([deal(1,12,0,"0.30"),deal(2,12,1,"0.15"),
                                     deal(3,12,1,"0.15")]),(3,1))
    def test_unmatched_position_rejected(self):
        with self.assertRaisesRegex(ValueError,"VOLUME_MISMATCH"):
            self.pairs([deal(1,12,0,"0.30"),deal(2,12,1,"0.20")])
    def test_duplicate_broker_ticket_rejected(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            self.pairs([deal(1,12,0,"0.30"),deal(1,12,1,"0.30")])
    def test_unrecognized_entry_rejected(self):
        with self.assertRaisesRegex(ValueError,"UNSUPPORTED"):
            self.pairs([deal(1,12,2,"0.30")])
    def test_broker_cashflow_deposit_excluded_from_trade_counts(self):
        self.assertEqual(self.pairs([deal(5,0,0,"0",kind="2")]),(0,0))
    def test_nonfinite_currency_rejected(self):
        for s in ("NaN","Infinity","not-a-number"):
            with self.assertRaises(ValueError):
                m["decimal"](s)
    def test_live_historical_is_never_certified(self):
        report=m["inspect"]()
        live=[x for x in report["accounts"] if x["environment"]=="LIVE"]
        self.assertEqual(len(live),1)
        self.assertFalse(live[0]["all_time_history_complete"])
        self.assertFalse(report["all_six_all_time_history_certified"])
        self.assertFalse(report["trading_authorized_by_audit"])
        self.assertFalse(report["new_broker_execution_ack_certified"])

if __name__=="__main__":
    unittest.main(verbosity=2)
