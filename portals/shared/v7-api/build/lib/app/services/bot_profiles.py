from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.models import BotTier


class TradeFrequency(str, Enum):
    HIGH = "high"
    MEDIUM_HIGH = "medium_high"
    LOW_SELECTIVE = "low_selective"


@dataclass(frozen=True, slots=True)
class BotProfile:
    tier: BotTier
    profile_id: str
    profile_version: int
    core_style: str
    bias_timeframes: tuple[str, ...]
    confirmation_timeframes: tuple[str, ...]
    execution_timeframe: str
    trade_frequency: TradeFrequency
    directional_only: bool
    basket_execution: bool
    smc_ict_confirmation: bool

    @property
    def primary_tf_flow(self) -> tuple[str, ...]:
        return (
            *self.bias_timeframes,
            *self.confirmation_timeframes,
            self.execution_timeframe,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tier"] = self.tier.value
        payload["trade_frequency"] = self.trade_frequency.value
        payload["bias_timeframes"] = list(self.bias_timeframes)
        payload["confirmation_timeframes"] = list(self.confirmation_timeframes)
        payload["primary_tf_flow"] = list(self.primary_tf_flow)
        return payload


BOT_PROFILES: dict[BotTier, BotProfile] = {
    BotTier.FLIPPER: BotProfile(
        tier=BotTier.FLIPPER,
        profile_id="flipper-v1",
        profile_version=1,
        core_style="adaptive_directional_grid_basket",
        bias_timeframes=("M15", "M5"),
        confirmation_timeframes=(),
        execution_timeframe="M1",
        trade_frequency=TradeFrequency.HIGH,
        directional_only=True,
        basket_execution=True,
        smc_ict_confirmation=False,
    ),
    BotTier.SCALPER: BotProfile(
        tier=BotTier.SCALPER,
        profile_id="scalper-v1",
        profile_version=1,
        core_style="precision_sniper_scalping",
        bias_timeframes=("M15", "M5"),
        confirmation_timeframes=(),
        execution_timeframe="M1",
        trade_frequency=TradeFrequency.MEDIUM_HIGH,
        directional_only=True,
        basket_execution=False,
        smc_ict_confirmation=False,
    ),
    BotTier.MASTER: BotProfile(
        tier=BotTier.MASTER,
        profile_id="master-v1",
        profile_version=1,
        core_style="day_trading_trend_smc_ict",
        bias_timeframes=("H4", "H1"),
        confirmation_timeframes=("M15",),
        execution_timeframe="M5",
        trade_frequency=TradeFrequency.LOW_SELECTIVE,
        directional_only=True,
        basket_execution=False,
        smc_ict_confirmation=True,
    ),
}


def get_bot_profile(tier: BotTier | str) -> BotProfile:
    resolved = tier if isinstance(tier, BotTier) else BotTier(tier)
    try:
        return BOT_PROFILES[resolved]
    except KeyError as exc:
        raise ValueError(f"No executable strategy profile for bot tier: {resolved.value}") from exc
