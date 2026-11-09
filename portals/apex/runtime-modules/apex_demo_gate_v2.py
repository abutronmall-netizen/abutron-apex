"""Independent APEX Deriv DEMO only execution gate. No MT5 imports, no order API."""
from datetime import datetime, timezone
import math

EXPECTED_CAP_USD=140.0
SYMBOL_COUNT=13

def time_age(raw,now):
    dt=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("tz required")
    return (now-dt).total_seconds()

def evaluate(policy,account,scanner,market,now=None):
    now=now or datetime.now(timezone.utc)
    failures=[]
    if not isinstance(policy,dict) or policy.get("schema")!="apex.trading.policy.v1":
        failures.append("POLICY_INVALID");policy={}
    if policy.get("environment")!="DERIV_DEMO" or policy.get("live_trading") is not False:
        failures.append("DEMO_ONLY_POLICY_REQUIRED")
    if policy.get("automated_demo_execution") is not True:
        failures.append("AUTOMATIC_DEMO_NOT_ENABLED")
    cap=policy.get("max_demo_loss_usd")
    if type(cap) not in (int,float) or not math.isfinite(cap) or not 0<cap<=EXPECTED_CAP_USD:
        failures.append("USD_140_CAP_MISSING");cap=None
    if not isinstance(account,dict) or account.get("schema")!="apex.mt5.account.v1" or account.get("source")!="Deriv DEMO MT5" or account.get("execution_enabled") is not False or account.get("live_enabled") is not False or account.get("history_complete") is not True:
        failures.append("ACCOUNT_SOURCE_NOT_VERIFIED");account={}
    a=account.get("account",{})
    if a.get("mode")!="DEMO" or a.get("broker")!="Deriv" or a.get("currency")!="USD":
        failures.append("WRONG_BROKER_ACCOUNT")
    if a.get("allow_trading_account") is not True or a.get("allow_trading_terminal") is not True:
        failures.append("BROKER_TRADING_NOT_PERMITTED")
    for name,doc,maxage in (("ACCOUNT",account,420),("SCANNER",scanner,180),("MARKET",market,420)):
        try:
            elapsed=time_age(doc["generated_at_utc"],now)
            if not -30<=elapsed<=maxage: failures.append(name+"_STALE")
        except (ValueError,TypeError,KeyError): failures.append(name+"_TIMESTAMP_INVALID")
    if not isinstance(scanner,dict) or scanner.get("schema")!="apex.scanner.shadow.v1" or scanner.get("source")!="Deriv DEMO MT5" or scanner.get("orders_enabled") is not False or scanner.get("symbol_count")!=SYMBOL_COUNT or len(scanner.get("instruments",[]))!=SYMBOL_COUNT:
        failures.append("SCANNER_INVALID");scanner={}
    if not isinstance(market,dict) or market.get("schema")!="apex.mt5.market.v1" or market.get("source")!="Deriv DEMO MT5" or market.get("execution_enabled") is not False or len(market.get("data",{}))!=SYMBOL_COUNT:
        failures.append("BROKER_BARS_INVALID")
    positions=account.get("positions")
    if not isinstance(positions,list) or len(positions)!=a.get("open_positions",None):
        failures.append("POSITION_RECONCILIATION_FAILED")
    elif positions: failures.append("EXISTING_POSITION")
    if a.get("open_positions",None)!=0: failures.append("BROKER_EXPOSURE_PRESENT")
    try:
        used=float(a["gross_negative_deal_cashflows_today_usd"])+max(0.,-float(a["floating_profit_usd"]))
        equity=float(a["equity_usd"])
        if not math.isfinite(used) or used<0 or not math.isfinite(equity) or equity<=0:
            raise ValueError
    except (KeyError,TypeError,ValueError,OverflowError):
        used=None;failures.append("BROKER_CASHFLOW_UNAVAILABLE")
    remaining=max(0.,cap-used) if cap is not None and used is not None else None
    if remaining is not None and remaining<=0:
        failures.append("DAILY_140_USD_CAP_EXHAUSTED")
    candidates=[]
    for item in scanner.get("instruments",[]):
        if not isinstance(item,dict) or item.get("proposal") not in ("BUY","SELL") or item.get("m5_signal")!=item.get("proposal"):
            continue
        symbol=item.get("symbol");bar=item.get("last_closed_m5")
        if not isinstance(symbol,str) or type(bar) is not int:continue
        try:
            if not 0<=now.timestamp()-(bar+300)<=180:continue
            frames=market["data"][symbol]
            if not isinstance(frames,dict) or len(frames)!=6 or frames["M5"][-1]["time"]!=bar:continue
        except (KeyError,TypeError,IndexError):continue
        candidates.append({"symbol":symbol,"side":item["proposal"],"m5_bar_time":bar})
    if not candidates: failures.append("NO_FRESH_M5_QUALIFIED_SIGNAL")
    return {"schema":"apex.demo.gate.v1","checked_utc":now.isoformat(),
            "status":"READY" if not failures else "BLOCKED",
            "blockers":list(dict.fromkeys(failures)),"demo_only":True,
            "orders_allowed":not failures,"max_demo_loss_usd":cap,
            "daily_negative_cashflows_usd":round(used,2) if used is not None else None,
            "remaining_budget_usd":round(remaining,2) if remaining is not None else None,
            "candidates":candidates}
