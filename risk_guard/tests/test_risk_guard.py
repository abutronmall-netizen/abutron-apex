import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from abutron_risk_guard import Account, CustomerRisk, Proposal, D, evaluate
from reservation_store import ReservationStore

NOW = datetime(2026, 11, 8, 2, 20, tzinfo=timezone.utc)


def fixture():
    a = Account(
        account_id="deriv-6207", customer_id="customer-a", environment="DEMO",
        equity_ccy=D("10000"), usd_per_ccy=D("1"),
        day_start_equity_ccy=D("10000"), peak_equity_ccy=D("10000"),
        open_stop_risk_ccy=D("0"), broker_asof=NOW)
    customer = CustomerRisk(customer_id="customer-a", accounts=(a,),
                            day_start_equity_usd=D("10000"), peak_equity_usd=D("10000"))
    p = Proposal(customer_id="customer-a", account_id="deriv-6207",
                 symbol="Volatility 75 Index", environment="DEMO", order_side="BUY",
                 one_lot_stop_risk_ccy=D("20"), one_lot_roundtrip_cost_ccy=D("0"),
                 one_lot_slippage_buffer_ccy=D("0"), volume_min=D("0.01"),
                 volume_max=D("2"), volume_step=D("0.01"), native_stop_validated=True,
                 contract_spec_verified=True, signal_fresh=True, signal_id="sig-1")
    return customer, p


class RiskTests(unittest.TestCase):
    def decide(self, customer=None, p=None, **kwargs):
        c0, p0 = fixture()
        return evaluate(customer or c0, p or p0, now=NOW, **kwargs)

    def test_default_volume_is_0_50_and_max_10_usd(self):
        d = self.decide()
        self.assertTrue(d.allowed)
        self.assertEqual(d.volume, D("0.50"))
        self.assertEqual(d.max_loss_ccy, D("10"))

    def test_round_down_volume_to_broker_step(self):
        c, p = fixture()
        p = replace(p, one_lot_stop_risk_ccy=D("18"), volume_step=D("0.07"))
        d = self.decide(c, p)
        self.assertTrue(d.allowed)
        self.assertEqual(d.volume, D("0.50"))  # .01 + 7*.07
        self.assertLessEqual(d.max_loss_ccy, D("10"))

    def test_never_increase_minimum_lot_to_fit(self):
        c, p = fixture()
        p = replace(p, volume_min=D("0.6"))
        self.assertEqual(self.decide(c, p).reason, "MINIMUM_LOT_EXCEEDS_RISK_BUDGET")

    def test_2_pct_account_exposure_limit(self):
        c, p = fixture()
        a = replace(c.accounts[0], open_stop_risk_ccy=D("197"))
        c = replace(c, accounts=(a,))
        d = self.decide(c, p)
        self.assertTrue(d.allowed)
        self.assertEqual(d.max_loss_ccy, D("3"))
        self.assertEqual(d.volume, D("0.15"))

    def test_2_pct_account_exposure_reject(self):
        c, p = fixture()
        a = replace(c.accounts[0], open_stop_risk_ccy=D("200"))
        self.assertEqual(self.decide(replace(c, accounts=(a,)), p).reason, "OPEN_RISK_CAP_REACHED")

    def test_2_pct_customer_exposure_includes_second_broker(self):
        c, p = fixture()
        b = replace(c.accounts[0], account_id="fp-0512", equity_ccy=D("10000"),
            peak_equity_ccy=D("10000"), day_start_equity_ccy=D("10000"),
            open_stop_risk_ccy=D("395"))
        c = replace(c, accounts=(c.accounts[0], b), day_start_equity_usd=D("20000"),
                    peak_equity_usd=D("20000"))
        d = self.decide(c, p)
        self.assertTrue(d.allowed)
        self.assertEqual(d.max_loss_ccy, D("5"))

    def test_2_pct_customer_exposure_reject(self):
        c, p = fixture()
        b = replace(c.accounts[0], account_id="fp-0512", open_stop_risk_ccy=D("400"))
        c = replace(c, accounts=(c.accounts[0], b), day_start_equity_usd=D("20000"),
                    peak_equity_usd=D("20000"))
        self.assertEqual(self.decide(c, p).reason, "OPEN_RISK_CAP_REACHED")

    def test_daily_3_pct_account_stop_latches(self):
        c, p = fixture()
        a = replace(c.accounts[0], equity_ccy=D("9700"))
        d = self.decide(replace(c, accounts=(a,)), p)
        self.assertFalse(d.allowed)
        self.assertTrue(d.latch_daily_loss)

    def test_daily_3_pct_customer_stop(self):
        c, p = fixture()
        c = replace(c, day_start_equity_usd=D("10500"))
        d = self.decide(c, p)
        self.assertEqual(d.reason, "CUSTOMER_DAILY_LOSS_THRESHOLD")
        self.assertTrue(d.latch_daily_loss)

    def test_20_pct_account_drawdown_lock(self):
        c, p = fixture()
        a = replace(c.accounts[0], peak_equity_ccy=D("12500"))
        d = self.decide(replace(c, accounts=(a,)), p)
        self.assertEqual(d.reason, "ACCOUNT_MAX_DRAWDOWN_THRESHOLD")
        self.assertTrue(d.latch_drawdown)

    def test_20_pct_customer_drawdown_lock(self):
        c, p = fixture()
        d = self.decide(replace(c, peak_equity_usd=D("12500")), p)
        self.assertEqual(d.reason, "CUSTOMER_MAX_DRAWDOWN_THRESHOLD")
        self.assertTrue(d.latch_drawdown)

    def test_daily_lock_does_not_auto_reset_when_equity_recovers(self):
        c, p = fixture()
        self.assertEqual(self.decide(replace(c, daily_lock_latched=True), p).reason,
                         "PERSISTENT_DAILY_LOSS_LOCK")

    def test_drawdown_lock_does_not_auto_reset_when_equity_recovers(self):
        c, p = fixture()
        self.assertEqual(self.decide(replace(c, drawdown_lock_latched=True), p).reason,
                         "PERSISTENT_MAX_DRAWDOWN_LOCK")

    def test_client_off_prevents_order(self):
        c, p = fixture()
        self.assertEqual(self.decide(replace(c, accounts=(replace(c.accounts[0], effective_on=False),)), p).reason,
                         "ACCOUNT_OFF_OR_NOT_AUTHORIZED")

    def test_kill_switch_prevents_order(self):
        c, p = fixture()
        self.assertEqual(self.decide(replace(c, accounts=(replace(c.accounts[0], kill_switch=True),)), p).reason,
                         "KILL_SWITCH_ACTIVE")

    def test_live_orders_are_rejected(self):
        c, p = fixture()
        self.assertEqual(self.decide(c, replace(p, environment="LIVE")).reason, "DEMO_BUY_SELL_ONLY")

    def test_live_accounts_are_rejected(self):
        c, p = fixture()
        self.assertEqual(self.decide(replace(c, accounts=(replace(c.accounts[0], environment="LIVE"),)), p).reason,
                         "LIVE_ACCOUNT_NOT_AUTHORIZED")

    def test_stale_broker_blocks(self):
        c, p = fixture()
        a = replace(c.accounts[0], broker_asof=NOW - timedelta(seconds=21))
        self.assertEqual(self.decide(replace(c, accounts=(a,)), p).reason, "STALE_OR_FUTURE_BROKER_DATA")

    def test_unprotected_position_blocks(self):
        c, p = fixture()
        a = replace(c.accounts[0], native_stops_verified=False)
        self.assertEqual(self.decide(replace(c, accounts=(a,)), p).reason, "BROKER_POSITIONS_OR_STOPS_UNVERIFIED")

    def test_missing_broker_inventory_blocks(self):
        c, p = fixture()
        self.assertEqual(self.decide(replace(c, account_inventory_complete=False), p).reason,
                         "INCOMPLETE_CUSTOMER_INVENTORY_OR_EXPOSURE")

    def test_missing_equity_baseline_blocks(self):
        c, p = fixture()
        self.assertEqual(self.decide(replace(c, day_start_equity_usd=D("0")), p).reason,
                         "NO_DURABLE_CUSTOMER_EQUITY_BASELINE")

    def test_owner_mismatch_blocks(self):
        c, p = fixture()
        self.assertEqual(self.decide(c, replace(p, customer_id="different-customer")).reason,
                         "CUSTOMER_ID_MISMATCH")

    def test_unverified_stop_blocks(self):
        c, p = fixture()
        self.assertEqual(self.decide(c, replace(p, native_stop_validated=False)).reason,
                         "STOP_CONTRACT_OR_SIGNAL_UNVERIFIED")

    def test_cost_and_slippage_count_toward_0_1_percent(self):
        c, p = fixture()
        p = replace(p, one_lot_roundtrip_cost_ccy=D("2"), one_lot_slippage_buffer_ccy=D("3"))
        d = self.decide(c, p)
        self.assertTrue(d.allowed)
        self.assertEqual(d.volume, D("0.40"))
        self.assertEqual(d.max_loss_ccy, D("10"))

    def test_pending_exposure_counted(self):
        d = self.decide(pending_customer_risk_usd=D("198"), pending_account_risk_ccy=D("198"))
        self.assertTrue(d.allowed)
        self.assertEqual(d.volume, D("0.10"))

    def test_high_pending_exposure_blocks(self):
        self.assertEqual(self.decide(pending_customer_risk_usd=D("200"),
                         pending_account_risk_ccy=D("200")).reason, "OPEN_RISK_CAP_REACHED")

    def test_binary_float_rejected(self):
        with self.assertRaises(ValueError):
            D(0.1)

    def test_duplicate_account_in_snapshot(self):
        c, p = fixture()
        c = replace(c, accounts=(c.accounts[0], c.accounts[0]))
        self.assertEqual(self.decide(c, p).reason, "DUPLICATE_ACCOUNT_IN_SNAPSHOT")

    def test_unauthorized_connected_account_blocks(self):
        c, p = fixture()
        c = replace(c, accounts=(replace(c.accounts[0], entitlement_ok=False),))
        self.assertEqual(self.decide(c, p).reason, "ACCOUNT_OFF_OR_NOT_AUTHORIZED")

    def test_missing_other_account_feed_blocks(self):
        c, p = fixture()
        b = replace(c.accounts[0], account_id="fp-0512", connected=False)
        c = replace(c, accounts=(c.accounts[0], b), day_start_equity_usd=D("20000"),
                    peak_equity_usd=D("20000"))
        self.assertEqual(self.decide(c, p).reason, "OTHER_ACCOUNT_BROKER_DISCONNECTED")


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'risk-reservations.db'
        self.store = ReservationStore(self.db)
        self.customer, self.proposal = fixture()

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_signal_rejected_after_restart(self):
        first = self.store.reserve(self.customer, self.proposal, now=NOW)
        self.assertTrue(first.allowed)
        fresh_store = ReservationStore(self.db)
        second = fresh_store.reserve(self.customer, self.proposal, now=NOW)
        self.assertEqual(second.reason, "SIGNAL_ALREADY_RESERVED_OR_PROCESSED")

    def test_pending_order_reduces_next_order_budget(self):
        first = self.store.reserve(self.customer, self.proposal, now=NOW)
        self.assertTrue(first.allowed)
        second = self.store.reserve(self.customer, replace(self.proposal, signal_id="sig-2"), now=NOW)
        self.assertTrue(second.allowed)
        self.assertEqual(first.max_loss_ccy, D("10"))
        self.assertEqual(second.max_loss_ccy, D("10"))

    def test_many_pending_reservations_reach_2pct_cap(self):
        for n in range(20):
            result = self.store.reserve(self.customer, replace(self.proposal, signal_id=f"sig-{n}"), now=NOW)
            self.assertTrue(result.allowed, result.reason)
        last = self.store.reserve(self.customer, replace(self.proposal, signal_id="sig-last"), now=NOW)
        self.assertEqual(last.reason, "OPEN_RISK_CAP_REACHED")

    def test_unknown_intent_stays_reserved(self):
        self.assertTrue(self.store.reserve(self.customer, self.proposal, now=NOW).allowed)
        self.store.mark_unknown(self.proposal.account_id, self.proposal.signal_id)
        self.assertEqual(self.store.reserve(self.customer, self.proposal, now=NOW).reason,
                         "SIGNAL_ALREADY_RESERVED_OR_PROCESSED")

    def test_release_requires_verified_terminal_outcome(self):
        self.assertTrue(self.store.reserve(self.customer, self.proposal, now=NOW).allowed)
        with self.assertRaises(ValueError):
            self.store.complete(self.proposal.account_id, self.proposal.signal_id, outcome="REJECTED", broker_proof="", now=NOW)
        self.store.complete(self.proposal.account_id, self.proposal.signal_id, outcome="REJECTED",
                            broker_proof="verified-native-mt5-reject-id", now=NOW)
        with self.assertRaises(ValueError):
            self.store.complete(self.proposal.account_id, self.proposal.signal_id, outcome="REJECTED",
                                broker_proof="duplicate", now=NOW)
        self.assertEqual(self.store.reserve(self.customer, self.proposal, now=NOW).reason,
                         "SIGNAL_ALREADY_RESERVED_OR_PROCESSED")

    def test_same_signal_id_with_modified_parameters_blocks(self):
        self.assertTrue(self.store.reserve(self.customer, self.proposal, now=NOW).allowed)
        modified = replace(self.proposal, one_lot_stop_risk_ccy=D("19"))
        self.assertEqual(self.store.reserve(self.customer, modified, now=NOW).reason,
                         "SIGNAL_ID_COLLISION")


if __name__ == '__main__':
    unittest.main()

class IndependenceTests(unittest.TestCase):
    def test_other_account_off_and_kill_switch_do_not_revoke_this_account(self):
        c, p = fixture()
        b = replace(c.accounts[0], account_id="fp-0512", effective_on=False, kill_switch=True)
        c = replace(c, accounts=(c.accounts[0], b), day_start_equity_usd=D("20000"),
                    peak_equity_usd=D("20000"))
        self.assertTrue(evaluate(c, p, now=NOW).allowed)

    def test_other_account_daily_loss_does_not_lock_healthy_account(self):
        c, p = fixture()
        b = replace(c.accounts[0], account_id="fp-0512", equity_ccy=D("9600"),
                    daily_lock_latched=True)
        c = replace(c, accounts=(c.accounts[0], b), day_start_equity_usd=D("20000"),
                    peak_equity_usd=D("20000"))
        self.assertTrue(evaluate(c, p, now=NOW).allowed)

    def test_latched_account_does_not_resume_after_rebound(self):
        c, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "locks.db")
            loss_account = replace(c.accounts[0], equity_ccy=D("9700"))
            r1 = store.reserve(replace(c, accounts=(loss_account,)), p, now=NOW)
            self.assertTrue(r1.latch_daily_loss)
            r2 = ReservationStore(Path(td) / "locks.db").reserve(c, p, now=NOW)
            self.assertEqual(r2.reason, "PERSISTENT_DAILY_LOSS_LOCK")

    def test_customer_drawdown_lock_persists_across_restart(self):
        c, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "locks.db")
            r1 = store.reserve(replace(c, peak_equity_usd=D("12500")), p, now=NOW)
            self.assertTrue(r1.latch_drawdown)
            r2 = ReservationStore(Path(td) / "locks.db").reserve(c, p, now=NOW)
            self.assertEqual(r2.reason, "PERSISTENT_MAX_DRAWDOWN_LOCK")

    def test_reconciled_outcome_requires_exposure_snapshot(self):
        c, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "locks.db")
            self.assertTrue(store.reserve(c, p, now=NOW).allowed)
            with self.assertRaises(ValueError):
                store.complete(p.account_id, p.signal_id, outcome="RECONCILED", broker_proof="MT5ticket101", now=NOW)
            store.complete(p.account_id, p.signal_id, outcome="RECONCILED", broker_proof="MT5ticket101",
                           now=NOW, reconciled_snapshot_includes_position=True)

class MultiAccountIdempotencyTests(unittest.TestCase):
    def test_identical_apex_signal_id_may_reserve_once_for_each_account(self):
        c, p = fixture()
        b = replace(c.accounts[0], account_id="fp-0512")
        c = replace(c, accounts=(c.accounts[0], b), day_start_equity_usd=D("20000"),
                    peak_equity_usd=D("20000"))
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "ledger.sqlite3")
            first = store.reserve(c, p, now=NOW)
            second = store.reserve(c, replace(p, account_id="fp-0512"), now=NOW)
            self.assertTrue(first.allowed)
            self.assertTrue(second.allowed)
            self.assertEqual(store.reserve(c, p, now=NOW).reason,
                             "SIGNAL_ALREADY_RESERVED_OR_PROCESSED")

class ContinuousMonitorTests(unittest.TestCase):
    def test_daily_stop_persists_without_any_trade_signal(self):
        c, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "risk.db")
            a = replace(c.accounts[0], effective_on=False, equity_ccy=D("9650"))
            events = store.observe(replace(c, accounts=(a,)), now=NOW)
            self.assertIn("ACCOUNT_DAILY_LOSS_THRESHOLD", events)
            # Now account recovers and switches on; earlier threshold stays locked.
            self.assertEqual(store.reserve(c, p, now=NOW).reason, "PERSISTENT_DAILY_LOSS_LOCK")

    def test_portfolio_drawdown_observer_persists(self):
        c, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "risk.db")
            c2 = replace(c, peak_equity_usd=D("12500"))
            self.assertIn("CUSTOMER_MAX_DRAWDOWN_THRESHOLD", store.observe(c2, now=NOW))
            self.assertEqual(store.reserve(c, p, now=NOW).reason, "PERSISTENT_MAX_DRAWDOWN_LOCK")

    def test_stale_input_does_not_update_locks(self):
        c, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "risk.db")
            a = replace(c.accounts[0], equity_ccy=D("9600"), broker_asof=NOW-timedelta(hours=1))
            with self.assertRaises(ValueError):
                store.observe(replace(c, accounts=(a,)), now=NOW)

class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_duplicate_reservations_admit_only_one(self):
        from concurrent.futures import ThreadPoolExecutor
        c, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "risk.db")
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: store.reserve(c, p, now=NOW), range(24)))
            self.assertEqual(sum(result.allowed for result in results), 1)
            self.assertEqual(sum(result.reason == "SIGNAL_ALREADY_RESERVED_OR_PROCESSED"
                                 for result in results), 23)

    def test_concurrent_different_signals_never_exceed_customer_budget(self):
        from concurrent.futures import ThreadPoolExecutor
        c, p = fixture()
        with tempfile.TemporaryDirectory() as td:
            store = ReservationStore(Path(td) / "risk.db")
            def claim(n):
                return store.reserve(c, replace(p, signal_id=f"event-{n}"), now=NOW)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(claim, range(40)))
            self.assertEqual(sum(x.reserved_risk_usd for x in results if x.allowed), D("200"))
            self.assertEqual(sum(x.allowed for x in results), 20)
