"""APEX official Deriv MT5 DEMO extra timeframes — M3 & M30 only.

Read-only, no account credentials or order APIs. The six established scanner
timeframes remain unchanged. Every returned bar must be fully closed.
"""
import json
import math
from datetime import datetime,timezone
import MetaTrader5 as mt5

TERMINAL=r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOLS=(
    "Volatility 10 Index.0","Volatility 25 Index.0","Volatility 50 Index.0",
    "Volatility 75 Index.0","Volatility 100 Index.0",
    "Crash 150 Index.0","Crash 300 Index.0","Crash 600 Index.0",
    "Crash 1000 Index.0","Boom 150 Index.0","Boom 300 Index.0",
    "Boom 600 Index.0","Boom 1000 Index.0",
)
PERIODS=(("M3",mt5.TIMEFRAME_M3,180),("M30",mt5.TIMEFRAME_M30,1800))

def main():
    if not mt5.initialize(TERMINAL,timeout=16000):
        raise RuntimeError("MT5 terminal unavailable")
    try:
        a=mt5.account_info();term=mt5.terminal_info()
        if (a is None or term is None or not term.connected
            or a.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO
            or "deriv" not in str(a.company).lower()
            or "demo" not in str(a.server).lower()
            or str(a.currency).upper()!="USD"):
            raise RuntimeError("Only Deriv USD DEMO allowed")
        now=datetime.now(timezone.utc)
        data={}
        for symbol in SYMBOLS:
            values={}
            for tf,period,seconds in PERIODS:
                rates=mt5.copy_rates_from_pos(symbol,period,1,4)
                if rates is None or len(rates)<2:
                    raise ValueError("Missing closed broker candles: "+symbol+" "+tf)
                rows=[]
                for bar in rates:
                    stamp=int(bar["time"])
                    if stamp+seconds>now.timestamp()-1:
                        raise ValueError("Nonclosed bar: "+symbol+" "+tf)
                    o,h,l,c=(float(bar[k]) for k in ("open","high","low","close"))
                    if (not all(math.isfinite(v) and v>0 for v in (o,h,l,c))
                        or h<max(o,c) or l>min(o,c)):
                        raise ValueError("Broker OHLC invalid")
                    rows.append({"time":stamp,"open":o,"high":h,"low":l,"close":c,
                                 "volume":int(bar["tick_volume"])})
                if any(rows[i]["time"]>=rows[i+1]["time"] for i in range(len(rows)-1)):
                    raise ValueError("Unsorted M3/M30 bars")
                values[tf]=rows
            data[symbol]=values
        print(json.dumps({"schema":"apex.mt5.extra_candles.v1",
            "source":"Deriv DEMO MT5","generated_at_utc":now.isoformat(),
            "data":data,"orders_placed":0,"execution_enabled":False,
            "live_enabled":False},allow_nan=False,separators=(",",":")),flush=True)
    finally:mt5.shutdown()

if __name__=="__main__":
    try:main()
    except Exception as exc:
        import sys
        print("APEX extra-candle inspection failed: "+type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)
