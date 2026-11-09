from __future__ import annotations

from app.services.brokers.base import BrokerAdapter


class BrokerRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, BrokerAdapter] = {}

    def register(self, adapter: BrokerAdapter) -> None:
        if not adapter.key:
            raise ValueError("Broker adapter key is required")
        self._adapters[adapter.key] = adapter

    def get(self, key: str) -> BrokerAdapter:
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise LookupError(f"No broker adapter registered for {key!r}") from exc

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


broker_registry = BrokerRegistry()
