from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker_link_policy import require_certified_broker_account_linking
from app.config import get_settings
from app.db import get_db
from app.email_verification import (
    VerificationRequest,
    ensure_mail_ready,
    parse_email_proof,
    requires_email_verification,
    send_email_proof,
)
from app.license_status_policy import require_certified_license_transition
from app.models import (
    AccountStatus,
    AuditEvent,
    BillingPlan,
    BotTier,
    Broker,
    Customer,
    Device,
    License,
    LicenseStatus,
    Notification,
    NotificationStatus,
    Payment,
    Role,
    Subscription,
    TradingAccount,
)
from app.release_capabilities import mobile_feature_flags
from app.schemas import (
    AdminDashboardResponse,
    AuditEventPublic,
    BillingPlanCreate,
    BillingPlanPublic,
    BillingWebhookEvent,
    BrokerCreate,
    BrokerPublic,
    CustomerPublic,
    DevicePublic,
    DeviceRegisterRequest,
    EquityDecisionPublic,
    EquitySyncRequest,
    LicensePublic,
    LicenseStatusUpdate,
    LoginRequest,
    MobileBootstrapResponse,
    NotificationCreate,
    NotificationPublic,
    PaymentConfirmationRequest,
    PaymentPublic,
    ReferralVerificationUpdate,
    RegisterRequest,
    SubscriptionCreate,
    SubscriptionPublic,
    TokenResponse,
    TradingAccountCreate,
    TradingAccountPublic,
)
from app.security import (
    create_access_token,
    get_current_customer,
    hash_password,
    require_admin,
    require_service_token,
    verify_password,
)
from app.services.billing import confirm_payment, create_subscription
from app.services.entitlements import reconcile_license
from app.services.equity_router import select_bot
from app.services.outbox import enqueue_account_assignment
from app.services.webhooks import verify_signature

settings = get_settings()
router = APIRouter(prefix="/api/v1")


@router.post("/auth/register", response_model=CustomerPublic, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> Customer:
    # Registration can resume without an October customer roster, but new
    # release accounts may not authenticate until email ownership is proven.
    release_signup = requires_email_verification(settings.env)
    if release_signup:
        ensure_mail_ready()  # fails before any database mutation if mail is unavailable
    email = request.email.strip().lower()
    if await db.scalar(select(Customer.id).where(Customer.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    customer = Customer(
        email=email,
        full_name=request.full_name.strip(),
        phone=request.phone.strip() if request.phone else None,
        password_hash=hash_password(request.password),
        role=Role.CUSTOMER,
        is_active=not release_signup,
    )
    db.add(customer)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    await db.refresh(customer)
    if release_signup:
        await send_email_proof(customer.email, customer.id)
    return customer


@router.post("/auth/verify-email")
async def verify_email(
    request: VerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    customer_id, email = parse_email_proof(request.token)
    customer = await db.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.email == email)
        .with_for_update()
    )
    if customer is None or customer.is_active:
        raise HTTPException(status_code=400, detail="INVALID_OR_USED_VERIFICATION")
    if customer.role != Role.CUSTOMER:
        raise HTTPException(status_code=400, detail="INVALID_OR_USED_VERIFICATION")
    customer.is_active = True
    await db.commit()
    return {"status": "email_verified", "trading": "disabled"}


@router.post("/auth/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    # Generic result prevents leaking registered email addresses.
    if requires_email_verification(settings.env):
        ensure_mail_ready()
    customer = await db.scalar(
        select(Customer).where(Customer.email == request.email.strip().lower())
    )
    if (customer is not None and not customer.is_active
            and customer.role == Role.CUSTOMER
            and verify_password(request.password, customer.password_hash)):
        await send_email_proof(customer.email, customer.id)
    return {"status": "verification_requested"}


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    customer = await db.scalar(
        select(Customer).where(Customer.email == request.email.strip().lower())
    )
    if customer is None or not customer.is_active or not verify_password(
        request.password, customer.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token, expires_in = create_access_token(customer)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=CustomerPublic)
async def me(customer: Customer = Depends(get_current_customer)) -> Customer:
    return customer


@router.get("/brokers", response_model=list[BrokerPublic])
async def list_brokers(
    _: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> list[Broker]:
    result = await db.scalars(
        select(Broker).where(Broker.is_active.is_(True)).order_by(Broker.display_name)
    )
    return list(result)


@router.post(
    "/accounts",
    response_model=TradingAccountPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_trading_account(
    request: TradingAccountCreate,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> TradingAccount:
    # Unverified self-asserted broker logins cannot confer account ownership.
    # Broker linking requires an independent broker attestation first.
    require_certified_broker_account_linking(settings.env)
    broker = await db.get(Broker, request.broker_id)
    if broker is None or not broker.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker unavailable")

    account = TradingAccount(
        customer_id=customer.id,
        broker_id=broker.id,
        broker_login=request.broker_login.strip(),
        server_name=request.server_name.strip() if request.server_name else None,
        status=AccountStatus.PENDING,
    )
    db.add(account)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This broker account is already registered",
        ) from exc
    await db.refresh(account)
    return account


@router.get("/accounts", response_model=list[TradingAccountPublic])
async def list_accounts(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> list[TradingAccount]:
    result = await db.scalars(
        select(TradingAccount)
        .where(TradingAccount.customer_id == customer.id)
        .order_by(TradingAccount.created_at.desc())
    )
    return list(result)



@router.post("/accounts/{account_id}/disable", response_model=TradingAccountPublic)
async def disable_account_portal_assignment(
    account_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> TradingAccount:
    """Disable portal assignment; does not assert broker OAuth revocation or close positions."""
    if settings.kronos_push_enabled:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="ACCOUNT_DISABLE_REQUIRES_CERTIFIED_BROKER_POSITION_HANDOFF",
        )
    account = await db.scalar(
        select(TradingAccount)
        .where(TradingAccount.id == account_id, TradingAccount.customer_id == customer.id)
        .with_for_update()
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if account.status == AccountStatus.DISABLED:
        return account
    previous = account.status
    account.status = AccountStatus.DISABLED
    license_record = await db.scalar(
        select(License).where(License.trading_account_id == account.id).with_for_update()
    )
    if license_record is not None and license_record.status == LicenseStatus.ACTIVE:
        license_record.status = LicenseStatus.SUSPENDED
    await enqueue_account_assignment(db, account, license_record)
    db.add(
        AuditEvent(
            actor_customer_id=customer.id,
            action="portal_account_assignment_disabled",
            entity_type="trading_account",
            entity_id=str(account.id),
            payload={
                "from": previous.value,
                "to": AccountStatus.DISABLED.value,
                "broker_connection_revoked": False,
                "broker_positions_closed": False,
            },
        )
    )
    await db.commit()
    await db.refresh(account)
    return account


@router.put("/devices", response_model=DevicePublic)
async def register_device(
    request: DeviceRegisterRequest,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> Device:
    device = await db.scalar(select(Device).where(Device.device_id == request.device_id))
    now = datetime.now(UTC)

    if device is not None and device.customer_id != customer.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Device is registered to another account",
        )

    if device is None:
        device = Device(
            customer_id=customer.id,
            platform=request.platform,
            device_id=request.device_id,
        )
        db.add(device)

    device.platform = request.platform
    device.push_token = request.push_token
    device.app_version = request.app_version
    device.is_active = True
    device.last_seen_at = now

    await db.commit()
    await db.refresh(device)
    return device


@router.get("/billing/plans", response_model=list[BillingPlanPublic])
async def list_billing_plans(
    _: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> list[BillingPlan]:
    plans = await db.scalars(
        select(BillingPlan)
        .where(BillingPlan.is_active.is_(True))
        .order_by(BillingPlan.price_minor)
    )
    return list(plans)


@router.post(
    "/billing/subscriptions",
    response_model=SubscriptionPublic,
    status_code=status.HTTP_201_CREATED,
)
async def start_subscription(
    request: SubscriptionCreate,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    license_record = await db.get(License, request.license_id)
    if license_record is None or license_record.customer_id != customer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")

    plan = await db.get(BillingPlan, request.plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing plan not found")

    try:
        subscription = await create_subscription(
            db,
            customer=customer,
            license_record=license_record,
            plan=plan,
            provider=request.provider.strip().lower(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(subscription)
    return subscription


@router.get("/billing/subscriptions", response_model=list[SubscriptionPublic])
async def list_subscriptions(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> list[Subscription]:
    subscriptions = await db.scalars(
        select(Subscription)
        .where(Subscription.customer_id == customer.id)
        .order_by(Subscription.created_at.desc())
    )
    return list(subscriptions)


@router.get("/notifications", response_model=list[NotificationPublic])
async def list_notifications(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> list[Notification]:
    notifications = await db.scalars(
        select(Notification)
        .where(Notification.customer_id == customer.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    )
    return list(notifications)


@router.patch("/notifications/{notification_id}/read", response_model=NotificationPublic)
async def mark_notification_read(
    notification_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> Notification:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.customer_id != customer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(notification)
    return notification


@router.get("/mobile/bootstrap", response_model=MobileBootstrapResponse)
async def mobile_bootstrap(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> MobileBootstrapResponse:
    accounts = list(
        await db.scalars(
            select(TradingAccount)
            .where(TradingAccount.customer_id == customer.id)
            .order_by(TradingAccount.created_at.desc())
        )
    )
    licenses = list(
        await db.scalars(
            select(License)
            .where(License.customer_id == customer.id)
            .order_by(License.created_at.desc())
        )
    )
    return MobileBootstrapResponse(
        customer=CustomerPublic.model_validate(customer),
        accounts=[TradingAccountPublic.model_validate(item) for item in accounts],
        licenses=[LicensePublic.model_validate(item) for item in licenses],
        feature_flags=mobile_feature_flags(),
    )


@router.put(
    "/internal/accounts/{account_id}/equity",
    response_model=EquityDecisionPublic,
    dependencies=[Depends(require_service_token)],
)
async def sync_equity(
    account_id: uuid.UUID,
    request: EquitySyncRequest,
    db: AsyncSession = Depends(get_db),
) -> EquityDecisionPublic:
    # A portal-disabled account is owner-controlled. Broker equity updates must
    # never silently reactivate it. Lock this row to serialize with /disable.
    account = await db.scalar(
        select(TradingAccount)
        .where(TradingAccount.id == account_id)
        .with_for_update()
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if account.status == AccountStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="PORTAL_DISABLED_ACCOUNT_REQUIRES_REVIEWED_REENABLE",
        )

    decision = select_bot(request.equity_usd)
    account.equity_usd = decision.equity_usd
    account.bot_tier = decision.tier
    account.route_reason = decision.reason
    account.status = request.account_status
    account.last_synced_at = datetime.now(UTC)

    license_record = await reconcile_license(db, account, decision)
    await enqueue_account_assignment(db, account, license_record)
    db.add(
        AuditEvent(
            action="equity_sync",
            entity_type="trading_account",
            entity_id=str(account.id),
            payload={
                "equity_usd": str(decision.equity_usd),
                "bot_tier": decision.tier.value,
                "eligible": decision.eligible,
                "reason": decision.reason,
            },
        )
    )
    await db.commit()
    return EquityDecisionPublic(
        eligible=decision.eligible,
        tier=decision.tier,
        equity_usd=decision.equity_usd,
        reason=decision.reason,
    )


@router.post(
    "/internal/billing/payment-confirmed",
    response_model=PaymentPublic,
    dependencies=[Depends(require_service_token)],
)
async def payment_confirmed(
    request: PaymentConfirmationRequest,
    db: AsyncSession = Depends(get_db),
):
    subscription = await db.get(Subscription, request.subscription_id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    try:
        payment = await confirm_payment(
            db,
            subscription=subscription,
            provider=request.provider.strip().lower(),
            provider_event_id=request.provider_event_id,
            amount_minor=request.amount_minor,
            currency=request.currency,
            raw_event=request.raw_event,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    license_record = await db.get(License, subscription.license_id)
    if license_record is not None:
        account = await db.get(TradingAccount, license_record.trading_account_id)
        if account is not None:
            await enqueue_account_assignment(db, account, license_record)

    db.add(
        AuditEvent(
            action="payment_confirmed",
            entity_type="subscription",
            entity_id=str(subscription.id),
            payload={
                "provider": request.provider,
                "provider_event_id": request.provider_event_id,
                "amount_minor": request.amount_minor,
                "currency": request.currency.upper(),
            },
        )
    )
    await db.commit()
    await db.refresh(payment)
    return payment


@router.post("/webhooks/billing/{provider}", response_model=PaymentPublic)
async def billing_webhook(
    provider: str,
    request: Request,
    x_abutron_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Payment:
    raw_body = await request.body()
    if not verify_signature(settings.billing_webhook_secret, raw_body, x_abutron_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    try:
        event = BillingWebhookEvent.model_validate_json(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload") from exc

    provider_name = provider.strip().lower()
    if not provider_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider is required")

    subscription = await db.get(Subscription, event.subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    if subscription.provider.strip().lower() != provider_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Webhook provider does not match subscription provider",
        )

    try:
        payment = await confirm_payment(
            db,
            subscription=subscription,
            provider=provider_name,
            provider_event_id=event.event_id,
            amount_minor=event.amount_minor,
            currency=event.currency,
            raw_event=event.model_dump(mode="json"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    license_record = await db.get(License, subscription.license_id)
    if license_record is not None:
        account = await db.get(TradingAccount, license_record.trading_account_id)
        if account is not None:
            await enqueue_account_assignment(db, account, license_record)

    db.add(
        AuditEvent(
            action="billing_webhook_confirmed",
            entity_type="subscription",
            entity_id=str(subscription.id),
            payload={
                "provider": provider_name,
                "provider_event_id": event.event_id,
                "amount_minor": event.amount_minor,
                "currency": event.currency.upper(),
            },
        )
    )
    await db.commit()
    await db.refresh(payment)
    return payment


@router.get("/admin/dashboard", response_model=AdminDashboardResponse)
async def admin_dashboard(
    _: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminDashboardResponse:
    customers = await db.scalar(select(func.count()).select_from(Customer)) or 0
    active_accounts = (
        await db.scalar(
            select(func.count())
            .select_from(TradingAccount)
            .where(TradingAccount.status == AccountStatus.ACTIVE)
        )
        or 0
    )
    active_licenses = (
        await db.scalar(
            select(func.count())
            .select_from(License)
            .where(License.status == LicenseStatus.ACTIVE)
        )
        or 0
    )
    registered_devices = await db.scalar(select(func.count()).select_from(Device)) or 0
    queued_notifications = (
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.status == NotificationStatus.QUEUED)
        )
        or 0
    )

    return AdminDashboardResponse(
        customers=customers,
        active_accounts=active_accounts,
        active_licenses=active_licenses,
        registered_devices=registered_devices,
        queued_notifications=queued_notifications,
    )


@router.get("/admin/customers", response_model=list[CustomerPublic])
async def admin_customers(
    _: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Customer]:
    customers = await db.scalars(select(Customer).order_by(Customer.created_at.desc()).limit(500))
    return list(customers)


@router.get("/admin/accounts", response_model=list[TradingAccountPublic])
async def admin_accounts(
    _: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[TradingAccount]:
    accounts = await db.scalars(
        select(TradingAccount).order_by(TradingAccount.created_at.desc()).limit(500)
    )
    return list(accounts)


@router.get("/admin/licenses", response_model=list[LicensePublic])
async def admin_licenses(
    _: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[License]:
    licenses = await db.scalars(select(License).order_by(License.created_at.desc()).limit(500))
    return list(licenses)


@router.get("/admin/subscriptions", response_model=list[SubscriptionPublic])
async def admin_subscriptions(
    _: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Subscription]:
    subscriptions = await db.scalars(
        select(Subscription).order_by(Subscription.created_at.desc()).limit(500)
    )
    return list(subscriptions)


@router.get("/admin/payments", response_model=list[PaymentPublic])
async def admin_payments(
    _: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Payment]:
    payments = await db.scalars(select(Payment).order_by(Payment.created_at.desc()).limit(500))
    return list(payments)


@router.get("/admin/audit-events", response_model=list[AuditEventPublic])
async def admin_audit_events(
    _: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEvent]:
    events = await db.scalars(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500)
    )
    return list(events)


@router.post(
    "/admin/brokers",
    response_model=BrokerPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_broker(
    request: BrokerCreate,
    admin: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Broker:
    broker = Broker(
        slug=request.slug,
        display_name=request.display_name.strip(),
        adapter_key=request.adapter_key.strip(),
        api_base_url=request.api_base_url,
    )
    db.add(broker)
    db.add(
        AuditEvent(
            actor_customer_id=admin.id,
            action="broker_created",
            entity_type="broker",
            entity_id=request.slug,
            payload={"display_name": request.display_name, "adapter_key": request.adapter_key},
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Broker slug already exists"
        ) from exc
    await db.refresh(broker)
    return broker


@router.post(
    "/admin/billing/plans",
    response_model=BillingPlanPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_billing_plan(
    request: BillingPlanCreate,
    admin: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BillingPlan:
    if request.product == BotTier.INELIGIBLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ineligible is not a billable product",
        )

    plan = BillingPlan(
        code=request.code,
        display_name=request.display_name.strip(),
        product=request.product,
        currency=request.currency.upper(),
        price_minor=request.price_minor,
        broker_discount_percent=request.broker_discount_percent,
    )
    db.add(plan)
    db.add(
        AuditEvent(
            actor_customer_id=admin.id,
            action="billing_plan_created",
            entity_type="billing_plan",
            entity_id=request.code,
            payload={
                "product": request.product.value,
                "price_minor": request.price_minor,
                "currency": request.currency.upper(),
                "broker_discount_percent": request.broker_discount_percent,
            },
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Billing plan code already exists",
        ) from exc
    await db.refresh(plan)
    return plan


@router.put("/admin/customers/{customer_id}/referral", response_model=CustomerPublic)
async def verify_referral(
    customer_id: uuid.UUID,
    request: ReferralVerificationUpdate,
    admin: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    if request.verified:
        if not request.broker_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Broker slug is required when verifying a referral",
            )
        broker = await db.scalar(
            select(Broker).where(
                Broker.slug == request.broker_slug,
                Broker.is_active.is_(True),
            )
        )
        if broker is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Referral broker is not active or does not exist",
            )

    customer.broker_referral_verified = request.verified
    customer.broker_referral_slug = request.broker_slug if request.verified else None
    db.add(
        AuditEvent(
            actor_customer_id=admin.id,
            action="broker_referral_updated",
            entity_type="customer",
            entity_id=str(customer.id),
            payload={
                "verified": request.verified,
                "broker_slug": customer.broker_referral_slug,
            },
        )
    )
    await db.commit()
    await db.refresh(customer)
    return customer


@router.post(
    "/admin/notifications",
    response_model=NotificationPublic,
    status_code=status.HTTP_201_CREATED,
)
async def queue_notification(
    request: NotificationCreate,
    admin: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Notification:
    customer = await db.get(Customer, request.customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    notification = Notification(
        customer_id=customer.id,
        title=request.title,
        body=request.body,
        data=request.data,
        status=NotificationStatus.QUEUED,
    )
    db.add(notification)
    await db.flush()
    db.add(
        AuditEvent(
            actor_customer_id=admin.id,
            action="notification_queued",
            entity_type="notification",
            entity_id=str(notification.id),
            payload={"customer_id": str(customer.id), "title": notification.title},
        )
    )
    await db.commit()
    await db.refresh(notification)
    return notification


@router.put("/admin/licenses/{license_id}", response_model=LicensePublic)
async def update_license_status(
    license_id: uuid.UUID,
    request: LicenseStatusUpdate,
    admin: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> License:
    require_certified_license_transition(request.status)
    license_record = await db.scalar(
        select(License).where(License.id == license_id).with_for_update()
    )
    if license_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")

    previous = license_record.status
    if previous == request.status:
        return license_record  # Idempotent: no new outbox event or audit entry.
    license_record.status = request.status

    account = await db.get(TradingAccount, license_record.trading_account_id)
    if account is not None:
        await enqueue_account_assignment(db, account, license_record)

    db.add(
        AuditEvent(
            actor_customer_id=admin.id,
            action="license_status_changed",
            entity_type="license",
            entity_id=str(license_record.id),
            payload={"from": previous.value, "to": request.status.value},
        )
    )
    await db.commit()
    await db.refresh(license_record)
    return license_record
