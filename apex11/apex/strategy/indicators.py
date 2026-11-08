"""Vectorised technical indicators (numpy only, no TA-Lib dependency)."""
from __future__ import annotations

import numpy as np

__all__ = [
    "sma", "ema", "wilders", "rsi", "true_range", "atr", "adx",
    "zscore", "bollinger", "donchian", "realised_vol", "slope",
    "percentile_rank", "returns", "clip",
]


def clip(x: float, lo: float, hi: float) -> float:
    return float(min(hi, max(lo, x)))


def returns(px: np.ndarray) -> np.ndarray:
    px = np.asarray(px, dtype=float)
    out = np.zeros_like(px)
    out[1:] = np.diff(px) / np.where(px[:-1] == 0, np.nan, px[:-1])
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def sma(px: np.ndarray, n: int) -> np.ndarray:
    px = np.asarray(px, dtype=float)
    n = max(1, int(n))
    if len(px) < n:
        return np.full_like(px, px.mean() if len(px) else 0.0)
    c = np.cumsum(np.insert(px, 0, 0.0))
    out = np.full_like(px, np.nan)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    out[: n - 1] = out[n - 1]
    return out


def ema(px: np.ndarray, n: int) -> np.ndarray:
    px = np.asarray(px, dtype=float)
    n = max(1, int(n))
    alpha = 2.0 / (n + 1.0)
    out = np.empty_like(px)
    if len(px) == 0:
        return out
    out[0] = px[0]
    for i in range(1, len(px)):
        out[i] = alpha * px[i] + (1 - alpha) * out[i - 1]
    return out


def wilders(x: np.ndarray, n: int) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    n = max(1, int(n))
    out = np.empty_like(x)
    if len(x) == 0:
        return out
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    high, low, close = map(lambda a: np.asarray(a, dtype=float), (high, low, close))
    prev = np.roll(close, 1)
    prev[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    return wilders(true_range(high, low, close), n)


def rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(np.asarray(close, dtype=float), prepend=np.asarray(close, dtype=float)[0])
    gain = np.clip(d, 0, None)
    loss = np.clip(-d, 0, None)
    ag, al = wilders(gain, n), wilders(loss, n)
    rs = np.divide(ag, np.where(al == 0, 1e-12, al))
    out = 100.0 - 100.0 / (1.0 + rs)
    return np.nan_to_num(out, nan=50.0)


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    """Wilder's ADX (trend-strength 0..100)."""
    high, low, close = map(lambda a: np.asarray(a, dtype=float), (high, low, close))
    up = np.diff(high, prepend=high[0])
    dn = -np.diff(low, prepend=low[0])
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = wilders(true_range(high, low, close), n)
    pdi = 100 * wilders(plus_dm, n) / np.where(tr == 0, 1e-12, tr)
    mdi = 100 * wilders(minus_dm, n) / np.where(tr == 0, 1e-12, tr)
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, 1e-12, pdi + mdi)
    return np.nan_to_num(wilders(dx, n), nan=0.0)


def zscore(px: np.ndarray, n: int) -> np.ndarray:
    px = np.asarray(px, dtype=float)
    m = sma(px, n)
    sd = np.sqrt(np.maximum(sma(px * px, n) - m * m, 1e-18))
    return np.nan_to_num((px - m) / sd, nan=0.0, posinf=0.0, neginf=0.0)


def bollinger(px: np.ndarray, n: int = 20, k: float = 2.0):
    m = sma(px, n)
    sd = np.sqrt(np.maximum(sma(np.asarray(px, float) ** 2, n) - m * m, 1e-18))
    return m - k * sd, m, m + k * sd


def donchian(high: np.ndarray, low: np.ndarray, n: int):
    high, low = np.asarray(high, float), np.asarray(low, float)
    n = max(1, int(n))
    upper = np.empty_like(high)
    lower = np.empty_like(low)
    for i in range(len(high)):
        lo = max(0, i - n + 1)
        upper[i] = high[lo:i + 1].max()
        lower[i] = low[lo:i + 1].min()
    return upper, lower


def realised_vol(px: np.ndarray, n: int, bars_per_year: float, method: str = "ewma") -> np.ndarray:
    r = returns(px)
    if method == "ewma":
        var = np.empty_like(r)
        lam = 1.0 - 2.0 / (n + 1.0)
        var[0] = r[0] ** 2
        for i in range(1, len(r)):
            var[i] = lam * var[i - 1] + (1 - lam) * r[i] ** 2
    else:
        var = sma(r * r, n)
    return np.sqrt(np.maximum(var, 0.0) * bars_per_year)


def slope(px: np.ndarray, n: int) -> np.ndarray:
    """Normalised linear-regression slope per bar, expressed in units of vol."""
    px = np.asarray(px, dtype=float)
    n = max(2, int(n))
    out = np.zeros_like(px)
    x = np.arange(n) - (n - 1) / 2.0
    denom = (x * x).sum()
    for i in range(n - 1, len(px)):
        w = px[i - n + 1:i + 1]
        out[i] = (x * (w - w.mean())).sum() / denom
    sd = np.std(np.diff(px), ddof=0) if len(px) > 2 else 0.0
    return out / sd if sd > 0 else out


def percentile_rank(x: np.ndarray, n: int) -> np.ndarray:
    x = np.asarray(x, float)
    out = np.zeros_like(x)
    for i in range(len(x)):
        lo = max(0, i - n + 1)
        w = x[lo:i + 1]
        out[i] = (w <= x[i]).mean() if len(w) else 0.5
    return out
