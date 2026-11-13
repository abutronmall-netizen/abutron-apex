#!/usr/bin/env python3
"""APEX-DERIV — automatic signal-to-order pipeline for Deriv synthetic indices.

One loop, no human in it:

    tick/bar -> RegimeAgent -> SignalAgents -> PortfolioAgent -> RiskAgent
             -> ExecutionAgent -> broker (paper or Deriv DEMO)

Every cycle prints the full decision tape so you can audit signal -> order:

    10:31  R_75    trend_up   ADX 27.8  signals trend+0.62 breakout+0.41
           target -3.2%  ->  SELL 0.011 @ 74,243 (-3.2% of equity)  filled

Usage
    python3 scripts/run_deriv.py                     # paper, accelerated, prints tape
    python3 scripts/run_deriv.py --bars 2000         # finite run, prints a summary
    python3 scripts/run_deriv.py --live-demo         # route orders to a Deriv DEMO account
    python3 scripts/run_deriv.py --bar-seconds 2     # one simulated hour every 2s

With --live-demo the script requires DERIV_API_TOKEN and refuses anything that is
not a virtual (demo) account. Without the token it stays in paper mode.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apex.config import load_config  # noqa: E402
from apex.data.synthetic import SyntheticSource  # noqa: E402
from apex.engine import ApexEngine  # noqa: E402

SYMS = ["R_75", "R_100", "BOOM500", "CRASH500", "stpRNG"]


def _fmt_sig(sig) -> str:
    sign = "+" if sig["score"] >= 0 else ""
    return f"{sig['agent']}{sign}{sig['score']:.2f}"


def tape_line(step: int, sim_ts: float, dec, fills: list) -> str:
    clock = time.strftime("%H:%M", time.gmtime(sim_ts))
    parts = [f"{clock} bar {step:>4d}"]
    regimes = dec.regimes or {}
    for s in SYMS:
        r = regimes.get(s, {})
        reg = r.get("regime", "-")[:10]
        sigs = " ".join(_fmt_sig(x) for x in dec.signals if x["symbol"] == s)
        w = dec.target_weights.get(s, 0.0)
        bit = f"  {s:<8s} {reg:<10s} w={w:+6.2%}"
        if sigs:
            bit += f"  [{sigs}]"
        parts.append(bit)
    holding = any("holding book" in n for n in (dec.notes or []))
    if holding:
        parts[0] += "   (holding book — re-optimises every N bars)"
    if fills:
        agg: dict = {}
        for f in fills:
            k = (f["symbol"], f["side"], round(f["price"], 6))
            if k in agg:
                agg[k]["qty"] += f["qty"]
                agg[k]["notional"] += f["notional"]
            else:
                agg[k] = dict(f)
        for f in agg.values():
            parts.append(f"  -> {f['side'].upper():4s} {f['symbol']:<8s} {f['qty']:>10.4f} @ "
                         f"{f['price']:>10.2f}  ({f['notional']:>9,.0f})  {f['reason']}")
    else:
        parts.append("  -> no order (inside hysteresis / all limits inside tolerance)")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="APEX-DERIV automatic signal-to-order")
    ap.add_argument("--config", default="config/deriv_only.yaml")
    ap.add_argument("--bars", type=int, default=0, help="0 = run forever")
    ap.add_argument("--bar-seconds", type=float, default=0.5,
                    help="wall-clock seconds per simulated hour")
    ap.add_argument("--warmup", type=int, default=400)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--live-demo", action="store_true",
                    help="route orders to a Deriv DEMO account (needs DERIV_API_TOKEN)")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()

    cfg = load_config(a.config)
    universe = [u["symbol"] for u in cfg["universe"]]
    assert set(universe) == set(SYMS), f"config is not Deriv-only: {universe}"

    broker = None
    if a.live_demo:
        raise SystemExit("This ABUTRON offline staging package forbids direct broker execution")
        token = os.environ.get("DERIV_API_TOKEN")
        if not token:
            print("!! --live-demo needs DERIV_API_TOKEN (create a DEMO token at app.deriv.com)")
            return 2
        from apex.brokers.adapters import DerivBroker
        from apex.data.deriv_ws import DerivClient
        client = DerivClient(app_id=str(cfg["live"]["deriv"]["app_id"]), token=token)
        client.start(universe)
        print(f"!! connected to Deriv DEMO account {client.account.get('login', '?')} "
              f"(virtual={client.account.get('is_virtual')})")
        broker = DerivBroker(cfg, client)

    print(f"APEX-DERIV  universe={universe}  mode={'deriv_demo' if broker else 'paper'}")
    engine = ApexEngine(cfg, mode="live_demo" if broker else "paper", seed=a.seed, broker=broker)
    source = SyntheticSource(cfg, seed=a.seed)

    hist = source.warmup(a.warmup)
    for i in range(a.warmup):
        engine.warmup({s: hist[s][i] for s in hist if i < len(hist[s])})

    stream = source.stream()
    step = warmup_done = 0
    peak = engine.broker.equity
    t0 = time.time()
    try:
        while True:
            bars = next(stream)
            step += 1
            n_before = len(engine.broker.trades())
            dec = engine.step(bars)
            fills = [t.to_dict() for t in engine.broker.trades()[n_before:]]
            peak = max(peak, engine.broker.equity)
            if not a.quiet:
                print(tape_line(step, dec.ts, dec, fills))
            if a.bars and step >= a.bars:
                break
            time.sleep(max(0.0, a.bar_seconds))
    except KeyboardInterrupt:
        print("\nstopped.")

    trades = engine.broker.trades()
    eq = engine.broker.equity
    print("\n" + "=" * 70)
    print(f"  bars {step}   equity {eq:,.2f}   pnl {eq - engine.broker.starting_equity:+,.2f} "
          f"({(eq / engine.broker.starting_equity - 1):+.2%})")
    print(f"  peak {peak:,.2f}   drawdown {(eq / peak - 1):.2%}   fills {len(trades)}   "
          f"runtime {time.time() - t0:.0f}s")
    by: dict[str, float] = {}
    for t in trades:
        by[t.symbol] = by.get(t.symbol, 0.0) + t.pnl
    for s in SYMS:
        print(f"    {s:<9s} pnl {by.get(s, 0.0):+10.2f}")
    print(f"  memory settled {engine.memory.settled} decisions")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
