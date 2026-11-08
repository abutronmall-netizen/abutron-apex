"""Rolling in-memory OHLCV store shared by all agents (no lookahead by construction)."""
from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from .models import Bar, Quote


class HistoryStore:
    def __init__(self, symbols: Iterable[str], maxlen: int = 1500) -> None:
        self.maxlen = maxlen
        self.symbols = list(symbols)
        self._o = {s: deque(maxlen=maxlen) for s in self.symbols}
        self._h = {s: deque(maxlen=maxlen) for s in self.symbols}
        self._l = {s: deque(maxlen=maxlen) for s in self.symbols}
        self._c = {s: deque(maxlen=maxlen) for s in self.symbols}
        self._v = {s: deque(maxlen=maxlen) for s in self.symbols}
        self._ts = {s: deque(maxlen=maxlen) for s in self.symbols}
        self.last_ts: float = 0.0

    def append(self, bar: Bar) -> None:
        s = bar.symbol
        if s not in self._c:
            self.symbols.append(s)
            for d in (self._o, self._h, self._l, self._c, self._v, self._ts):
                d[s] = deque(maxlen=self.maxlen)
        self._o[s].append(bar.open)
        self._h[s].append(bar.high)
        self._l[s].append(bar.low)
        self._c[s].append(bar.close)
        self._v[s].append(bar.volume)
        self._ts[s].append(bar.ts)
        self.last_ts = max(self.last_ts, bar.ts)

    def warm(self, bars: Dict[str, List[Bar]]) -> None:
        for s, blist in bars.items():
            for b in blist:
                self.append(b)

    def __len__(self) -> int:
        return max((len(x) for x in self._c.values()), default=0)

    def n(self, symbol: str) -> int:
        return len(self._c.get(symbol, ()))

    def arrays(self, symbol: str, n: Optional[int] = None) -> Dict[str, np.ndarray]:
        s = symbol
        out = {
            "o": np.asarray(self._o.get(s, ()), dtype=float),
            "h": np.asarray(self._h.get(s, ()), dtype=float),
            "l": np.asarray(self._l.get(s, ()), dtype=float),
            "c": np.asarray(self._c.get(s, ()), dtype=float),
            "v": np.asarray(self._v.get(s, ()), dtype=float),
        }
        if n and len(out["c"]) > n:
            out = {k: v[-n:] for k, v in out.items()}
        return out

    def closes(self, symbol: str, n: Optional[int] = None) -> np.ndarray:
        a = np.asarray(self._c.get(symbol, ()), dtype=float)
        return a[-n:] if n and len(a) > n else a

    def last_price(self, symbol: str) -> float:
        a = self._c.get(symbol)
        return float(a[-1]) if a else 0.0

    def returns_matrix(self, n: int = 120) -> Tuple[List[str], np.ndarray]:
        """Time-aligned simple-return matrix (rows = timestamps), no lookahead.

        Symbols trade on different clocks (equities keep office hours, synthetics
        run 24/7), so aligning by *timestamp* rather than by index is essential:
        index alignment silently corrupts every covariance and correlation.
        """
        series = {}
        for s in self.symbols:
            c = np.asarray(self._c.get(s, ()), dtype=float)
            t = np.asarray(self._ts.get(s, ()), dtype=float)
            if len(c) < 30:
                continue
            r = np.diff(c) / np.where(c[:-1] == 0, np.nan, c[:-1])
            series[s] = (t[1:], np.nan_to_num(r))
        if not series:
            return [], np.zeros((0, 0))
        # use only timestamps where EVERY symbol printed a bar: zero-padding
        # missing cells would decimate cross-covariances and corrupt the book.
        common = None
        for t, _ in series.values():
            common = t[-n:] if common is None else np.intersect1d(common, t[-n:], assume_unique=True)
        if common is None or len(common) < 30:
            common = np.unique(np.concatenate([t[-n:] for t, _ in series.values()]))[-n:]
        mat = np.zeros((len(common), len(series)))
        for j, (s, (t, r)) in enumerate(series.items()):
            idx = np.searchsorted(t, common)
            ok = (idx >= 0) & (idx < len(t))
            idx = idx[ok]
            mat[ok.nonzero()[0], j] = r[idx]
        return list(series.keys()), mat

    def realised_vol(self, symbol: str, n: int, bars_per_year: float) -> float:
        c = self.closes(symbol, n + 1)
        if len(c) < 5:
            return 0.0
        r = np.diff(c) / np.where(c[:-1] == 0, np.nan, c[:-1])
        return float(np.nanstd(r) * np.sqrt(bars_per_year))

    def to_quotes(self, spreads_bps: Dict[str, float]) -> Dict[str, Quote]:
        out = {}
        for s in self.symbols:
            p = self.last_price(s)
            if p <= 0:
                continue
            half = p * spreads_bps.get(s, 2.0) / 2.0 / 1e4
            v = float(self._v[s][-1]) if self._v.get(s) else 0.0
            out[s] = Quote(symbol=s, ts=self.last_ts, bid=p - half, ask=p + half, last=p, volume=v)
        return out
