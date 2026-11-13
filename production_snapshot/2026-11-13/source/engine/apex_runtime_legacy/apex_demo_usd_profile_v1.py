"""Broker-native USD SL/TP planner for user-specified APEX Deriv DEMO profiles.

Stops and targets are desired GROSS USD trade P&L, *not* MT5 points.
Commissions, swap, stop slippage, spread and account-level costs can alter net P&L.
Any unrepresentable quote, unsupported lot, minimum broker stop, or $140 daily
risk budget violation MUST block entry; never silently resize or widen protection.
No order_send calls here. Kronos is not imported.
"""
import math
from apex_demo_mt5_executor import Blocked, BUFFER, MAGIC, current_loss
import MetaTrader5 as mt5

PROFILE_SCHEMA="apex.deriv.user_profile.review.v1"
PROFILE_STATUS="ACTIVE_DERIV_DEMO_USD_GROSS"
EXPECTED_SOURCE_SHA="f965a4f6cf9380a3c48401480d49b2af2b235243f82890f8fc14d01073ad1d1d"

def validate_profile(payload):
    if (not isinstance(payload,dict) or payload.get("schema")!=PROFILE_SCHEMA or
        payload.get("status")!=PROFILE_STATUS or
        payload.get("source_sha256")!=EXPECTED_SOURCE_SHA or
        payload.get("lot_unit")!="lots" or
        payload.get("stop_loss_unit")!="USD_GROSS_BROKER_PNL" or
        payload.get("take_profit_unit")!="USD_GROSS_BROKER_PNL" or
        payload.get("live_trading_allowed") is not False):
        raise Blocked("OWNER_USD_PROFILE_NOT_VALIDATED")
    rows=payload.get("rows")
    if not isinstance(rows,list) or len(rows)!=13:
        raise Blocked("USD_PROFILE_SYMBOL_COVERAGE")
    from apex_fast_scanner import EXPECTED
    expected=set(EXPECTED)
    mapping={}
    for row in rows:
        if not isinstance(row,list) or len(row)!=4:raise Blocked("BAD_PROFILE_ROW")
        sym,lot,loss,target=row
        if sym in mapping or sym not in expected:
            raise Blocked("UNAPPROVED_PROFILE_SYMBOL")
        for n in (lot,loss,target):
            if type(n) not in (int,float) or not math.isfinite(n) or n<=0:
                raise Blocked("INVALID_USD_PROFILE_NUMBER")
        mapping[sym]={"volume":float(lot),"sl_usd":float(loss),"tp_usd":float(target)}
    if set(mapping)!=expected:raise Blocked("USD_PROFILE_SYMBOL_MISSING")
    return mapping

def broker_gross_price(symbol, side, lot, entry, target_usd, target_type, spec):
    """Invert the official broker order_calc_profit quote into one valid tick.

    BUY prices round UP, SELL prices round DOWN. This ensures the SL is
    no worse, and the TP no lower, than the requested GROSS USD at quote.
    """
    if target_type not in ("SL","TP") or side not in ("BUY","SELL"):
        raise Blocked("INVALID_USD_TARGET_DIRECTION")
    sign=1 if side=="BUY" else -1
    order_type=mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL
    direction=sign * (1 if target_type=="TP" else -1)
    point=float(spec.point)
    step=float(spec.trade_tick_size) or point
    if not all(math.isfinite(n) and n>0 for n in (point,step,entry,lot,target_usd)):
        raise Blocked("INVALID_BROKER_PRICE_INCREMENT")
    def calc(distance):
        dest=entry+direction*distance
        if dest<=step: return None
        value=mt5.order_calc_profit(order_type,symbol,lot,entry,dest)
        if value is None or not math.isfinite(float(value)):return None
        pnl=float(value)
        return pnl if target_type=="TP" else -pnl
    hi=step
    lo=0.0
    for _ in range(65):
        got=calc(hi)
        if got is None:raise Blocked("USD_TARGET_UNREACHABLE_VALID_PRICE")
        if got>=target_usd: break
        hi*=2
    else:
        raise Blocked("USD_TARGET_OUTSIDE_BROKER_RANGE")
    for _ in range(64):
        mid=(lo+hi)/2
        got=calc(mid)
        if got is None: raise Blocked("USD_TARGET_BROKER_CALC_FAILED")
        if got>=target_usd:hi=mid
        else:lo=mid
    raw=entry+direction*hi
    # BUY: round UP. SELL: round DOWN. Both preserve or improve requested
    # gross SL/TP protection; never inflate stop-loss risk through rounding.
    ticks=(math.ceil((raw/step)-1e-8) if side=="BUY" else math.floor((raw/step)+1e-8))
    quoted=round(ticks*step,int(spec.digits))
    if quoted<=step or (side=="BUY" and not
        (quoted<entry if target_type=="SL" else quoted>entry)) or (
        side=="SELL" and not (quoted>entry if target_type=="SL" else quoted<entry)):
        raise Blocked("INVALID_QUANTIZED_USD_TARGET")
    got=mt5.order_calc_profit(order_type,symbol,lot,entry,quoted)
    if got is None or not math.isfinite(float(got)):
        raise Blocked("USD_TARGET_QUOTE_VALIDATION_FAILED")
    monetary=float(got) * (1 if target_type=="TP" else -1)
    tolerance=min(1.0,max(0.02,target_usd*0.01))
    if not (0<monetary and (target_usd-monetary)<=tolerance and
            (monetary-target_usd)<=tolerance):
        raise Blocked("USD_TARGET_NOT_PRECISE_AT_BROKER_TICK")
    if target_type=="SL" and monetary>target_usd+tolerance:
        raise Blocked("USD_STOP_LOSS_OVERSHOOTS_REQUEST")
    return quoted,round(monetary,4)

def plan_usd_request(account,candidate,market_rows,profile,cap_usd):
    mapping=validate_profile(profile)
    symbol=candidate["symbol"];side=candidate["side"]
    if side not in ("BUY","SELL") or symbol not in mapping:
        raise Blocked("SYMBOL_NOT_CONFIGURED_IN_USD_PROFILE")
    settings=mapping[symbol]
    vol,stop_usd,target_usd=(settings[k] for k in ("volume","sl_usd","tp_usd"))
    spec=mt5.symbol_info(symbol);tick=mt5.symbol_info_tick(symbol)
    if spec is None or tick is None or int(spec.trade_mode)!=mt5.SYMBOL_TRADE_MODE_FULL:
        raise Blocked("BROKER_SYMBOL_NOT_TRADABLE")
    step=float(spec.volume_step);minimum=float(spec.volume_min)
    if (step<=0 or not minimum-1e-8<=vol<=float(spec.volume_max)+1e-8 or
        abs((vol-minimum)/step-round((vol-minimum)/step))>1e-5):
        raise Blocked("PROFILE_LOT_REJECTED_BY_BROKER")
    now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    if not 0<=now.timestamp()-int(tick.time)<=15:
        raise Blocked("BROKER_QUOTE_STALE")
    price=round(float(tick.ask if side=="BUY" else tick.bid),int(spec.digits))
    spread=float(tick.ask)-float(tick.bid)
    if not math.isfinite(spread) or spread<0:
        raise Blocked("INVALID_BROKER_SPREAD")
    sl,risk_gross=broker_gross_price(symbol,side,vol,price,stop_usd,"SL",spec)
    tp,profit_gross=broker_gross_price(symbol,side,vol,price,target_usd,"TP",spec)
    used=float(current_loss(account))
    if not math.isfinite(used) or not 0<cap_usd<=140:
        raise Blocked("USD_CAP_OR_ACCOUNT_LOSS_INVALID")
    # 30% buffer admits room for broker costs/slippage without claiming a
    # guaranteed outcome. A $100 SL with 30% buffer needs at least $130 headroom.
    buffered=round(risk_gross*BUFFER+0.005,4)
    if buffered>cap_usd-used:
        raise Blocked("PROFILE_USD_STOP_EXCEEDS_REMAINING_CAP")
    margin=mt5.order_calc_margin(mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL,
                                 symbol,vol,price)
    if margin is None or not math.isfinite(float(margin)) or float(margin)>float(account.margin_free)*.10:
        raise Blocked("BROKER_PROFILE_MARGIN_RESERVE_EXCEEDED")
    # Protect against minimum broker stops on both sides, including quote size.
    minimum_distance=float(spec.trade_stops_level)*float(spec.point)
    if (side=="BUY" and (price-sl<minimum_distance or tp-price<minimum_distance)) or (
        side=="SELL" and (sl-price<minimum_distance or price-tp<minimum_distance)):
        raise Blocked("USD_STOPS_TOO_CLOSE_FOR_BROKER_MINIMUM")
    order_type=mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL
    fillings=[]
    if int(spec.filling_mode)&1:fillings.append(mt5.ORDER_FILLING_FOK)
    if int(spec.filling_mode)&2:fillings.append(mt5.ORDER_FILLING_IOC)
    if not fillings:fillings.append(mt5.ORDER_FILLING_RETURN)
    for fill in fillings:
        req={"action":mt5.TRADE_ACTION_DEAL,"symbol":symbol,"volume":vol,
             "type":order_type,"price":price,"sl":sl,"tp":tp,"deviation":10,
             "magic":MAGIC,"comment":"APEX DEMO USD","type_time":mt5.ORDER_TIME_GTC,
             "type_filling":fill}
        check=mt5.order_check(req)
        if check is not None and int(check.retcode)==0:
            return req,{"model":"OWNER_USD_GROSS_V1",
                        "configured_volume":vol,
                        "configured_stop_usd":stop_usd,
                        "configured_target_usd":target_usd,
                        "broker_gross_stop_usd":risk_gross,
                        "broker_gross_target_usd":profit_gross,
                        "risk_buffered_estimate_usd":round(buffered,2),
                        "account_loss_used_usd":round(used,2),
                        "remaining_allowance_usd":round(cap_usd-used,2),
                        "broker_retcode":0,
                        "fees_included_in_targets":False}
    raise Blocked("BROKER_USD_PROTECTED_ORDER_CHECK_REJECTED")
