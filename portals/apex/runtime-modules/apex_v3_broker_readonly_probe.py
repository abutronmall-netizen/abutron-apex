"""Read-only: test all user USD profiles against current Deriv MT5 quote/profit APIs.
NO order_send, NO modifying position or active account.
"""
import json,sys
from pathlib import Path
sys.path.insert(0,"/opt/apex/runtime")
import MetaTrader5 as mt5
from apex_demo_mt5_executor import verified_demo,Blocked
from apex_multi_usd_planner_v3 import validate_profile,broker_gross_price,plan_usd_request
p=json.loads(Path(r"Z:\opt\apex\runtime\demo-feed\usd_profile.json").read_text())
market=json.loads(Path(r"Z:\opt\apex\runtime\demo-feed\market.json").read_text())
profiles=validate_profile(p)
a=verified_demo(require_trading=False)
try:
    allrows=[]
    for name,config in profiles.items():
        spec=mt5.symbol_info(name);tick=mt5.symbol_info_tick(name)
        if spec is None or tick is None:
            allrows.append({"symbol":name,"status":"NO_BROKER_QUOTE"})
            continue
        row={"symbol":name,"lot":config["volume"],"sl_usd":config["sl_usd"],"tp_usd":config["tp_usd"]}
        for side in ("BUY","SELL"):
            price=round(float(tick.ask if side=="BUY" else tick.bid),int(spec.digits))
            detail={}
            try:
                sl,loss=broker_gross_price(name,side,config["volume"],price,config["sl_usd"],"SL",spec)
                tp,profit=broker_gross_price(name,side,config["volume"],price,config["tp_usd"],"TP",spec)
                detail={"sl":sl,"tp":tp,"gross_sl_usd":loss,"gross_tp_usd":profit}
                try:
                    request,meta=plan_usd_request(a,{"symbol":name,"side":side},market["data"][name],p,None)
                    detail["admission"]="PASS_BROKER_ORDER_CHECK_NO_SEND"
                    detail["risk_buffer_usd"]=meta["risk_buffered_estimate_usd"]
                    detail["request_volume"]=request["volume"]
                except Blocked as e:
                    detail["admission"]="BLOCKED_"+str(e)
            except Blocked as e:
                detail["admission"]="TARGET_CONVERSION_BLOCKED_"+str(e)
            row[side]=detail
        print("PROFILE_AUDIT",json.dumps(row,allow_nan=False),flush=True)
        allrows.append(row)
    print("PROFILE_SUMMARY",json.dumps({
      "source_sha":p["source_sha256"],"count":len(allrows),
      "usd_conversion_pass":sum("gross_sl_usd" in r.get("BUY",{}) for r in allrows),
      "buy_broker_precheck_pass":sum(r.get("BUY",{}).get("admission")=="PASS_BROKER_ORDER_CHECK_NO_SEND" for r in allrows),
      "sell_broker_precheck_pass":sum(r.get("SELL",{}).get("admission")=="PASS_BROKER_ORDER_CHECK_NO_SEND" for r in allrows),
      "orders_sent":0,
    }),flush=True)
finally:
    mt5.shutdown()
