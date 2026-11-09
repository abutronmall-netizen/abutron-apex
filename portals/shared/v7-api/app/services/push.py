from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.models import Device, Notification

settings = get_settings()


class PushDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PushResult:
    provider_message_id: str


class PushGatewayClient:
    async def send(self, device: Device, notification: Notification) -> PushResult:
        if not settings.push_gateway_enabled:
            raise PushDeliveryError("Push gateway is disabled")
        if not settings.push_gateway_url:
            raise PushDeliveryError("Push gateway URL is not configured")
        if not device.push_token:
            raise PushDeliveryError("Device has no push token")

        payload = {
            "platform": device.platform.value,
            "token": device.push_token,
            "title": notification.title,
            "body": notification.body,
            "data": notification.data,
        }
        headers = {"X-Abutron-Push-Token": settings.push_gateway_token}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.push_gateway_url.rstrip("/") + "/v1/push",
                json=payload,
                headers=headers,
            )
        if response.is_error:
            raise PushDeliveryError(f"Push gateway returned HTTP {response.status_code}")

        body = response.json()
        message_id = body.get("message_id")
        if not message_id:
            raise PushDeliveryError("Push gateway did not return message_id")
        return PushResult(provider_message_id=str(message_id))
