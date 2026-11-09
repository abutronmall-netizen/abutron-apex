from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import (
    AccountStatus,
    BotTier,
    DevicePlatform,
    LicenseStatus,
    NotificationStatus,
    PaymentStatus,
    Role,
    SubscriptionStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=50)


class CustomerPublic(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    role: Role
    is_active: bool
    broker_referral_verified: bool
    broker_referral_slug: str | None
    created_at: datetime


class BrokerPublic(ORMModel):
    id: uuid.UUID
    slug: str
    display_name: str
    is_active: bool


class BrokerCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,78}[a-z0-9]$")
    display_name: str = Field(min_length=2, max_length=160)
    adapter_key: str = Field(min_length=2, max_length=80)
    api_base_url: str | None = Field(default=None, max_length=500)


class ReferralVerificationUpdate(BaseModel):
    verified: bool
    broker_slug: str | None = Field(default=None, max_length=80)


class TradingAccountPublic(ORMModel):
    id: uuid.UUID
    broker_login: str
    server_name: str | None
    currency: str
    equity_usd: Decimal
    bot_tier: BotTier
    route_reason: str
    status: AccountStatus
    last_synced_at: datetime | None


class LicensePublic(ORMModel):
    id: uuid.UUID
    trading_account_id: uuid.UUID
    product: BotTier
    status: LicenseStatus
    starts_at: datetime | None
    expires_at: datetime | None


class LicenseStatusUpdate(BaseModel):
    status: LicenseStatus


class TradingAccountCreate(BaseModel):
    broker_id: uuid.UUID
    broker_login: str = Field(min_length=1, max_length=120)
    server_name: str | None = Field(default=None, max_length=160)


class EquitySyncRequest(BaseModel):
    equity_usd: Decimal = Field(ge=Decimal(0))
    account_status: AccountStatus = AccountStatus.ACTIVE


class EquityDecisionPublic(BaseModel):
    eligible: bool
    tier: BotTier
    equity_usd: Decimal
    reason: str


class DeviceRegisterRequest(BaseModel):
    platform: DevicePlatform
    device_id: str = Field(min_length=4, max_length=255)
    push_token: str | None = Field(default=None, max_length=4096)
    app_version: str | None = Field(default=None, max_length=40)


class DevicePublic(ORMModel):
    id: uuid.UUID
    platform: DevicePlatform
    device_id: str
    app_version: str | None
    is_active: bool
    last_seen_at: datetime


class BillingPlanCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,78}[a-z0-9]$")
    display_name: str = Field(min_length=2, max_length=160)
    product: BotTier
    currency: str = Field(default="ZAR", min_length=3, max_length=3)
    price_minor: int = Field(gt=0)
    broker_discount_percent: int = Field(default=70, ge=0, le=100)


class BillingPlanPublic(ORMModel):
    id: uuid.UUID
    code: str
    display_name: str
    product: BotTier
    currency: str
    price_minor: int
    broker_discount_percent: int
    is_active: bool


class SubscriptionCreate(BaseModel):
    license_id: uuid.UUID
    plan_id: uuid.UUID
    provider: str = Field(default="manual", min_length=2, max_length=80)


class SubscriptionPublic(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    license_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    provider: str
    provider_reference: str | None
    amount_minor: int
    currency: str
    discount_percent: int
    starts_at: datetime | None
    renews_at: datetime | None
    created_at: datetime


class PaymentConfirmationRequest(BaseModel):
    subscription_id: uuid.UUID
    provider: str = Field(min_length=2, max_length=80)
    provider_event_id: str = Field(min_length=2, max_length=255)
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    raw_event: dict = Field(default_factory=dict)


class PaymentPublic(ORMModel):
    id: uuid.UUID
    subscription_id: uuid.UUID
    provider: str
    provider_event_id: str
    amount_minor: int
    currency: str
    status: PaymentStatus
    paid_at: datetime | None


class BillingWebhookEvent(BaseModel):
    subscription_id: uuid.UUID
    event_id: str = Field(min_length=2, max_length=255)
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    status: Literal["paid"]
    data: dict = Field(default_factory=dict)


class AuditEventPublic(ORMModel):
    id: uuid.UUID
    actor_customer_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    payload: dict
    created_at: datetime


class NotificationCreate(BaseModel):
    customer_id: uuid.UUID
    title: str = Field(min_length=1, max_length=180)
    body: str = Field(min_length=1, max_length=4000)
    data: dict = Field(default_factory=dict)


class NotificationPublic(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    title: str
    body: str
    data: dict
    status: NotificationStatus
    created_at: datetime
    sent_at: datetime | None
    read_at: datetime | None


class MobileBootstrapResponse(BaseModel):
    customer: CustomerPublic
    accounts: list[TradingAccountPublic]
    licenses: list[LicensePublic]
    feature_flags: dict[str, bool]


class AdminDashboardResponse(BaseModel):
    customers: int
    active_accounts: int
    active_licenses: int
    registered_devices: int
    queued_notifications: int
