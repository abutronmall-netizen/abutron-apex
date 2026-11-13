from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BrokerAccountSnapshot:
    broker_login: str
    equity_usd: Decimal
    currency: str
    connected: bool


class BrokerAdapter(ABC):
    """Contract implemented by each broker connector.

    Broker-specific authentication and MT5/API details stay outside the
    customer/admin domain layer.
    """

    key: str

    @abstractmethod
    async def fetch_account(self, broker_login: str) -> BrokerAccountSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError
