from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    BillingPlan,
    Customer,
    License,
    LicenseStatus,
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)
from app.services.pricing import discounted_amount

CURRENT_SUBSCRIPTION_STATUSES = (
    SubscriptionStatus.PENDING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAST_DUE,
)


async def create_subscription(
    db: AsyncSession,
    *,
    customer: Customer,
    license_record: License,
    plan: BillingPlan,
    provider: str,
) -> Subscription:
    if not plan.is_active:
        raise ValueError("Billing plan is inactive")
    if plan.product != license_record.product:
        raise ValueError("Billing plan does not match the routed bot product")

    existing = await db.scalar(
        select(Subscription)
        .where(
            Subscription.license_id == license_record.id,
            Subscription.status.in_(CURRENT_SUBSCRIPTION_STATUSES),
        )
        .order_by(Subscription.created_at.desc())
    )
    if existing is not None:
        raise ValueError("License already has a current subscription")

    discount = plan.broker_discount_percent if customer.broker_referral_verified else 0
    amount = discounted_amount(plan.price_minor, discount)

    subscription = Subscription(
        customer_id=customer.id,
        license_id=license_record.id,
        plan_id=plan.id,
        status=SubscriptionStatus.PENDING,
        provider=provider,
        amount_minor=amount,
        currency=plan.currency,
        discount_percent=discount,
    )
    db.add(subscription)
    await db.flush()
    return subscription


async def confirm_payment(
    db: AsyncSession,
    *,
    subscription: Subscription,
    provider: str,
    provider_event_id: str,
    amount_minor: int,
    currency: str,
    raw_event: dict[str, Any] | None = None,
) -> Payment:
    # Shared service-level protection: routes alone cannot certify payment.
    environment = get_settings().env.lower()
    if environment.startswith("recovery") or environment in {"production", "prod", "staging"}:
        raise ValueError("BILLING_ACTIVATION_DISABLED_PENDING_PROVIDER_CERTIFICATION")
    existing = await db.scalar(
        select(Payment).where(Payment.provider_event_id == provider_event_id)
    )
    if existing is not None:
        if existing.subscription_id != subscription.id:
            raise ValueError("Payment event is already linked to another subscription")
        return existing

    if subscription.status == SubscriptionStatus.ACTIVE:
        raise ValueError("Subscription is already paid")
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise ValueError("Cancelled subscription cannot accept payment")
    if subscription.status == SubscriptionStatus.EXPIRED:
        raise ValueError("Expired subscription cannot accept payment")
    if amount_minor != subscription.amount_minor:
        raise ValueError("Payment amount does not match subscription amount")
    if currency.upper() != subscription.currency.upper():
        raise ValueError("Payment currency does not match subscription currency")

    now = datetime.now(UTC)
    payment = Payment(
        subscription_id=subscription.id,
        provider=provider,
        provider_event_id=provider_event_id,
        amount_minor=amount_minor,
        currency=currency.upper(),
        status=PaymentStatus.PAID,
        raw_event=raw_event or {},
        paid_at=now,
    )
    db.add(payment)

    subscription.status = SubscriptionStatus.ACTIVE
    if subscription.starts_at is None:
        subscription.starts_at = now

    license_record = await db.get(License, subscription.license_id)
    if license_record is None:
        raise ValueError("Subscription license no longer exists")
    license_record.status = LicenseStatus.ACTIVE
    if license_record.starts_at is None:
        license_record.starts_at = now

    await db.flush()
    return payment
