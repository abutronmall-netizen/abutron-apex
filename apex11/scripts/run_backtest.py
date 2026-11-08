#!/usr/bin/env python3
"""Run a walk-forward backtest and write results/ artefacts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apex.backtest.runner import run_backtest  # noqa: E402
from apex.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="APEX backtest")
    ap.add_argument("--bars", type=int, default=None, help="number of hourly bars to simulate")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    cfg = load_config(a.config)
    res = run_backtest(cfg, n_bars=a.bars, seed=a.seed, outdir=a.out, verbose=not a.quiet)
    m = res["metrics"]
    return 0 if "error" not in m else 1


if __name__ == "__main__":
    raise SystemExit(main())
