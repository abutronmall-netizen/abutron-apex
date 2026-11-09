from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import BillingPlan, BotTier

DEFAULT_PLANS = (
    {
        "code": "flipper-once-off",
        "display_name": "Abutron Flipper",
        "product": BotTier.FLIPPER,
        "currency": "ZAR",
        "price_minor": 500_000,
        "broker_discount_percent": 70,
    },
    {
        "code": "scalper-once-off",
        "display_name": "Abutron Scalper",
        "product": BotTier.SCALPER,
        "currency": "ZAR",
        "price_minor": 330_000,
        "broker_discount_percent": 70,
    },
    {
        "code": "master-once-off",
        "display_name": "Abutron Master",
        "product": BotTier.MASTER,
        "currency": "ZAR",
        "price_minor": 1_000_000,
        "broker_discount_percent": 70,
    },
)


async def bootstrap_catalog() -> None:
    async with SessionLocal() as db:
        for plan_data in DEFAULT_PLANS:
            plan = await db.scalar(
                select(BillingPlan).where(BillingPlan.code == plan_data["code"])
            )
            if plan is None:
                plan = BillingPlan(**plan_data)
                db.add(plan)
            else:
                plan.display_name = plan_data["display_name"]
                plan.product = plan_data["product"]
                plan.currency = plan_data["currency"]
                plan.price_minor = plan_data["price_minor"]
                plan.broker_discount_percent = plan_data["broker_discount_percent"]
                plan.is_active = True

        await db.commit()


if __name__ == "__main__":
    asyncio.run(bootstrap_catalog())
