from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Device,
    Notification,
    NotificationAttempt,
    NotificationStatus,
    PushAttemptStatus,
)
from app.services.push import PushDeliveryError, PushGatewayClient

BATCH_SIZE = 25


async def process_once() -> int:
    async with SessionLocal() as db:
        notifications = list(
            await db.scalars(
                select(Notification)
                .where(Notification.status == NotificationStatus.QUEUED)
                .order_by(Notification.created_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        )

        client = PushGatewayClient()
        processed = 0

        for notification in notifications:
            devices = list(
                await db.scalars(
                    select(Device).where(
                        Device.customer_id == notification.customer_id,
                        Device.is_active.is_(True),
                        Device.push_token.is_not(None),
                    )
                )
            )

            successes = 0
            last_message_id = None
            for device in devices:
                attempt = NotificationAttempt(
                    notification_id=notification.id,
                    device_id=device.id,
                    provider="abutron_push_gateway",
                )
                db.add(attempt)
                try:
                    result = await client.send(device, notification)
                    attempt.status = PushAttemptStatus.SENT
                    attempt.provider_message_id = result.provider_message_id
                    attempt.sent_at = datetime.now(UTC)
                    successes += 1
                    last_message_id = result.provider_message_id
                except (PushDeliveryError, httpx.HTTPError, ValueError) as exc:
                    attempt.status = PushAttemptStatus.FAILED
                    attempt.error = str(exc)[:2000]

            if successes:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(UTC)
                notification.provider_message_id = last_message_id
            elif devices:
                notification.status = NotificationStatus.FAILED
            else:
                notification.status = NotificationStatus.FAILED

            processed += 1

        await db.commit()
        return processed


async def run_forever() -> None:
    while True:
        processed = await process_once()
        await asyncio.sleep(2 if processed else 5)


if __name__ == "__main__":
    asyncio.run(run_forever())
