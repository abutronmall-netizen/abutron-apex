"""Market-data abstractions shared by the backtester, the paper loop and live feeds."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import numpy as np

from ..core.models import Bar

# trading hours / annualisation per asset class, by bar period
BARS_PER_YEAR_DAILY = {
    "crypto": 365.0,
    "us_equity": 252.0,
    "fx_index": 252.0,
    "deriv_synthetic": 365.0,
}
_PERIOD = "1h"


def set_period(period: str) -> None:
    """Switch annualisation between hourly ("1h") and daily ("1D") bars."""
    global _PERIOD
    _PERIOD = period


def get_period() -> str:
    return _PERIOD


BARS_PER_YEAR = {
    "crypto": 8760.0,
    "us_equity": 252.0 * 6.5,
    "fx_index": 252.0 * 23.0,
    "deriv_synthetic": 8760.0,
}

SESSION_UTC = {
    # start_hour_utc, end_hour_utc  (None = 24/7)
    "crypto": None,
    "us_equity": (14, 21),
    "fx_index": (7, 21),
    "deriv_synthetic": None,
}


def annualisation_from_ts(ts) -> float:
    """Bars per year implied by actual timestamps (hourly, daily, anything)."""
    import numpy as _np

    ts = _np.asarray(list(ts), dtype=float)
    if ts.size < 2:
        return 8760.0 if _PERIOD == "1h" else 365.25
    dt = float(_np.median(_np.diff(ts)))
    if dt <= 0:
        return 8760.0 if _PERIOD == "1h" else 365.25
    return float(365.25 * 24 * 3600 / dt)


def bars_per_year(asset_class: str) -> float:
    if _PERIOD != "1h":
        return BARS_PER_YEAR_DAILY.get(asset_class, 252.0)
    return BARS_PER_YEAR.get(asset_class, 6240.0)


def in_session(asset_class: str, hour_utc: int) -> bool:
    if _PERIOD != "1h":
        return True
    s = SESSION_UTC.get(asset_class)
    if s is None:
        return True
    return s[0] <= hour_utc < s[1]


@dataclass
class Panel:
    """Columnar OHLCV panel: dict[symbol] -> dict of numpy arrays."""
    symbols: List[str]
    ts: np.ndarray
    o: Dict[str, np.ndarray]
    h: Dict[str, np.ndarray]
    l: Dict[str, np.ndarray]
    c: Dict[str, np.ndarray]
    v: Dict[str, np.ndarray]
    active: Dict[str, np.ndarray]
    asset_class: Dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.ts)

    def bar(self, symbol: str, i: int) -> Bar:
        return Bar(
            symbol=symbol, ts=float(self.ts[i]), open=float(self.o[symbol][i]),
            high=float(self.h[symbol][i]), low=float(self.l[symbol][i]),
            close=float(self.c[symbol][i]), volume=float(self.v[symbol][i]),
        )

    def closes(self, symbol: str, upto: int) -> np.ndarray:
        """Closes from 0..upto inclusive (no lookahead)."""
        return self.c[symbol][: upto + 1]

    def slice_symbol(self, symbol: str, start: int, end: int) -> Dict[str, np.ndarray]:
        return {
            "o": self.o[symbol][start:end], "h": self.h[symbol][start:end],
            "l": self.l[symbol][start:end], "c": self.c[symbol][start:end],
            "v": self.v[symbol][start:end],
        }

    def iterator(self, start: int = 0) -> Iterable[Dict[str, Bar]]:
        for i in range(start, len(self.ts)):
            yield {s: self.bar(s, i) for s in self.symbols if self.active[s][i]}


class DataSource:
    """Anything that can hand the engine a warmup panel and then stream bars."""

    name = "base"

    def warmup(self, n: int) -> Dict[str, List[Bar]]:
        raise NotImplementedError

    def stream(self) -> Iterable[Dict[str, Bar]]:
        raise NotImplementedError
