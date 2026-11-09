import MetaTrader5 as mt5, json, datetime, math
p=r"C:\Program Files\MetaTrader 5\terminal64.exe"
assert mt5.initialize(p,timeout=16000), "terminal IPC unavailable"
try:
 a=mt5.account_info()
 assert a and a.trade_mode==mt5.ACCOUNT_TRADE_MODE_DEMO and "deriv" in str(a.company).lower()
 data=json.load(open("/var/lib/apex/mt5-market/deriv_demo_bars.json"))["data"]
 for name in list(data)[:6]:
  s=mt5.symbol_info(name); t=mt5.symbol_info_tick(name)
  print(json.dumps({"symbol":name,"bid":None if t is None else t.bid,"ask":None if t is None else t.ask,
   "last":None if t is None else t.last,"tick_epoch":None if t is None else t.time,
   "min_volume":None if s is None else s.volume_min,
   "point":None if s is None else s.point,
   "last_h1_close":data[name]["H1"][-1]["close"]}))
finally:mt5.shutdown()
