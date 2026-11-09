from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountStatus, BotTier, License, LicenseStatus, TradingAccount
from app.services.equity_router import EquityDecision


async def reconcile_license(
    db: AsyncSession,
    account: TradingAccount,
    decision: EquityDecision,
) -> License | None:
    existing = await db.scalar(
        select(License).where(License.trading_account_id == account.id)
    )

    if not decision.eligible:
        if existing and existing.status == LicenseStatus.ACTIVE:
            existing.status = LicenseStatus.SUSPENDED
        return existing

    if existing is None:
        existing = License(
            customer_id=account.customer_id,
            trading_account_id=account.id,
            product=decision.tier,
            status=LicenseStatus.PENDING,
            source="equity_router",
        )
        db.add(existing)
        await db.flush()
        return existing

    existing.product = decision.tier
    return existing


def license_allows_execution(license_record: License | None) -> bool:
    if license_record is None or license_record.status != LicenseStatus.ACTIVE:
        return False
    return license_record.expires_at is None or license_record.expires_at > datetime.now(UTC)


def account_allows_execution(account: TradingAccount, license_record: License | None) -> bool:
    """Defense in depth: never assign an executable bot to an ineligible account."""
    if account.status != AccountStatus.ACTIVE:
        return False
    if account.bot_tier not in {BotTier.FLIPPER, BotTier.SCALPER}:
        return False
    if not license_allows_execution(license_record):
        return False
    return (
        license_record.customer_id == account.customer_id
        and license_record.trading_account_id == account.id
        and license_record.product == account.bot_tier
    )
