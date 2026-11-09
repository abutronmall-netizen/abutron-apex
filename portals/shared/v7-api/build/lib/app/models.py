from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    CUSTOMER = "customer"
    SUPPORT = "support"
    ADMIN = "admin"


class AccountStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class BotTier(str, enum.Enum):
    INELIGIBLE = "ineligible"
    FLIPPER = "flipper"
    SCALPER = "scalper"
    MASTER = "master"


class LicenseStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class DevicePlatform(str, enum.Enum):
    ANDROID = "android"
    IOS = "ios"


class NotificationStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class PushAttemptStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False), default=Role.CUSTOMER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    broker_referral_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    broker_referral_slug: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    trading_accounts: Mapped[list[TradingAccount]] = relationship(back_populates="customer")
    licenses: Mapped[list[License]] = relationship(back_populates="customer")
    devices: Mapped[list[Device]] = relationship(back_populates="customer")


class Broker(Base):
    __tablename__ = "brokers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    adapter_key: Mapped[str] = mapped_column(String(80))
    api_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    trading_accounts: Mapped[list[TradingAccount]] = relationship(back_populates="broker")


class TradingAccount(Base):
    __tablename__ = "trading_accounts"
    __table_args__ = (
        Index("ix_trading_accounts_customer_status", "customer_id", "status"),
        Index("ix_trading_accounts_broker_login", "broker_id", "broker_login", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    broker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brokers.id"), index=True
    )
    broker_login: Mapped[str] = mapped_column(String(120))
    server_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    equity_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal(0))
    bot_tier: Mapped[BotTier] = mapped_column(
        Enum(BotTier, native_enum=False), default=BotTier.INELIGIBLE
    )
    route_reason: Mapped[str] = mapped_column(String(255), default="awaiting_equity_sync")
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, native_enum=False), default=AccountStatus.PENDING
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    customer: Mapped[Customer] = relationship(back_populates="trading_accounts")
    broker: Mapped[Broker] = relationship(back_populates="trading_accounts")
    license: Mapped[License | None] = relationship(
        back_populates="trading_account", uselist=False
    )


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    trading_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_accounts.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    product: Mapped[BotTier] = mapped_column(Enum(BotTier, native_enum=False))
    status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus, native_enum=False), default=LicenseStatus.PENDING
    )
    source: Mapped[str] = mapped_column(String(80), default="equity_router")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    customer: Mapped[Customer] = relationship(back_populates="licenses")
    trading_account: Mapped[TradingAccount] = relationship(back_populates="license")


class BillingPlan(Base):
    __tablename__ = "billing_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    product: Mapped[BotTier] = mapped_column(Enum(BotTier, native_enum=False), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="ZAR")
    price_minor: Mapped[int] = mapped_column(Integer)
    broker_discount_percent: Mapped[int] = mapped_column(Integer, default=70)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_customer_status", "customer_id", "status"),
        Index("ix_subscriptions_license_status", "license_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    license_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_plans.id"), index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False), default=SubscriptionStatus.PENDING
    )
    provider: Mapped[str] = mapped_column(String(80), default="manual")
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="ZAR")
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80))
    provider_event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False), default=PaymentStatus.PENDING
    )
    raw_event: Mapped[dict] = mapped_column(JSON, default=dict)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_customer_platform", "customer_id", "platform"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[DevicePlatform] = mapped_column(Enum(DevicePlatform, native_enum=False))
    device_id: Mapped[str] = mapped_column(String(255), unique=True)
    push_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="devices")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, native_enum=False), default=NotificationStatus.QUEUED
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80))
    status: Mapped[PushAttemptStatus] = mapped_column(
        Enum(PushAttemptStatus, native_enum=False), default=PushAttemptStatus.PENDING
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[str] = mapped_column(String(120))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, native_enum=False), default=OutboxStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
