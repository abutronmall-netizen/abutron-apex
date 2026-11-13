"""APEX connection capability probe for the existing official MetaTrader5 Python API.
Do not log broker credentials, account IDs or send orders."""
import MetaTrader5 as mt5
import json
from datetime import datetime, timezone
path=r"C:\Program Files\MetaTrader 5\terminal64.exe"
if not mt5.initialize(path,timeout=15000):
 print(json.dumps({"ok":False,"error":"MT5 IPC not available"}))
else:
 try:
  a=mt5.account_info()
  if a is None or a.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO or "deriv" not in a.company.lower():
   print(json.dumps({"ok":False,"error":"Only authenticated Deriv DEMO broker data allowed"}))
  else:
   allsyms=mt5.symbols_get() or []
   filtered=[s.name for s in allsyms if any(t in s.name.lower() for t in ["volatility", "crash", "boom", "eurusd", "xauusd"])]
   samples=[]
   for name in filtered[:35]:
    rates=mt5.copy_rates_from_pos(name,mt5.TIMEFRAME_M5,0,120)
    samples.append({"symbol":name,"bars":0 if rates is None else len(rates),
                    "last_bar_utc":None if rates is None or len(rates)==0 else datetime.fromtimestamp(int(rates[-1]["time"]),timezone.utc).isoformat()})
   print(json.dumps({"ok":True,"broker_is_deriv_demo":True,"total_symbols":len(allsyms),"sample_symbols":samples},separators=(",",":")))
 finally:
  mt5.shutdown()
