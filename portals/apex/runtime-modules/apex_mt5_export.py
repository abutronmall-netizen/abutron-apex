"""APEX broker-only OHLCV exporter for the official MetaTrader5 Python API.

Runs inside the existing isolated Wine MT5 context as apexmt5. No login data
or account identifiers are exported, and absolutely no trading APIs are used.
"""
import json
from datetime import datetime, timezone
import math
import MetaTrader5 as mt5
import sys

TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOLS = (
    "Volatility 10 Index.0",
    "Volatility 25 Index.0",
    "Volatility 50 Index.0",
    "Volatility 75 Index.0",
    "Volatility 100 Index.0",
    "Crash 150 Index.0", "Crash 300 Index.0",
    "Crash 600 Index.0", "Crash 1000 Index.0",
    "Boom 150 Index.0", "Boom 300 Index.0",
    "Boom 600 Index.0", "Boom 1000 Index.0",
)
PERIODS = (
    ("M1", mt5.TIMEFRAME_M1),
    ("M5", mt5.TIMEFRAME_M5),
    ("M15", mt5.TIMEFRAME_M15),
    ("H1", mt5.TIMEFRAME_H1),
    ("H4", mt5.TIMEFRAME_H4),
    ("D1", mt5.TIMEFRAME_D1),
)


def main():
    if not mt5.initialize(TERMINAL, timeout=16000):
        raise RuntimeError("MT5 broker data unavailable")
    try:
        info = mt5.account_info()
        terminal = mt5.terminal_info()
        if (info is None or terminal is None or not terminal.connected
                or int(info.trade_mode) != mt5.ACCOUNT_TRADE_MODE_DEMO
                or "deriv" not in str(info.company).lower()
                or "demo" not in str(info.server).lower()):
            raise RuntimeError("The authenticated terminal must be Deriv DEMO")
        generated = datetime.now(timezone.utc).isoformat()
        exported = {}
        failures = []
        for symbol in SYMBOLS:
            details = mt5.symbol_info(symbol)
            if details is None:
                failures.append({"symbol": symbol, "problem": "symbol unavailable"})
                continue
            frames = {}
            for name, tf in PERIODS:
                records = mt5.copy_rates_from_pos(symbol, tf, 1, 400)
                if records is None or len(records) < 60:
                    failures.append({"symbol":symbol, "period":name, "problem":"insufficient candles"})
                    continue
                rows = []
                last = -1
                for r in records:
                    ts = int(r["time"])
                    o, h, l, c = (float(r[k]) for k in ("open", "high", "low", "close"))
                    if (ts <= last or not all(math.isfinite(v) and v > 0 for v in (o, h, l, c))
                            or h < max(o,c) or l > min(o,c)):
                        raise ValueError("Invalid broker candle for %s %s" % (symbol, name))
                    last = ts
                    rows.append({"time":ts, "open":o,"high":h,
                                 "low":l,"close":c,
                                 "volume":int(r["tick_volume"])})
                frames[name] = rows
            if frames:
                exported[symbol] = frames
        if len(exported) < 10 or any("M5" not in v or "H1" not in v for v in exported.values()):
            raise RuntimeError("Broker coverage insufficient; refusing snapshot")
        document = {"schema":"apex.mt5.market.v1","source":"Deriv DEMO MT5",
                    "generated_at_utc":generated, "execution_enabled":False,
                    "data":exported,"failures":failures}
        sys.stdout.write(json.dumps(document,separators=(",",":"),allow_nan=False))
        sys.stdout.write("\n")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Only non-secret, non-identifying errors are emitted.
        sys.stderr.write("APEX market export failed: %s\n" % type(e).__name__)
        sys.exit(1)
