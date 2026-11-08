"""Performance analytics for equity curves and trade lists."""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

SECONDS_PER_YEAR = 365.25 * 24 * 3600


def _drawdown(eq: np.ndarray) -> Tuple[float, int]:
    peak = np.maximum.accumulate(eq)
    dd = eq / np.where(peak == 0, np.nan, peak) - 1.0
    dd = np.nan_to_num(dd)
    i = int(np.argmin(dd))
    return float(-dd.min()), i


def compute_metrics(
    equity: Sequence[Tuple[float, float]],
    trades: List[Dict[str, Any]] | None = None,
    start_equity: float | None = None,
    bars_per_year: float | None = None,
) -> Dict[str, Any]:
    if len(equity) < 3:
        return {"error": "not enough equity points"}
    ts = np.array([p[0] for p in equity], dtype=float)
    if bars_per_year is None:
        from ..data.base import annualisation_from_ts
        bars_per_year = annualisation_from_ts(ts)
    eq = np.array([p[1] for p in equity], dtype=float)
    eq = np.nan_to_num(eq, nan=start_equity or 1.0)
    start_equity = start_equity or float(eq[0])
    years = max((ts[-1] - ts[0]) / SECONDS_PER_YEAR, 1e-6)
    rets = np.diff(eq) / np.where(eq[:-1] == 0, np.nan, eq[:-1])
    rets = np.nan_to_num(rets)

    total = eq[-1] / start_equity - 1.0
    cagr = (eq[-1] / start_equity) ** (1 / years) - 1 if eq[-1] > 0 else -1.0
    vol = float(np.std(rets) * np.sqrt(bars_per_year))
    sharpe = float(np.mean(rets) / (np.std(rets) + 1e-12) * np.sqrt(bars_per_year))
    downside = rets[rets < 0]
    sortino = float(np.mean(rets) / (np.std(downside) + 1e-12) * np.sqrt(bars_per_year)) if len(downside) else 0.0
    mdd, mdd_i = _drawdown(eq)
    calmar = float(cagr / mdd) if mdd > 1e-9 else 0.0
    # tail ratio: right tail vs left tail of the return distribution.
    # floored and clamped -> a near-flat equity curve can no longer emit 5e9.
    _p95 = float(np.percentile(rets, 95))
    _p5 = float(abs(np.percentile(rets, 5)))
    tail = float(np.clip(_p95 / max(_p5, 1e-6), 0.0, 10.0))
    _skew = float(np.nan_to_num(((rets - rets.mean()) ** 3).mean() / (rets.std() ** 3 + 1e-12)))
    _kurt = float(np.nan_to_num(((rets - rets.mean()) ** 4).mean() / (rets.std() ** 4 + 1e-12)))

    out: Dict[str, Any] = {
        "start": round(ts[0], 0),
        "end": round(ts[-1], 0),
        "days": round(years * 365.25, 1),
        "start_equity": round(start_equity, 2),
        "end_equity": round(float(eq[-1]), 2),
        "total_return": round(total, 4),
        "cagr": round(cagr, 4),
        "volatility": round(vol, 4),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_drawdown": round(mdd, 4),
        "max_dd_index": mdd_i,
        "calmar": round(calmar, 2),
        "tail_ratio": round(tail, 2),
        "hit_rate_daily": round(float((rets > 0).mean()), 3),
        "skew": round(_skew, 2),
        "kurtosis": round(_kurt, 2),
        "bars_per_year_used": round(float(bars_per_year), 1),
    }

    if trades:
        pnls = np.array([t.get("pnl", 0.0) for t in trades], dtype=float)
        closed = pnls[np.abs(pnls) > 1e-9]
        wins = closed[closed > 0]
        losses = closed[closed < 0]
        fees = float(sum(abs(t.get("notional", 0.0)) for t in trades))
        out.update({
            "trades": len(trades),
            "closed_trades": int(len(closed)),
            "win_rate": round(float(len(wins) / len(closed)), 3) if len(closed) else 0.0,
            "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if len(losses) and losses.sum() != 0 else float("inf") if len(wins) else 0.0,
            "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
            "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
            "realised_pnl": round(float(closed.sum()), 2),
            "traded_notional": round(fees, 2),
            "turnover_x": round(fees / max(start_equity, 1.0), 2),
        })
    return out
