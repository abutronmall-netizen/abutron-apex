"""No-order broker-native APEX order_check probe for DEMO Volatility 75."""
import sys,json,os
from pathlib import Path
sys.path.insert(0,"/opt/apex/runtime")
import MetaTrader5 as mt5
from apex_demo_mt5_executor import verified_demo,plan_request,Blocked
market=Path(r"Z:\opt\apex\runtime\demo-feed\market.json")
try:
 data=json.loads(market.read_text())
 account=verified_demo(require_trading=True)
 try:
  cap=100.0
  pct=min(100,100*cap/float(account.equity))
  request,meta=plan_request(account,{"symbol":"Volatility 75 Index.0","side":"BUY"},data["data"]["Volatility 75 Index.0"],pct,pct)
  print(json.dumps({"status":"ORDER_CHECK_ONLY","symbol":request["symbol"],
                    "side":"BUY","minimum_volume":request["volume"],"has_stop":request["sl"]>0,
                    "has_target":request["tp"]>0,"model":meta,"orders_sent":0}),flush=True)
 finally:mt5.shutdown()
except (Blocked,ValueError,KeyError,TypeError) as e:
 print(json.dumps({"status":"BROKER_PREFLIGHT_BLOCKED","reason":str(e)[:140],"orders_sent":0}),flush=True)
 raise SystemExit(1)
