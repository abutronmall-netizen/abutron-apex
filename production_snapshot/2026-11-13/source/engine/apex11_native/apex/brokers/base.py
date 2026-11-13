"""Broker interface."""
from __future__ import annotations

from typing import Dict, List, Optional

from ..core.models import Fill, Order, Position, Quote, Trade


class Broker:
    name = "base"

    def set_quote(self, q: Quote) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def submit(self, order: Order) -> Optional[Fill]:
        raise NotImplementedError

    @property
    def cash(self) -> float:
        raise NotImplementedError

    @property
    def equity(self) -> float:
        raise NotImplementedError

    def positions(self) -> Dict[str, Position]:
        raise NotImplementedError

    def trades(self) -> List[Trade]:
        raise NotImplementedError

    def flatten(self, symbol: Optional[str] = None) -> List[Fill]:
        raise NotImplementedError
