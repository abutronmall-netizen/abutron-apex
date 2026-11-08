#!/usr/bin/env python3
"""Multi-seed robustness sweep — never judge a strategy on one lucky path."""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apex.backtest.runner import run_backtest  # noqa: E402
from apex.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=1600)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--out", default="results/sweep.json")
    ap.add_argument("--config", default=None)
    ap.add_argument("--set", action="append", default=[], metavar="A.B.C=VALUE",
                    help="override any config leaf, e.g. --set agents.fusion.memory_influence=1.0")
    a = ap.parse_args()

    cfg = load_config(a.config)
    for kv in a.set:
        key, _, val = kv.partition("=")
        node = cfg
        parts = key.split(".")
        for part in parts[:-1]:
            node = node[part]
        cur = node.get(parts[-1])
        node[parts[-1]] = (type(cur)(val) if isinstance(cur, (int, float, bool)) and not isinstance(cur, bool)
                           else (val.lower() in {"1", "true", "yes"} if isinstance(cur, bool) else val))
    print("config overrides:", a.set if a.set else "none")
    rows = []
    for k in range(a.seeds):
        seed = 1000 + k * 37
        r = run_backtest(cfg, n_bars=a.bars, seed=seed, outdir=False, verbose=False)
        m = r["metrics"]
        rows.append({"seed": seed, "return": m["total_return"], "sharpe": m["sharpe"],
                     "vol": m["volatility"], "mdd": m["max_drawdown"], "trades": m["trades"]})
        print(f"seed {seed:5d}  ret {m['total_return']:+.2%}  sharpe {m['sharpe']:+.2f}  "
              f"mdd {-abs(m['max_drawdown']):.2%}  trades {m['trades']}")

    def agg(key):
        vals = [r[key] for r in rows]
        return round(st.mean(vals), 4), round(st.median(vals), 4), round(st.pstdev(vals), 4)

    summary = {k: {"mean": agg(k)[0], "median": agg(k)[1], "stdev": agg(k)[2]}
               for k in ("return", "sharpe", "vol", "mdd", "trades")}
    print("\nmean return %+.2f%%  median %+.2f%%  stdev %.2f%%" %
          (summary["return"]["mean"] * 100, summary["return"]["median"] * 100,
           summary["return"]["stdev"] * 100))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"rows": rows, "summary": summary}, indent=2))
    print(f"written -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
