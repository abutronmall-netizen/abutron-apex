from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models import BotTier

MIN_EQUITY = Decimal("20.00")
FLIPPER_MAX = Decimal("4999.99")
SCALPER_MAX = Decimal("9999.99")
MASTER_MAX = Decimal("1000000.00")


@dataclass(frozen=True, slots=True)
class EquityDecision:
    eligible: bool
    tier: BotTier
    equity_usd: Decimal
    reason: str


def select_bot(equity_usd: Decimal | float | str) -> EquityDecision:
    equity = Decimal(str(equity_usd)).quantize(Decimal("0.01"))

    if equity < Decimal(0):
        raise ValueError("equity_usd cannot be negative")

    if equity < MIN_EQUITY:
        return EquityDecision(
            eligible=False,
            tier=BotTier.INELIGIBLE,
            equity_usd=equity,
            reason="MINIMUM_EQUITY_NOT_MET",
        )

    if equity <= FLIPPER_MAX:
        return EquityDecision(
            eligible=True,
            tier=BotTier.FLIPPER,
            equity_usd=equity,
            reason="EQUITY_ROUTE_FLIPPER",
        )

    if equity <= SCALPER_MAX:
        return EquityDecision(
            eligible=True,
            tier=BotTier.SCALPER,
            equity_usd=equity,
            reason="EQUITY_ROUTE_SCALPER",
        )

    # Master is specified for the longer-term product tier, but remains
    # disabled for the current Flipper/Scalper-only release.
    if equity <= MASTER_MAX:
        return EquityDecision(
            eligible=False,
            tier=BotTier.INELIGIBLE,
            equity_usd=equity,
            reason="MASTER_BOT_DEFERRED_FOR_RELEASE",
        )

    return EquityDecision(
        eligible=False,
        tier=BotTier.INELIGIBLE,
        equity_usd=equity,
        reason="EQUITY_ABOVE_AUTOMATIC_ROUTE_REQUIRES_REVIEW",
    )
