#!/usr/bin/env python3
"""Run the real backtest on **actual market data**.

Sources (no API keys): OKX (crypto), Nasdaq (US equities), FRED (FX + index levels).
Everything is cached under data_cache/ so the run is reproducible offline.

    python3 scripts/run_real.py                 # daily bars, ~4 years
    python3 scripts/run_real.py --refresh       # re-download
    python3 scripts/run_real.py --freq 1h       # hourly (crypto only until Yahoo cooperates)

The universe is intersected with whatever real data is available, so instruments
whose feed is unreachable are dropped instead of being simulated.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apex.backtest.runner import run_backtest          # noqa: E402
from apex.config import load_config                     # noqa: E402
from apex.data.real import build_real_panel, build_real_panel_daily  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="APEX real-data backtest")
    ap.add_argument("--config", default="config/default.yaml")
    ap.add_argument("--freq", default="1D", choices=["1D", "1h"])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--out", default="results/real")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--set", action="append", default=[], help="dotted override, e.g. agents.fusion.rebalance_every=5")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    cfg = load_config(a.config)
    for kv in a.set:
        k, _, v = kv.partition("=")
        node = cfg
        parts = k.split(".")
        for part in parts[:-1]:
            node = node[part]
        try:
            node[parts[-1]] = json.loads(v)
        except json.JSONDecodeError:
            node[parts[-1]] = v
    print(f"APEX real-data backtest · {a.freq} bars · {time.strftime('%Y-%m-%d %H:%M')}")
    panel = (build_real_panel_daily(cfg, refresh=a.refresh) if a.freq == "1D"
             else build_real_panel(cfg, refresh=a.refresh))
    if not panel.symbols:
        print("no real data available")
        return 1

    # intersect the configured universe with what we actually downloaded
    keep = set(panel.symbols)
    cfg["universe"] = [u for u in cfg["universe"] if u["symbol"] in keep]
    cfg["backtest"]["warmup_bars"] = a.warmup
    print(f"\nuniverse ({len(cfg['universe'])}): {[u['symbol'] for u in cfg['universe']]}")
    print(f"window: {time.strftime('%Y-%m-%d', time.gmtime(panel.ts[0]))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(panel.ts[-1]))}  ({len(panel)} bars)\n")

    rep = run_backtest(cfg, panel=panel, outdir=Path(a.out), verbose=a.verbose)
    m = rep["metrics"]
    b = m["benchmark"]
    print(f"  overrides: {a.set or 'none'}")
    print("=" * 62)
    print(f"  REAL DATA · {len(rep['config']['universe'])} instruments · {len(panel)} bars")
    print("=" * 62)
    print(f"  return        {m['total_return']:+.2%}   benchmark {b['total_return']:+.2%}   "
          f"excess {m['excess_return']:+.2%}")
    print(f"  cagr          {m['cagr']:+.2%}")
    print(f"  vol (ann)     {m['volatility']:.2%}")
    print(f"  sharpe        {m['sharpe']:+.2f}   sortino {m['sortino']:+.2f}")
    print(f"  max drawdown  -{m['max_drawdown']:.2%}   calmar {m['calmar']:+.2f}")
    print(f"  trades        {m['trades']}   win {m['win_rate']:.1%}   PF {m['profit_factor']}")
    print("-" * 62)
    for s, d in m["per_symbol"].items():
        print(f"    {s:<9s} pnl {d['pnl']:>10,.0f}   trades {d['trades']:>4d}")
    if m.get("per_regime"):
        print("-" * 62)
        for r, d in m["per_regime"].items():
            print(f"    {r:<10s} pnl {d.get('pnl', 0):>10,.0f}   bars {d.get('bars', 0)}")
    print("=" * 62)
    print(f"report -> {Path(a.out) / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
