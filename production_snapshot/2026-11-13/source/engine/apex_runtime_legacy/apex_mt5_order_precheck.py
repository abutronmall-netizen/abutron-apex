"""APEX Deriv DEMO broker order_precheck only: 13 symbols, two directions.

Uses the official MT5 order_check(), order_calc_profit(), order_calc_margin().
NEVER invokes mt5.order_send(). No automatic execution is authorized.
The precheck deliberately requires only the Deriv DEMO account.
"""
from datetime import datetime,timezone
from pathlib import Path
import json
import math
import MetaTrader5 as mt5

TERMINAL=r"C:\Program Files\MetaTrader 5\terminal64.exe"
MARKET=Path("/var/lib/apex/mt5-market/deriv_demo_bars.json")
MAX_TICK_AGE=150
BUFFER_MULTIPLIER=1.30


def atr(rows,length=14):
    tr=[]
    for prev,cur in zip(rows[-(length+2):-1],rows[-(length+1):]):
        p=prev["close"]
        tr.append(max(cur["high"]-cur["low"],abs(cur["high"]-p),abs(cur["low"]-p)))
    if len(tr)!=length+1:raise ValueError("ATR window incomplete")
    return sum(tr[-length:])/length


def main():
    data=json.loads(MARKET.read_text(encoding="utf8"))
    if data.get("source")!="Deriv DEMO MT5" or data.get("execution_enabled") is not False or len(data.get("data",{}))!=13:
        raise RuntimeError("Only a verified Deriv DEMO market snapshot permitted")
    t=datetime.fromisoformat(data["generated_at_utc"])
    if t.tzinfo is None or not 0<=(datetime.now(timezone.utc)-t).total_seconds()<660:
        raise RuntimeError("Stale broker OHLCV")
    if not mt5.initialize(TERMINAL,timeout=20000):
        raise RuntimeError("Broker terminal unavailable")
    try:
        account=mt5.account_info()
        terminal=mt5.terminal_info()
        if (account is None or terminal is None or not terminal.connected
                or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO
                or "deriv" not in str(account.company).lower()
                or "demo" not in str(account.server).lower()
                or str(account.currency).upper()!="USD"):
            raise RuntimeError("Deriv USD DEMO account verification failed")
        current=mt5.positions_get()
        if current is None:
            raise RuntimeError("Existing position exposure unavailable")
        if current:
            raise RuntimeError("Existing open broker positions; no order prechecks")
        out=[]
        for name, frames in data["data"].items():
            sym=mt5.symbol_info(name)
            quote=mt5.symbol_info_tick(name)
            for side in ("BUY","SELL"):
                entry={"symbol":name,"side":side,"status":"BLOCKED",
                       "submitted":False,"execution_authorized":False,
                       "order_check_accepted":False}
                try:
                    if sym is None or quote is None:
                        raise ValueError("Broker quote/spec unavailable")
                    age=(datetime.now(timezone.utc)-datetime.fromtimestamp(int(quote.time),timezone.utc)).total_seconds()
                    if not 0<=age<MAX_TICK_AGE:
                        raise ValueError("Broker tick stale")
                    price=float(quote.ask if side=="BUY" else quote.bid)
                    if price<=0 or not math.isfinite(price):
                        raise ValueError("Invalid tick price")
                    volume=float(sym.volume_min)
                    if volume<=0 or volume>sym.volume_max or sym.volume_step<=0:
                        raise ValueError("Broker minimum volume invalid")
                    m5atr=atr(frames["M5"])
                    point=float(sym.point)
                    if point<=0 or m5atr<=0:
                        raise ValueError("Invalid ATR/contract point")
                    distance=max(0.75*m5atr,(int(sym.trade_stops_level)+5)*point,20*point)
                    digits=int(sym.digits)
                    stop=round(price-distance if side=="BUY" else price+distance,digits)
                    target=round(price+1.5*distance if side=="BUY" else price-1.5*distance,digits)
                    if stop<=0 or target<=0:
                        raise ValueError("Protective prices invalid")
                    order_side=mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL
                    risk=mt5.order_calc_profit(order_side,name,volume,price,stop)
                    margin=mt5.order_calc_margin(order_side,name,volume,price)
                    if risk is None or margin is None or not math.isfinite(float(risk)) or not math.isfinite(float(margin)):
                        raise ValueError("Broker USD risk/margin calculator unavailable")
                    expected=max(0.,-float(risk))
                    buffered=BUFFER_MULTIPLIER*expected
                    entry.update({"min_lot":round(volume,5),"price":round(price,digits),
                        "sl":stop,"tp":target,
                        "expected_stop_loss_usd":round(expected,2),
                        "model_buffered_loss_usd":round(buffered,2),
                        "required_margin_usd":round(float(margin),2),
                        "tick_age_s":round(age,1),
                    })
                    # Report risk in USD; account-specific limits are set in
                    # the independent risk governor, not in broker order_check.
                    if float(margin) > account.margin_free * 0.1:
                        raise ValueError("Broker margin insufficient under 10 percent reserve")
                    filling=[]
                    if int(sym.filling_mode)&1:filling.append(mt5.ORDER_FILLING_FOK)
                    if int(sym.filling_mode)&2:filling.append(mt5.ORDER_FILLING_IOC)
                    if not filling:filling=[mt5.ORDER_FILLING_RETURN]
                    for fill in filling:
                        request={"action":mt5.TRADE_ACTION_DEAL,"symbol":name,
                                 "volume":volume,"type":order_side,
                                 "price":price,"sl":stop,"tp":target,
                                 "deviation":10,"magic":20261031,
                                 "comment":"APEX DEMO PRECHECK ONLY",
                                 "type_time":mt5.ORDER_TIME_GTC,"type_filling":fill}
                        checked=mt5.order_check(request)
                        if checked is None:
                            entry["broker_check"] = "No response from official MT5 order_check"
                            continue
                        entry["check_retcode"]=int(checked.retcode)
                        entry["filling_mode"]=int(fill)
                        entry["broker_check"]="Official MT5 order_check retcode"
                        if int(checked.retcode)==0:
                            entry["order_check_accepted"]=True
                            entry["status"]="PRECHECK_PASSED_NO_ORDER"
                            break
                    if not entry["order_check_accepted"]:
                        entry["status"]="BROKER_PRECHECK_REJECTED"
                except (ValueError,TypeError,AttributeError) as error:
                    entry["reason"]=str(error)[:140]
                # Actual end-of-check timestamp for this specific direction.
                # No trade has been submitted, whether the precheck passed or failed.
                entry["checked_at_utc"]=datetime.now(timezone.utc).isoformat()
                out.append(entry)
        report={"schema":"apex.mt5.order_precheck.v1",
                "source":"Deriv DEMO MT5",
                "generated_at_utc":datetime.now(timezone.utc).isoformat(),
                "single_loss_reference_usd":None,
                "aggregate_loss_reference_usd":None,
                "mode":"OFFICIAL_BROKER_PRECHECK_NO_ORDER",
                "orders_placed":0,
                "execution_authorized":False,"live_enabled":False,
                "checked":sum(x["order_check_accepted"] for x in out),
                "evaluated":len(out),"results":out}
        print(json.dumps(report,allow_nan=False,separators=(",",":")),flush=True)
    finally:
        mt5.shutdown()


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"schema":"apex.mt5.order_precheck.v1",
          "status":"BLOCKED","reason":type(exc).__name__,
          "orders_placed":0,"execution_authorized":False}),flush=True)
        raise SystemExit(1)
