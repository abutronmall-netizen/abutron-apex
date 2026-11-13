#!/usr/bin/env python3
"""Which agent actually earns its keep — measured at portfolio level.

Per-agent edge statistics are marginal: they score a signal in isolation and say
nothing about how it interacts with the fusion, the risk caps or the vol target.
Removing an agent with a *negative* memory edge can make things worse (it can be
acting as a brake). The only trustworthy answer is a counterfactual run.

    python3 scripts/agent_ablation.py                 # real data, daily
    python3 scripts/agent_ablation.py --freq 1h       # real data, hourly crypto
    python3 scripts/agent_ablation.py --synthetic --bars 2000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apex.backtest.runner import run_backtest            # noqa: E402
from apex.config import load_config                      # noqa: E402
from apex.data.real import build_real_panel_daily        # noqa: E402
from apex.data.synthetic import make_panel               # noqa: E402

AGENTS = ["trend", "mean_reversion", "breakout"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq", default="1D", choices=["1D", "1h"])
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--bars", type=int, default=2000)
    ap.add_argument("--warmup", type=int, default=300)
    a = ap.parse_args()

    cfg0 = load_config()
    if a.synthetic:
        panel = make_panel(cfg0, n_bars=a.bars)
        cfg0["universe"] = [u for u in cfg0["universe"]]
    else:
        panel = build_real_panel_daily(cfg0)
        cfg0["universe"] = [u for u in cfg0["universe"] if u["symbol"] in set(panel.symbols)]

    def run(label: str, disabled: str | None):
        cfg = load_config()
        cfg["universe"] = cfg0["universe"]
        cfg["system"]["memory_file"] = f"/tmp/abl_{label}.json"
        cfg["system"]["decision_log"] = f"/tmp/abl_{label}.jsonl"
        if disabled:
            cfg["agents"][disabled]["enabled"] = False
        rep = run_backtest(cfg, panel=panel, outdir=None, verbose=False)
        m = rep["metrics"]
        return m

    base = run("base", None)
    print(f"{'book':<22s} {'return':>9s} {'sharpe':>7s} {'maxDD':>7s} {'PF':>6s} {'trades':>7s}  marginal")
    print("-" * 82)
    print(f"{'all agents':<22s} {base['total_return']:>+8.2%} {base['sharpe']:>+7.2f} "
          f"{-base['max_drawdown']:>+7.2%} {base['profit_factor']:>6.2f} {base['trades']:>7d}")
    for ag in AGENTS:
        m = run(f"no_{ag}", ag)
        d_ret = m["total_return"] - base["total_return"]
        d_sh = m["sharpe"] - base["sharpe"]
        print(f"{'without ' + ag:<22s} {m['total_return']:>+8.2%} {m['sharpe']:>+7.2f} "
              f"{-m['max_drawdown']:>+7.2%} {m['profit_factor']:>6.2f} {m['trades']:>7d}  "
              f"ret {d_ret:+.2%}  sharpe {d_sh:+.2f}")
    print("-" * 82)
    print("marginal = the book's result minus the result without that agent.")
    print("positive => the agent adds value at portfolio level; negative => it is a drag.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
