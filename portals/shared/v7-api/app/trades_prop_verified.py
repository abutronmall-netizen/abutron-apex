"""Authenticated V7 genuine broker-trades and prop reconciliation READ APIs.

These routes never synthesize balances, orders, trades or prop funding.
The new tables remain empty until a separately certified provider data importer
is independently validated and licensed. No API write method is exported.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Customer
from app.security import get_current_customer, require_admin


class TradeItem(BaseModel):
    id: uuid.UUID
    trading_account_id: uuid.UUID
    broker_ticket: str
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: Decimal
    lifecycle: Literal["OPEN", "CLOSED"]
    open_price: Decimal
    close_price: Decimal | None
    net_pnl: Decimal | None
    commission: Decimal | None
    swap: Decimal | None
    pnl_currency: str
    opened_at: datetime
    closed_at: datetime | None
    broker_source: str
    broker_reconciled_at: datetime


class TradeList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TradeItem]
    count: int
    source: Literal["BROKER_RECONCILED"]
    execution_enabled: Literal[False] = False


class PropItem(BaseModel):
    id: uuid.UUID
    firm_name: str
    program_name: str
    phase: Literal["APPLICATION", "EVALUATION", "VERIFICATION", "FUNDED", "FAILED", "CLOSED"]
    source_reconciled_at: datetime


class PropOverview(BaseModel):
    items: list[PropItem]
    count: int
    source: Literal["EXTERNAL_VERIFIED_PROP_RECORDS"]
    new_challenge_enabled: Literal[False] = False
    payments_enabled: Literal[False] = False
    payouts_enabled: Literal[False] = False


router = APIRouter(prefix="/api/v1", tags=["verified-trades-prop"])


@router.get("/trades", response_model=TradeList)
async def list_verified_trades(
    lifecycle: Literal["OPEN", "CLOSED"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> TradeList:
    # Ownership is enforced through the existing account FK, not a user-provided
    # customer ID; QA/disabled identities never get past get_current_customer.
    result = await db.execute(text("""
        SELECT h.id,h.trading_account_id,h.broker_ticket,h.symbol,h.direction,
               h.volume,h.lifecycle,h.open_price,h.close_price,h.net_pnl,
               h.commission,h.swap,h.pnl_currency,h.opened_at,h.closed_at,
               h.broker_source,h.broker_reconciled_at
        FROM public.broker_trade_history h
        JOIN public.trading_accounts a ON a.id=h.trading_account_id
        WHERE a.customer_id=:owner
        AND (CAST(:life AS text) IS NULL OR h.lifecycle=CAST(:life AS text))
        ORDER BY h.opened_at DESC,h.id DESC
        LIMIT :max_rows OFFSET :skip_rows
    """), {"owner":customer.id,"life":lifecycle,"max_rows":limit,"skip_rows":offset})
    items = [TradeItem.model_validate(dict(row)) for row in result.mappings()]
    return TradeList(items=items,count=len(items),source="BROKER_RECONCILED")


@router.get("/prop/overview", response_model=PropOverview)
async def prop_firm_overview(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> PropOverview:
    result = await db.execute(text("""
        SELECT id,firm_name,program_name,phase,source_reconciled_at
        FROM public.prop_firm_accounts
        WHERE customer_id=:owner
        ORDER BY created_at DESC,id DESC LIMIT 100
    """), {"owner":customer.id})
    items = [PropItem.model_validate(dict(row)) for row in result.mappings()]
    return PropOverview(items=items,count=len(items),source="EXTERNAL_VERIFIED_PROP_RECORDS")


@router.get("/admin/trades", response_model=TradeList)
async def admin_verified_trades(
    limit: int = Query(default=50,ge=1,le=100),
    _: Customer = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> TradeList:
    result = await db.execute(text("""
        SELECT h.id,h.trading_account_id,h.broker_ticket,h.symbol,h.direction,
               h.volume,h.lifecycle,h.open_price,h.close_price,h.net_pnl,
               h.commission,h.swap,h.pnl_currency,h.opened_at,h.closed_at,
               h.broker_source,h.broker_reconciled_at
        FROM public.broker_trade_history h
        JOIN public.trading_accounts a ON a.id=h.trading_account_id
        ORDER BY h.opened_at DESC,h.id DESC LIMIT :max_rows
    """),{"max_rows":limit})
    items = [TradeItem.model_validate(dict(row)) for row in result.mappings()]
    return TradeList(items=items,count=len(items),source="BROKER_RECONCILED")
