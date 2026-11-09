"""APEX profile risk inspection, NO ORDER SEND or modification."""
import json, math, sys
from pathlib import Path
import MetaTrader5 as mt5
sys.path.insert(0,"/opt/apex/runtime")
from apex_demo_mt5_executor import verified_demo,atr
profile=[
("Volatility 10 Index.0",1,20,50),
("Volatility 25 Index.0",1,20,50),
("Volatility 50 Index.0",4,50,100),
("Volatility 75 Index.0",0.15,100,200),
("Volatility 100 Index.0",2,100,200),
("Crash 150 Index.0",1,20,50),
("Crash 300 Index.0",1,20,50),
("Crash 600 Index.0",0.5,50,100),
("Crash 1000 Index.0",0.2,100,200),
("Boom 150 Index.0",1,20,50),
("Boom 300 Index.0",1,20,50),
("Boom 600 Index.0",0.5,50,100),
("Boom 1000 Index.0",0.5,100,200)]
a=verified_demo(require_trading=False)
try:
  data=json.loads(Path(r"Z:\opt\apex\runtime\demo-feed\market.json").read_text())
  for sym,vol,sl,tp in profile:
    spec=mt5.symbol_info(sym)
    tick=mt5.symbol_info_tick(sym)
    if spec is None or tick is None:
      print("RISK",json.dumps({"symbol":sym,"error":"NO_BROKER_QUOTE"}));continue
    point=float(spec.point);price=float(tick.ask)
    frames=data["data"].get(sym,{})
    try:
      volatility=atr(frames["M5"])
      dyn_distance=max(volatility*.75, point*(int(spec.trade_stops_level)+5),point*20)
      current_min=float(spec.volume_min)
      std_loss=mt5.order_calc_profit(mt5.ORDER_TYPE_BUY,sym,vol,price,price-dyn_distance)
      current_min_loss=mt5.order_calc_profit(mt5.ORDER_TYPE_BUY,sym,current_min,price,price-dyn_distance)
      point_loss=mt5.order_calc_profit(mt5.ORDER_TYPE_BUY,sym,vol,price,price-sl*point)
      price_loss=mt5.order_calc_profit(mt5.ORDER_TYPE_BUY,sym,vol,price,price-sl)
      valid_lot=(current_min-1e-7<=vol<=float(spec.volume_max)+1e-7 and
         abs((vol-current_min)/float(spec.volume_step)-round((vol-current_min)/float(spec.volume_step)))<1e-4)
      out={"symbol":sym,"profile_lot":vol,"profile_sl":sl,"profile_tp":tp,
           "broker_min_lot":current_min,"broker_lot_step":float(spec.volume_step),
           "broker_point":point,"profile_lot_valid":bool(valid_lot),
           "apex_auto_lot":current_min,"apex_stop_type":"ATR_DERIVED",
           "apex_stop_distance_price":round(dyn_distance,7),
           "profile_atr_stop_gross_usd":round(max(0.,-std_loss),3) if std_loss is not None else None,
           "profile_atr_stop_buffered_usd":round(max(0.,-std_loss)*1.3,3) if std_loss is not None else None,
           "current_apex_buffered_risk_usd":round(max(0.,-current_min_loss)*1.3,3) if current_min_loss is not None else None,
           "profile_SL_if_MT5_points_usd":round(max(0.,-point_loss),3) if point_loss is not None else None,
           "profile_SL_if_price_distance_usd":round(max(0.,-price_loss),3) if price_loss is not None else None,
           "min_broker_stop_points":int(spec.trade_stops_level),
           "price":price}
      print("RISK",json.dumps(out,allow_nan=False))
    except Exception as exc:print("RISK",json.dumps({"symbol":sym,"error":type(exc).__name__+":"+str(exc)[:80]}))
finally:
  mt5.shutdown()
