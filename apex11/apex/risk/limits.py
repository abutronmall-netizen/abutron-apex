"""Portfolio risk maths: covariance, vol, parametric VaR, correlation clusters."""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

Z = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263}


def annualised_cov(rets: np.ndarray, bars_per_year) -> np.ndarray:
    """Annualise with a per-symbol bar count (assets trade different hours)."""
    if rets.size == 0:
        return np.zeros((0, 0))
    if rets.shape[0] < 3:
        return np.zeros((rets.shape[1], rets.shape[1]))
    cov = np.atleast_2d(np.cov(rets, rowvar=False))
    d = np.diag(np.diag(cov))
    cov = 0.85 * cov + 0.15 * d            # shrinkage => stable on short samples
    b = np.asarray(bars_per_year, dtype=float)
    if b.ndim == 0:
        scale = float(b)
    else:
        scale = np.sqrt(np.outer(b, b))    # D S D with D = diag(sqrt(bpy))
    return cov * scale


def portfolio_vol(weights: np.ndarray, cov: np.ndarray) -> float:
    if weights.size == 0 or cov.size == 0:
        return 0.0
    return float(np.sqrt(max(weights @ cov @ weights, 0.0)))


def parametric_var(weights: np.ndarray, cov: np.ndarray, confidence: float = 0.95) -> float:
    """1-day 95% VaR as a fraction of equity (positive number = loss)."""
    vol_annual = portfolio_vol(weights, cov)
    daily = vol_annual / np.sqrt(252.0)
    return float(Z.get(round(confidence, 3), 1.6449) * daily)


def corr_clusters(symbols: Sequence[str], cov: np.ndarray, threshold: float = 0.85) -> List[List[str]]:
    n = len(symbols)
    if n == 0 or cov.size == 0:
        return []
    sd = np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    corr = cov / np.outer(sd, sd)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            # Floating-point shrinkage may yield 0.8499999999999999 at an
            # exact 0.85 boundary. Include boundary ties within numerical
            # tolerance without lowering the correlation-risk threshold.
            if abs(corr[i, j]) >= threshold or np.isclose(abs(corr[i, j]), threshold, rtol=0.0, atol=1e-12):
                union(i, j)
    groups: Dict[int, List[str]] = {}
    for i, s in enumerate(symbols):
        groups.setdefault(find(i), []).append(s)
    return [g for g in groups.values() if len(g) > 1]


def scale_weights(weights: Dict[str, float], scale: float) -> Dict[str, float]:
    return {k: v * scale for k, v in weights.items()}


def gross(weights: Dict[str, float]) -> float:
    return float(sum(abs(v) for v in weights.values()))


def net(weights: Dict[str, float]) -> float:
    return float(sum(weights.values()))


def apply_cap(weights: Dict[str, float], cap: float) -> Dict[str, float]:
    g = gross(weights)
    if g <= cap or g <= 0:
        return dict(weights)
    return scale_weights(weights, cap / g)
