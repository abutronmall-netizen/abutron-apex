"""ABUTRON APEX 1.1.0 — isolated DEMO pre-order risk-policy reference module.

This module NEVER submits orders, writes client activation, or changes a trading service.
All equity, exposure, broker instrument facts, native stop validity, permissions,
and high-water/daily baselines must originate in authenticated, reconciled sources.
Order intent persistence and broker receipts remain separate integration requirements.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_FLOOR, InvalidOperation
from typing import Tuple


def D(v: str | int | Decimal) -> Decimal:
    """Reject binary floats; use decimal strings for money and contract volumes."""
    if isinstance(v, float) or isinstance(v, bool):
        raise ValueError("Decimal monetary data must not be a float/bool")
    try:
        result = Decimal(v)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid decimal data") from None
    if not result.is_finite():
        raise ValueError("Nonfinite decimal data")
    return result


@dataclass(frozen=True)
class RiskPolicy:
    per_trade: Decimal = D("0.001")  # 0.10% of account equity
    open_risk: Decimal = D("0.02")  # 2% per account AND per customer portfolio
    daily_loss: Decimal = D("0.03")  # 3% per account AND customer portfolio
    peak_drawdown: Decimal = D("0.20")  # 20% per account AND customer portfolio
    freshness_seconds: int = 20


@dataclass(frozen=True)
class Account:
    account_id: str
    customer_id: str
    environment: str
    equity_ccy: Decimal
    usd_per_ccy: Decimal
    day_start_equity_ccy: Decimal
    peak_equity_ccy: Decimal
    open_stop_risk_ccy: Decimal
    # Above exposure includes ALL positions, including externally opened positions.
    exposure_complete: bool = True
    native_stops_verified: bool = True
    connected: bool = True
    entitlement_ok: bool = True
    effective_on: bool = True
    kill_switch: bool = False
    daily_lock_latched: bool = False
    drawdown_lock_latched: bool = False
    broker_asof: datetime | None = None


@dataclass(frozen=True)
class CustomerRisk:
    customer_id: str
    accounts: Tuple[Account, ...]
    # USD baselines must be durable and sourced from UTC day-boundary snapshots.
    day_start_equity_usd: Decimal
    peak_equity_usd: Decimal
    daily_lock_latched: bool = False
    drawdown_lock_latched: bool = False
    exposure_complete: bool = True
    # All connected accounts of this customer must be represented in accounts.
    account_inventory_complete: bool = True


@dataclass(frozen=True)
class Proposal:
    customer_id: str
    account_id: str
    symbol: str
    environment: str
    order_side: str
    # Broker-verified ABS(negative order_calc_profit(1 lot, entry, SL)) in account CCY.
    one_lot_stop_risk_ccy: Decimal
    # Broker commission + stress buffers per lot in account currency.
    one_lot_roundtrip_cost_ccy: Decimal
    one_lot_slippage_buffer_ccy: Decimal
    volume_min: Decimal
    volume_max: Decimal
    volume_step: Decimal
    native_stop_validated: bool
    contract_spec_verified: bool
    signal_fresh: bool
    signal_id: str


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    volume: Decimal = D("0")
    max_loss_ccy: Decimal = D("0")
    reserved_risk_usd: Decimal = D("0")
    # True means transaction owner MUST persist loss lock before continuing.
    latch_daily_loss: bool = False
    latch_drawdown: bool = False


def _positive(value: Decimal) -> bool:
    return D(value) > 0


def evaluate(
    customer: CustomerRisk,
    proposal: Proposal,
    *,
    now: datetime,
    policy: RiskPolicy = RiskPolicy(),
    pending_customer_risk_usd: Decimal = D("0"),
    pending_account_risk_ccy: Decimal = D("0"),
) -> Decision:
    """Fail-closed pure risk decision. No order execution, DB side effects or unlocks.

    Reservations MUST be serialized atomically across all customer accounts; inputs
    pending_* must include unresolved native order submissions. Unknown broker
    submission state must keep its reservation until reconciled with broker history.
    """
    def block(reason: str, daily: bool = False, drawdown: bool = False) -> Decision:
        return Decision(False, reason, latch_daily_loss=daily, latch_drawdown=drawdown)

    try:
        if now.tzinfo is None or now.utcoffset() is None:
            return block("INVALID_UTC_CLOCK")
        if not customer.customer_id or not proposal.signal_id or not proposal.symbol:
            return block("MISSING_IDENTITY")
        if proposal.customer_id != customer.customer_id:
            return block("CUSTOMER_ID_MISMATCH")
        if proposal.environment != "DEMO" or proposal.order_side not in ("BUY", "SELL"):
            return block("DEMO_BUY_SELL_ONLY")
        if len(set(a.account_id for a in customer.accounts)) != len(customer.accounts):
            return block("DUPLICATE_ACCOUNT_IN_SNAPSHOT")
        if not customer.account_inventory_complete or not customer.exposure_complete:
            return block("INCOMPLETE_CUSTOMER_INVENTORY_OR_EXPOSURE")
        if not customer.accounts or any(a.customer_id != customer.customer_id for a in customer.accounts):
            return block("INVALID_ACCOUNT_OWNERSHIP")
        matching = [a for a in customer.accounts if a.account_id == proposal.account_id]
        if len(matching) != 1:
            return block("ACCOUNT_NOT_IN_CUSTOMER_PORTFOLIO")
        account = matching[0]
        if account.environment != "DEMO":
            return block("LIVE_ACCOUNT_NOT_AUTHORIZED")
        if customer.daily_lock_latched or account.daily_lock_latched:
            return block("PERSISTENT_DAILY_LOSS_LOCK")
        if customer.drawdown_lock_latched or account.drawdown_lock_latched:
            return block("PERSISTENT_MAX_DRAWDOWN_LOCK")
        if account.kill_switch:
            return block("KILL_SWITCH_ACTIVE")
        if not account.connected or not account.entitlement_ok or not account.effective_on:
            return block("ACCOUNT_OFF_OR_NOT_AUTHORIZED")
        if not proposal.native_stop_validated or not proposal.contract_spec_verified or not proposal.signal_fresh:
            return block("STOP_CONTRACT_OR_SIGNAL_UNVERIFIED")
        if not _positive(D(customer.day_start_equity_usd)) or not _positive(D(customer.peak_equity_usd)):
            return block("NO_DURABLE_CUSTOMER_EQUITY_BASELINE")
        if D(pending_customer_risk_usd) < 0 or D(pending_account_risk_ccy) < 0:
            return block("NEGATIVE_PENDING_RISK")
        for a in customer.accounts:
            fields = (a.equity_ccy, a.usd_per_ccy, a.day_start_equity_ccy,
                      a.peak_equity_ccy, a.open_stop_risk_ccy)
            # Connected real-money accounts that are client-OFF, unfunded and
            # broker-confirmed flat remain in the FULL customer inventory.
            # They contribute exactly zero to DEMO risk buying power; never
            # invent positive cash/equity to satisfy an accounting check.
            inactive_zero_live = (
                a.environment == "LIVE" and not a.effective_on and
                D(a.equity_ccy) == D("0") and
                D(a.day_start_equity_ccy) == D("0") and
                D(a.peak_equity_ccy) == D("0") and
                D(a.open_stop_risk_ccy) == D("0") and
                D(a.usd_per_ccy) > D("0"))
            if ((not inactive_zero_live and
                 any(not _positive(D(v)) for v in fields[:4])) or
                D(fields[4]) < 0):
                return block("INVALID_ACCOUNT_EQUITY_OR_EXPOSURE")
            if not a.exposure_complete or not a.native_stops_verified:
                return block("BROKER_POSITIONS_OR_STOPS_UNVERIFIED")
            if not a.connected:
                return block("OTHER_ACCOUNT_BROKER_DISCONNECTED")
            if a.broker_asof is None or a.broker_asof.tzinfo is None:
                return block("STALE_OR_UNDATED_BROKER_DATA")
            elapsed = (now - a.broker_asof).total_seconds()
            if elapsed < -1 or elapsed > policy.freshness_seconds:
                return block("STALE_OR_FUTURE_BROKER_DATA")
        if D(account.equity_ccy) <= D(account.day_start_equity_ccy) * (1 - policy.daily_loss):
            return block("ACCOUNT_DAILY_LOSS_THRESHOLD", daily=True)
        if D(account.equity_ccy) <= D(account.peak_equity_ccy) * (1 - policy.peak_drawdown):
            return block("ACCOUNT_MAX_DRAWDOWN_THRESHOLD", drawdown=True)
        portfolio_equity_usd = sum((D(a.equity_ccy) * D(a.usd_per_ccy) for a in customer.accounts), D("0"))
        if portfolio_equity_usd <= D(customer.day_start_equity_usd) * (1 - policy.daily_loss):
            return block("CUSTOMER_DAILY_LOSS_THRESHOLD", daily=True)
        if portfolio_equity_usd <= D(customer.peak_equity_usd) * (1 - policy.peak_drawdown):
            return block("CUSTOMER_MAX_DRAWDOWN_THRESHOLD", drawdown=True)
        per_lot_risk = sum((D(proposal.one_lot_stop_risk_ccy),
                            D(proposal.one_lot_roundtrip_cost_ccy),
                            D(proposal.one_lot_slippage_buffer_ccy)), D("0"))
        if not _positive(D(proposal.one_lot_stop_risk_ccy)) or any(D(v) < 0 for v in
           (proposal.one_lot_roundtrip_cost_ccy, proposal.one_lot_slippage_buffer_ccy)):
            return block("INVALID_BROKER_RISK_QUOTE")
        minimum = D(proposal.volume_min)
        maximum = D(proposal.volume_max)
        step = D(proposal.volume_step)
        if not (minimum > 0 and maximum >= minimum and step > 0):
            return block("INVALID_BROKER_VOLUME_RULES")
        account_open_risk = D(account.open_stop_risk_ccy) + D(pending_account_risk_ccy)
        customer_open_risk_usd = sum((D(a.open_stop_risk_ccy) * D(a.usd_per_ccy)
                    for a in customer.accounts), D("0")) + D(pending_customer_risk_usd)
        allowed_by_trade = policy.per_trade * D(account.equity_ccy)
        allowed_by_account = policy.open_risk * D(account.equity_ccy) - account_open_risk
        allowed_by_customer = (policy.open_risk * portfolio_equity_usd - customer_open_risk_usd) / D(account.usd_per_ccy)
        max_risk_ccy = min(allowed_by_trade, allowed_by_account, allowed_by_customer)
        if max_risk_ccy <= 0:
            return block("OPEN_RISK_CAP_REACHED")
        max_lots_by_risk = max_risk_ccy / per_lot_risk
        if max_lots_by_risk < minimum:
            return block("MINIMUM_LOT_EXCEEDS_RISK_BUDGET")
        max_valid = min(maximum, max_lots_by_risk)
        steps = ((max_valid - minimum) / step).to_integral_value(rounding=ROUND_FLOOR)
        volume = minimum + steps * step
        exposure = volume * per_lot_risk
        if volume < minimum or volume > maximum or exposure > max_risk_ccy:
            return block("VOLUME_RISK_CALCULATION_REJECTED")
        return Decision(True, "ALLOW_DEMO_PREORDER_ONLY", volume,
                        exposure, exposure * D(account.usd_per_ccy))
    except (ValueError, InvalidOperation, ArithmeticError, TypeError):
        return block("INVALID_OR_INCOMPLETE_INPUT")
