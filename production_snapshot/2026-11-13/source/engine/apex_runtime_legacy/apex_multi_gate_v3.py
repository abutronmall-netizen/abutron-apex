"""APEX v3 DEMO-only multi-symbol signal admission: no account-wide dollar limit.
Pure read-only gate; broker-side protections are applied by execution planner.
"""
from datetime import datetime, timezone
from apex_fast_scanner import EXPECTED
from apex_demo_gate_v2 import time_age

def evaluate(policy,account,scanner,market,now=None):
    now=now or datetime.now(timezone.utc)
    blockers=[]
    if not isinstance(policy,dict) or policy.get("schema")!="apex.trading.policy.v1":
        blockers.append("OWNER_POLICY_SCHEMA_INVALID");policy={}
    if policy.get("environment")!="DERIV_DEMO" or policy.get("live_trading") is not False:
        blockers.append("DEMO_ONLY_POLICY_REQUIRED")
    if policy.get("automated_demo_execution") is not True:
        blockers.append("AUTO_DEMO_NOT_AUTHORIZED")
    if policy.get("max_demo_loss_usd") is not None:
        blockers.append("OLD_ACCOUNT_CAP_POLICY_PRESENT")
    if policy.get("max_concurrent_positions")!=13 or policy.get("max_positions_per_symbol")!=1:
        blockers.append("OWNER_CONCURRENCY_POLICY_INVALID")
    if not isinstance(account,dict) or account.get("schema")!="apex.mt5.account.v1" or account.get("source")!="Deriv DEMO MT5" or account.get("execution_enabled") is not False or account.get("live_enabled") is not False or account.get("history_complete") is not True:
        blockers.append("ACCOUNT_SNAPSHOT_SOURCE_INVALID");account={}
    a=account.get("account",{})
    if a.get("mode")!="DEMO" or a.get("broker")!="Deriv" or a.get("currency")!="USD":
        blockers.append("WRONG_BROKER_OR_LIVE_ACCOUNT")
    if a.get("allow_trading_account") is not True or a.get("allow_trading_terminal") is not True:
        blockers.append("BROKER_TRADING_PERMISSION_MISSING")
    for name,doc,maxage in (("ACCOUNT",account,420),("SCANNER",scanner,180),("MARKET",market,420)):
        try:
            elapsed=time_age(doc["generated_at_utc"],now)
            if not -30<=elapsed<=maxage:blockers.append(name+"_STALE")
        except (KeyError,TypeError,ValueError):blockers.append(name+"_INVALID_TIMESTAMP")
    if (not isinstance(scanner,dict) or scanner.get("schema")!="apex.scanner.shadow.v1" or
        scanner.get("source")!="Deriv DEMO MT5" or scanner.get("orders_enabled") is not False or
        scanner.get("symbol_count")!=13 or len(scanner.get("instruments",[]))!=13):
        blockers.append("SCANNER_NOT_VALIDATED");scanner={}
    if (not isinstance(market,dict) or market.get("schema")!="apex.mt5.market.v1" or
        market.get("source")!="Deriv DEMO MT5" or market.get("execution_enabled") is not False or
        set(market.get("data",{}))!=set(EXPECTED)):
        blockers.append("MARKET_DATA_NOT_VALIDATED");market={}
    positions=account.get("positions")
    if not isinstance(positions,list) or len(positions)!=a.get("open_positions",-1):
        blockers.append("ACCOUNT_POSITION_SNAPSHOT_INCONSISTENT")
    candidates=[]
    for item in scanner.get("instruments",[]):
        if item.get("proposal") not in ("BUY","SELL") or item.get("m5_signal")!=item.get("proposal"):continue
        symbol=item.get("symbol");bar=item.get("last_closed_m5")
        if symbol not in EXPECTED or type(bar) is not int:continue
        try:
            if not 0<=now.timestamp()-(bar+300)<=180:continue
            frames=market["data"][symbol]
            if set(frames)!={"M1","M5","M15","H1","H4","D1"} or int(frames["M5"][-1]["time"])!=bar:continue
        except (KeyError,IndexError,TypeError,ValueError):continue
        candidates.append({"symbol":symbol,"side":item["proposal"],"m5_bar_time":bar})
    return {"schema":"apex.demo.multi.gate.v3","checked_utc":now.isoformat(),
            "status":"BLOCKED" if blockers else "READY",
            "blockers":list(dict.fromkeys(blockers)),"demo_only":True,
            "orders_allowed":not blockers,"account_loss_cap_usd":None,
            "max_concurrent_positions":13,"max_positions_per_symbol":1,
            "candidates":candidates}
