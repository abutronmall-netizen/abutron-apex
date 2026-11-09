"""APEX signal-to-execution routing, stage 1: deterministic fail-closed gates.

This module connects the approved broker-only EMA/RSI M5 proposal to an
eventually broker-executed single-position DEMO request. The root policy must
carry account-specific risk percentages, an explicitly enabled DEMO flag,
and independently reviewed execution certification before broker submission.
It does not import MT5 or submit orders.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import os
import tempfile

SCAN=Path("/var/lib/apex/scanner/latest.json")
MARKET=Path("/var/lib/apex/mt5-market/deriv_demo_bars.json")
ACCOUNT=Path("/var/lib/apex/mt5-market/deriv_demo_account.json")
GOVERNOR=Path("/var/lib/apex/risk/latest.json")
POLICY=Path("/etc/apex/trading-policy.json")
OUT=Path("/var/lib/apex/execution/signal_route_latest.json")

def read(path):
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else None
    except (OSError,ValueError,UnicodeError):return None

def delta_time(x,now):
    try:
        dt=datetime.fromisoformat(str(x).replace("Z","+00:00"))
        return (now-dt).total_seconds() if dt.tzinfo else None
    except (TypeError,ValueError,OverflowError):return None

def pct(x):
    return type(x) in (float,int) and math.isfinite(x) and 0<x<=100

def route(scan,market,account,governor,policy,now=None):
    now=now or datetime.now(timezone.utc)
    failures=[]
    if not policy or policy.get("schema")!="apex.trading.policy.v1" or policy.get("environment")!="DERIV_DEMO" or policy.get("live_trading") is not False:
        failures.append("INVALID_ROOT_DEMO_POLICY")
    if not policy or policy.get("automated_demo_execution") is not True:
        failures.append("DEMO_EXECUTION_NOT_AUTHORIZED_IN_ROOT_POLICY")
    trade_pct=policy.get("risk_per_trade_pct") if policy else None
    daily_pct=policy.get("max_daily_loss_pct") if policy else None
    if not pct(trade_pct) or not pct(daily_pct):
        failures.append("ACCOUNT_RISK_PERCENTAGES_NOT_CONFIGURED")
    if not account or account.get("schema")!="apex.mt5.account.v1" or account.get("source")!="Deriv DEMO MT5" or account.get("execution_enabled") is not False:
        failures.append("BROKER_ACCOUNT_UNVERIFIED")
        info={}
    else:
        info=account.get("account",{})
        if info.get("mode")!="DEMO" or info.get("broker")!="Deriv" or info.get("currency")!="USD":
            failures.append("NOT_DERIV_USD_DEMO")
        if account.get("history_complete") is not True:
            failures.append("BROKER_HISTORY_INCOMPLETE")
        age=delta_time(account.get("generated_at_utc"),now)
        if age is None or age < -30 or age>420:failures.append("BROKER_ACCOUNT_STALE")
        positions=account.get("positions")
        if not isinstance(positions,list) or len(positions)!=info.get("open_positions"):
            failures.append("BROKER_POSITION_RECONCILIATION_INVALID")
        elif positions:
            failures.append("EXISTING_OPEN_POSITIONS_REQUIRE_RECONCILIATION")
        if not isinstance(info.get("gross_negative_deal_cashflows_today_usd"),(int,float)):
            failures.append("BROKER_COMMISSION_ACCOUNTING_MISSING")
    if not market or market.get("schema")!="apex.mt5.market.v1" or market.get("source")!="Deriv DEMO MT5" or market.get("execution_enabled") is not False:
        failures.append("BROKER_MARKET_UNVERIFIED")
        bars={}
    else:
        bars=market.get("data",{})
        age=delta_time(market.get("generated_at_utc"),now)
        if age is None or age<-30 or age>420:failures.append("BROKER_MARKET_STALE")
    if not scan or scan.get("schema")!="apex.scanner.shadow.v1" or scan.get("source")!="Deriv DEMO MT5" or scan.get("orders_enabled") is not False or scan.get("symbol_count")!=13:
        failures.append("SCANNER_UNVERIFIED")
        proposals=[]
    else:
        proposals=scan.get("instruments",[])
        age=delta_time(scan.get("generated_at_utc"),now)
        if age is None or age<-30 or age>180:failures.append("SCANNER_STALE")
    if not governor or governor.get("schema")!="apex.risk.governor.v1" or governor.get("environment")!="DERIV_DEMO":
        failures.append("RISK_GOVERNOR_MISSING")
    else:
        # Existing governor has not yet certified broker execution.
        if governor.get("orders_enabled") is not True or governor.get("kill_switch")!="UNLOCKED" or governor.get("overall_status")!="APPROVED":
            failures.append("INDEPENDENT_RISK_APPROVAL_NOT_GRANTED")
        age=delta_time(governor.get("generated_at_utc"),now)
        if age is None or age<-30 or age>240:failures.append("RISK_GOVERNOR_STALE")
    candidate=None
    all_candidates=[]
    for x in proposals:
        if not isinstance(x,dict) or x.get("proposal") not in ("BUY","SELL"):continue
        symbol=x.get("symbol");side=x.get("proposal");bar=x.get("last_closed_m5")
        if side!=x.get("m5_signal") or not isinstance(symbol,str) or type(bar) is not int:
            continue
        if not 0<=now.timestamp()-(bar+300)<=240:continue
        market_rows=bars.get(symbol,{}).get("M5",[])
        if not market_rows or market_rows[-1].get("time")!=bar:continue
        if x.get("trade_ready") is not False or x.get("execution_authorized") is not False:
            failures.append("SCANNER_EXECUTION_SOURCE_CHANGED")
            continue
        key=hashlib.sha256(("apex_ema_rsi_mtf_research_v1|"+symbol+"|M5|"+str(bar)+"|"+side).encode()).hexdigest()
        all_candidates.append({
            "signal_key":key,"symbol":symbol,"side":side,"m5_bar_time":bar,
            "strategy":"apex_ema_rsi_mtf_research_v1",
            "risk_pct_requested":trade_pct if pct(trade_pct) else None,
            "max_daily_loss_pct_requested":daily_pct if pct(daily_pct) else None
        })
    if all_candidates:candidate=all_candidates[0]
    if not candidate:failures.append("NO_FRESH_QUALIFIED_M5_STRATEGY_SIGNAL")
    status="APPROVED_FOR_DEMO_EXECUTION" if not failures else "BLOCKED"
    return {
        "schema":"apex.signal_route.v1","generated_at_utc":now.isoformat(),
        "environment":"DERIV_DEMO","status":status,
        "broker_account_connected":bool(info.get("mode")=="DEMO"),
        "execution_allowed":status=="APPROVED_FOR_DEMO_EXECUTION",
        "live_enabled":False,
        "candidate":candidate,"qualified_count":len(all_candidates),
        "blockers":list(dict.fromkeys(failures)),
        "orders_submitted_by_router":0
    }

def atomic(path,value):
    path.parent.mkdir(exist_ok=True,parents=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".signal-route.")
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(value,f,allow_nan=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    data=route(read(SCAN),read(MARKET),read(ACCOUNT),read(GOVERNOR),read(POLICY))
    atomic(OUT,data)
    print(json.dumps({
        "status":data["status"],"broker_linked":data["broker_account_connected"],
        "qualified_signals":data["qualified_count"],"blockers":data["blockers"],
        "orders_submitted":data["orders_submitted_by_router"]}),flush=True)

if __name__=="__main__":main()
