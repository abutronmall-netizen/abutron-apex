"""APEX only: read current Deriv DEMO contract volume limits. No orders."""
import json
import MetaTrader5 as mt5
from pathlib import Path
import sys
sys.path.insert(0,"/opt/apex/runtime")
from apex_demo_mt5_executor import verified_demo
account=verified_demo(require_trading=False)
try:
    for symbol in ("Volatility 75 Index.0","Volatility 100 Index.0","Crash 1000 Index.0","Boom 1000 Index.0"):
        info=mt5.symbol_info(symbol)
        if info is None: print(json.dumps({"symbol":symbol,"status":"UNAVAILABLE"}));continue
        v=0.05
        minv=float(info.volume_min);step=float(info.volume_step);maxv=float(info.volume_max)
        valid=step>0 and minv-1e-7<=v<=maxv+1e-7 and abs((v-minv)/step-round((v-minv)/step))<1e-5
        print(json.dumps({"symbol":symbol,"requested_lot":v,"minimum_lot":minv,"lot_step":step,"maximum_lot":maxv,"requested_lot_valid":bool(valid),"account_mode":"DEMO"}),flush=True)
finally:
    mt5.shutdown()
