"""APEX 1.1.0 candidate -> ABUTRON dual-layer DEMO risk reservation.

NO ORDER-SENDING: no MT5 transport, authorization, dispatch, or switch writes.
The caller must verify authenticated broker provenance, durable equity snapshots,
account-revision fencing and exclusive writer ownership before using this.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from abutron_replacement.candidate_contract import AccountGate, BrokerNativeRisk, review_candidate
from risk_guard.abutron_risk_guard import CustomerRisk, Proposal, D
from risk_guard.reservation_store import ReservationStore


@dataclass(frozen=True)
class NativePreflightResult:
    risk_reserved: bool
    reason: str
    signal_id: str | None = None
    reserved_volume: Decimal = D('0')
    # This is *not* broker order authorization. Only the authenticated
    # existing native MT5 writer may decide to submit, after fresh rechecks.
    broker_order_authorized: bool = False


def reserve_apex11_demo_candidate(
    *,
    signal: Mapping[str, Any],
    gate: AccountGate,
    native: BrokerNativeRisk,
    customer: CustomerRisk,
    proposal: Proposal,
    store: ReservationStore,
    now: datetime,
) -> NativePreflightResult:
    """Use existing candidate identity and strict 0.10/2/3/20 guard together.

    Existing candidate's 20% *nominal open-risk* check is deliberately not the
    admission authority; actual aggregate open-stop risk must pass the stricter
    2% account AND customer cap in the persisted ReservationStore. The 20%
    policy is now a separate persistent peak-to-equity drawdown lockout.

    This is a reservation boundary, NOT a side-effecting broker order writer.
    Do not interpret risk_reserved=True as an MT5 execution receipt.
    """
    def block(reason: str) -> NativePreflightResult:
        return NativePreflightResult(False, reason)

    if now.tzinfo is None or now.utcoffset() is None:
        return block('UTC_CLOCK_NOT_VERIFIED')
    if customer.customer_id != gate.owner or proposal.customer_id != gate.owner:
        return block('CUSTOMER_OWNER_MISMATCH')
    if proposal.account_id != gate.connection_id or proposal.environment != gate.environment:
        return block('NATIVE_ACCOUNT_IDENTITY_MISMATCH')
    if proposal.symbol != signal.get('symbol') or proposal.order_side != signal.get('status'):
        return block('APEX_SIGNAL_RISK_PROPOSAL_MISMATCH')
    if proposal.environment != 'DEMO':
        return block('LIVE_NOT_SUPPORTED')

    reviewed = review_candidate(signal=signal, gate=gate, native=native, now=int(now.timestamp()))
    if not reviewed.get('engineering_gates_passed') or not reviewed.get('order_candidate'):
        blockers = reviewed.get('blockers') or ['CANDIDATE_NOT_ELIGIBLE']
        return block('APEX_CANDIDATE_BLOCKED:' + ','.join(str(x) for x in blockers))
    expected_id = reviewed.get('signal_id_for_separate_ledger')
    if not expected_id or proposal.signal_id != expected_id:
        return block('SIGNAL_LEDGER_KEY_MISMATCH')

    target_account = [a for a in customer.accounts if a.account_id == gate.connection_id]
    if len(target_account) != 1:
        return block('ACCOUNT_NOT_FOUND_IN_CUSTOMER_SNAPSHOT')
    a = target_account[0]
    try:
        eq_usd = D(a.equity_ccy) * D(a.usd_per_ccy)
        existing_usd = D(a.open_stop_risk_ccy) * D(a.usd_per_ccy)
        if abs(eq_usd - D(str(gate.account_equity_usd))) > D('0.01'):
            return block('EQUITY_SNAPSHOT_RECONCILIATION_MISMATCH')
        if abs(existing_usd - D(str(gate.current_verified_stop_risk_usd))) > D('0.01'):
            return block('OPEN_RISK_SNAPSHOT_RECONCILIATION_MISMATCH')

        # Native risk must be based on OrderCalcProfit for the stop and must
        # not understate the independent native tick-value stress estimate.
        native_ticks = D(str(abs(native.price - native.stop_price))) / D(str(native.tick_size))
        native_estimate_usd = (native_ticks + D(native.slippage_budget_ticks)) * D(str(native.tick_value_per_lot_usd))
        proposed_usd = (D(proposal.one_lot_stop_risk_ccy)
                        + D(proposal.one_lot_roundtrip_cost_ccy)
                        + D(proposal.one_lot_slippage_buffer_ccy)) * D(a.usd_per_ccy)
        if proposed_usd + D('0.000001') < native_estimate_usd:
            return block('RISK_QUOTE_BELOW_NATIVE_STRESS_ESTIMATE')
        if (D(proposal.volume_min) != D(str(native.min_lot)) or
            D(proposal.volume_step) != D(str(native.lot_step)) or
            D(proposal.volume_max) > D(str(native.max_lot))):
            return block('BROKER_VOLUME_CONTRACT_MISMATCH')
    except (ValueError, ArithmeticError, TypeError):
        return block('INVALID_NATIVE_RISK_SNAPSHOT')

    result = store.reserve(customer, proposal, now=now)
    if not result.allowed:
        return block('RISK_GUARD:' + result.reason)
    # The stored intent remains reserved until real native MT5 ACK and
    # independently reconciled broker position/SL/TP evidence arrive.
    return NativePreflightResult(True, 'DEMO_RISK_RESERVED_NOT_SUBMITTED',
                                 signal_id=expected_id, reserved_volume=result.volume)