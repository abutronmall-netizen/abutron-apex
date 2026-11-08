"""Walk-forward backtest runner.

The *same* engine, agents and cost model used in paper trading are replayed bar by
bar over historical data. No vectorised shortcuts => no lookahead bugs.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from ..config import Cfg, load_config
from ..data.synthetic import make_panel
from ..engine import ApexEngine
from .metrics import compute_metrics

from ..paths import data_path

RESULTS = data_path("results")


def run_backtest(
    cfg: Optional[Cfg] = None,
    n_bars: Optional[int] = None,
    seed: Optional[int] = None,
    outdir: Optional[Path] = None,
    verbose: bool = True,
    panel=None,
) -> Dict[str, Any]:
    cfg = cfg or load_config()
    bt = cfg["backtest"]
    n_bars = int(n_bars or bt.get("n_bars") or 3200)
    warmup = int(bt.get("warmup_bars", 300))

    t0 = time.time()
    if panel is None:
        panel = make_panel(cfg, n_bars=n_bars, seed=seed)
    n_bars = len(panel)
    # full audit JSONL is off by default here; decisions land in report.json
    engine = ApexEngine(cfg, mode="backtest", seed=seed, log_decisions=False)

    for i in range(min(warmup, len(panel))):
        engine.warmup({s: panel.bar(s, i) for s in panel.symbols if panel.active[s][i]})
    if verbose:
        print(f"[apex] warmup done ({warmup} bars) in {time.time() - t0:.1f}s")

    for i in range(warmup, len(panel)):
        engine.step(
            {s: panel.bar(s, i) for s in panel.symbols if panel.active[s][i]},
            ts=float(panel.ts[i]),
        )
        if verbose and (i - warmup) % 500 == 0:
            eq = engine.broker.equity
            print(f"[apex] bar {i}/{len(panel)}  equity {eq:,.0f}  "
                  f"pos {len([p for p in engine.broker.positions.values() if p.qty])}")

    trades = [t.to_dict() for t in engine.broker.trades()]
    equity = engine.equity_curve
    # annualisation is always inferred from the panel's actual bar spacing
    from ..data.base import annualisation_from_ts
    bpy = annualisation_from_ts(panel.ts)
    metrics = compute_metrics(equity, trades, engine.broker.starting_equity, bars_per_year=bpy)
    metrics["bars_per_year_used"] = round(float(bpy), 1)

    # ---- benchmark: equal-weight buy & hold of the universe --------------
    bench = _benchmark(panel, warmup, engine.broker.starting_equity, bpy=bpy)
    metrics["benchmark"] = bench
    metrics["excess_return"] = round(metrics.get("total_return", 0.0) - bench.get("total_return", 0.0), 4)

    # ---- per-symbol attribution -----------------------------------------
    per_symbol: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        d = per_symbol.setdefault(t["symbol"], {"pnl": 0.0, "trades": 0, "notional": 0.0})
        d["pnl"] += t["pnl"]
        d["notional"] += abs(t["notional"])
        d["trades"] += 1
    for s, d in per_symbol.items():
        d["pnl"] = round(d["pnl"], 2)
        d["notional"] = round(d["notional"], 2)
    metrics["per_symbol"] = dict(sorted(per_symbol.items(), key=lambda kv: -kv[1]["pnl"]))

    out = {
        "config": {"n_bars": n_bars, "warmup": warmup, "mode": "backtest",
                   "data": "real" if panel is not None and getattr(panel, "source", "") == "real" else "synthetic",
                   "universe": engine.symbols, "seed": seed if seed is not None else cfg["system"]["seed"],
                   "runtime_s": round(time.time() - t0, 2)},
        "metrics": metrics,
        "equity_curve": [[round(t, 0), round(v, 2)] for t, v in equity],
        "trades": trades[-800:],
        "decisions": [d.to_dict() for d in engine.decisions[-120:]],
        "final_state": engine.state(),
    }

    if outdir is not False:
        _write(out, Path(outdir) if outdir else RESULTS, metrics, equity)
    if verbose:
        _print_summary(metrics, out["config"])
    return out


def _benchmark(panel, warmup: int, start_equity: float, bpy: float | None = None) -> Dict[str, Any]:
    syms = [s for s in panel.symbols]
    curves = []
    for s in syms:
        c = panel.c[s][warmup:]
        if len(c) > 2 and c[0] > 0:
            curves.append(c / c[0])
    if not curves:
        return {"total_return": 0.0, "volatility": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
    m = np.vstack(curves).mean(axis=0)
    eq = list(zip(panel.ts[warmup:], m * start_equity))
    mm = compute_metrics(eq, None, start_equity, bars_per_year=bpy)
    return {k: mm.get(k) for k in ("total_return", "volatility", "sharpe", "max_drawdown", "cagr")}


def _write(out: Dict[str, Any], outdir: Path, metrics: Dict[str, Any], equity) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(json.dumps(out, indent=2, default=str))
    with open(outdir / "equity.csv", "w", encoding="utf-8") as fh:
        fh.write("ts,equity\n")
        for t, v in equity:
            fh.write(f"{int(t)},{v:.2f}\n")
    with open(outdir / "trades.csv", "w", encoding="utf-8") as fh:
        fh.write("ts,symbol,side,qty,price,notional,pnl,reason,agent\n")
        for t in out["trades"]:
            fh.write(f"{int(t['ts'])},{t['symbol']},{t['side']},{t['qty']},{t['price']},"
                     f"{t['notional']},{t['pnl']},{t['reason']},{t['agent']}\n")
    (outdir / "report.md").write_text(_markdown(metrics, out["config"]), encoding="utf-8")


def _markdown(m: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    b = m.get("benchmark", {})

    def pct(x):
        return f"{x:+.2%}" if isinstance(x, (int, float)) else str(x)

    rows = [
        ("Total return", pct(m.get("total_return", 0))),
        ("Benchmark (EW buy & hold)", pct(b.get("total_return", 0))),
        ("Excess return", pct(m.get("excess_return", 0))),
        ("CAGR", pct(m.get("cagr", 0))),
        ("Volatility (ann.)", pct(m.get("volatility", 0))),
        ("Sharpe", m.get("sharpe")),
        ("Sortino", m.get("sortino")),
        ("Max drawdown", pct(-abs(m.get("max_drawdown", 0) or 0))),
        ("Calmar", m.get("calmar")),
        ("Trades", m.get("trades")),
        ("Win rate", pct(m.get("win_rate", 0) or 0)),
        ("Profit factor", m.get("profit_factor")),
        ("Turnover (x equity)", m.get("turnover_x")),
        ("Days simulated", m.get("days")),
    ]
    per = "\n".join(
        f"| {s} | {d['trades']} | {d['pnl']:+,.0f} | {d['notional']:,.0f} |"
        for s, d in (m.get("per_symbol") or {}).items()
    )
    return f"""# APEX backtest report

Generated by `scripts/run_backtest.py` · bars: {cfg['n_bars']} · warmup: {cfg['warmup']} · seed: {cfg['seed']}

| Metric | Value |
|---|---|
""" + "\n".join(f"| {k} | {v} |" for k, v in rows) + f"""

## Per-instrument attribution

| Symbol | Trades | Realised PnL | Notional traded |
|---|---|---|---|
{per}
"""


def _print_summary(m: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    b = m.get("benchmark", {})
    print("\n" + "=" * 62)
    print(f"  APEX backtest  ·  {cfg['n_bars']} bars  ·  {m.get('days')} days")
    print("=" * 62)
    print(f"  return        {m.get('total_return', 0):+8.2%}   (benchmark {b.get('total_return', 0):+.2%})")
    print(f"  cagr          {m.get('cagr', 0):+8.2%}")
    print(f"  vol (ann)     {m.get('volatility', 0):8.2%}")
    print(f"  sharpe        {m.get('sharpe', 0):8.2f}   sortino {m.get('sortino', 0):.2f}")
    print(f"  max drawdown  {-abs(m.get('max_drawdown', 0) or 0):8.2%}   calmar {m.get('calmar', 0):.2f}")
    print(f"  trades        {m.get('trades', 0):8d}   win rate {m.get('win_rate', 0):.1%}  "
          f"PF {m.get('profit_factor')}")
    print("=" * 62 + "\n")
