"""Offline demonstration with generated OHLC bars; NOT market data or performance proof."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from abutron_replacement import AbutronApex11SignalBridge
manifest=json.loads((Path(__file__).resolve().parent / "manifest_EXAMPLE_NOT_REAL_COSTS.json").read_text())
bridge=AbutronApex11SignalBridge(manifest["universe"])
for i in range(330):
    price=100000+10*math.sin(i/7)+2*i
    result=bridge.on_closed_candle({"symbol":"R_75","ts":1600000000+i*300,
        "open":price-3,"high":price+12,"low":price-15,"close":price,
        "volume":1000,"is_closed":True,"provenance":"authenticated_mt5"})
print(json.dumps(result,indent=2))
print("NOTE: fixture is synthetic; 'authenticated_mt5' is a contract stub, NOT a verified source")
