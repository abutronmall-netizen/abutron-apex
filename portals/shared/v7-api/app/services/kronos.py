from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.config import get_settings
from app.models import BotTier

settings = get_settings()


@dataclass(frozen=True, slots=True)
class KronosAssignment:
    broker_login: str
    tier: BotTier
    equity_usd: Decimal
    enabled: bool
    strategy_profile: dict[str, Any] | None = None
    contract_version: int = 2


class KronosExecutionClient:
    """Thin boundary between the customer platform and the live Kronos engine.

    The platform never imports or mutates Kronos trading-core code directly.
    The live engine receives explicit account assignment commands through this adapter.
    """

    def __init__(self) -> None:
        self.base_url = settings.kronos_engine_url.rstrip("/")
        self.token = settings.kronos_engine_token

    async def apply_assignment(self, assignment: KronosAssignment) -> dict:
        payload = {
            "assignment_contract_version": assignment.contract_version,
            "broker_login": assignment.broker_login,
            "bot_tier": assignment.tier.value,
            "equity_usd": str(assignment.equity_usd),
            "enabled": assignment.enabled,
            "strategy_profile": assignment.strategy_profile,
        }
        headers = {"X-Abutron-Engine-Token": self.token}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{self.base_url}/platform/v1/account-assignment",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
