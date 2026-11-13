"""APEX broker-native guarded Deriv DEMO execution bridge.

MT5 official Python under the isolated existing Wine terminal. Does not use
external paid providers or unrelated original platforms. A broker order can
ONLY be sent by --execute-once after root policy, independent governor, and
account-specific percentage controls all grant approval.

Deployment remains PREVIEW while parameters/certification are outstanding.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys

sys.path.insert(0,"/opt/apex/runtime")
from apex_fast_scanner import evaluate as evaluate_strategy

import MetaTrader5 as mt5

POLICY=Path("/etc/apex/trading-policy.json")
ROUTE=Path("/var/lib/apex/execution/signal_route_latest.json")
SCANNER=Path("/var/lib/apex/scanner/latest.json")
MARKET=Path("/var/lib/apex/mt5-market/deriv_demo_bars.json")
GOVERNOR=Path("/var/lib/apex/risk/latest.json")
DB=Path("/var/lib/apex/demo-execution/attempts.sqlite")
TERMINAL=r"C:\Program Files\MetaTrader 5\terminal64.exe"
MAGIC=20261031
BUFFER=1.30

class Blocked(RuntimeError):
    pass

def read(path):
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict):raise Blocked("INVALID_DOCUMENT")
    return data

def age(t):
    dt=datetime.fromisoformat(str(t).replace("Z","+00:00"))
    if dt.tzinfo is None:raise Blocked("NO_UTC_TIMESTAMP")
    return (datetime.now(timezone.utc)-dt).total_seconds()

def finite(v):
    return type(v) in (float,int) and math.isfinite(v)

def authorize(policy,route,scan,market,governor):
    if (policy.get("schema")!="apex.trading.policy.v1"
        or policy.get("environment")!="DERIV_DEMO"
        or policy.get("live_trading") is not False
        or policy.get("automated_demo_execution") is not True):
        raise Blocked("ROOT_DEMO_EXECUTION_LOCKED")
    per=policy.get("risk_per_trade_pct");daily=policy.get("max_daily_loss_pct")
    if not (finite(per) and finite(daily) and 0<per<=100 and 0<daily<=100):
        raise Blocked("RISK_PERCENTAGES_MISSING")
    if (route.get("schema")!="apex.signal_route.v1"
        or route.get("environment")!="DERIV_DEMO"
        or route.get("status")!="APPROVED_FOR_DEMO_EXECUTION"
        or route.get("execution_allowed") is not True or route.get("live_enabled") is not False
        or not -30<=age(route["generated_at_utc"])<=90):
        raise Blocked("SIGNAL_ROUTE_NOT_APPROVED")
    if (governor.get("schema")!="apex.risk.governor.v1"
        or governor.get("overall_status")!="APPROVED"
        or governor.get("kill_switch")!="UNLOCKED"
        or governor.get("orders_enabled") is not True
        or not -30<=age(governor["generated_at_utc"])<=120):
        raise Blocked("INDEPENDENT_RISK_GOVERNOR_NOT_APPROVED")
    if (scan.get("schema")!="apex.scanner.shadow.v1"
        or scan.get("orders_enabled") is not False or scan.get("source")!="Deriv DEMO MT5"
        or not -30<=age(scan["generated_at_utc"])<=180):
        raise Blocked("SCANNER_NOT_FRESH")
    if (market.get("schema")!="apex.mt5.market.v1"
        or market.get("source")!="Deriv DEMO MT5"
        or market.get("execution_enabled") is not False
        or not -30<=age(market["generated_at_utc"])<=420):
        raise Blocked("MARKET_SOURCE_NOT_FRESH")
    candidate=route.get("candidate")
    if not isinstance(candidate,dict):raise Blocked("NO_SIGNAL")
    symbol=candidate.get("symbol");side=candidate.get("side");bar=candidate.get("m5_bar_time")
    if side not in ("BUY","SELL") or not isinstance(symbol,str) or type(bar) is not int:
        raise Blocked("BAD_SIGNAL_IDENTITY")
    if not 0<=datetime.now(timezone.utc).timestamp()-(bar+300)<=210:
        raise Blocked("SIGNAL_EXPIRED")
    data=market.get("data",{}).get(symbol)
    if not isinstance(data,dict) or len(data)!=6 or data["M5"][-1]["time"]!=bar:
        raise Blocked("BAR_NOT_LATEST")
    recalculated=evaluate_strategy(symbol,data)
    if recalculated["proposal"]!=side or recalculated["m5_signal"]!=side:
        raise Blocked("STRATEGY_NOT_REPRODUCIBLE")
    expected=hashlib.sha256(("apex_ema_rsi_mtf_research_v1|"+symbol+"|M5|"+str(bar)+"|"+side).encode()).hexdigest()
    if candidate.get("signal_key")!=expected:
        raise Blocked("SIGNAL_KEY_MISMATCH")
    return candidate,data,float(per),float(daily)

def init_ledger(path=DB):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    conn=sqlite3.connect(str(path),timeout=12,isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS attempts (
      signal_key TEXT PRIMARY KEY,
      created_utc TEXT NOT NULL,
      symbol TEXT NOT NULL,side TEXT NOT NULL,
      state TEXT NOT NULL,
      request_json TEXT NOT NULL,
      broker_order INTEGER,
      broker_deal INTEGER,
      error_code TEXT)""")
    return conn

def reserve(conn,candidate,request):
    conn.execute("BEGIN IMMEDIATE")
    try:
        # ANY prior attempt (including failed, unknown, unprotected) permanently
        # prohibits repeat submission for the same M5 signal.
        outstanding=conn.execute("""SELECT COUNT(*) FROM attempts WHERE state IN
           ('PENDING','UNKNOWN','UNPROTECTED','OPEN_PROTECTED')""").fetchone()[0]
        if outstanding:raise Blocked("UNRECONCILED_BROKER_ATTEMPT")
        existing=conn.execute("SELECT state FROM attempts WHERE signal_key=?",
                              (candidate["signal_key"],)).fetchone()
        if existing:raise Blocked("SIGNAL_ALREADY_ATTEMPTED")
        conn.execute("INSERT INTO attempts(signal_key,created_utc,symbol,side,state,request_json) VALUES (?,?,?,?,?,?)",
            (candidate["signal_key"],datetime.now(timezone.utc).isoformat(),
             candidate["symbol"],candidate["side"],"PENDING",json.dumps(request,sort_keys=True)))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

def mark(conn,key,state,order=None,deal=None,error=None):
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE attempts SET state=?,broker_order=?,broker_deal=?,error_code=? WHERE signal_key=?",
                     (state,order,deal,error,key))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK");raise

def verified_demo(require_trading=True):
    if not mt5.initialize(TERMINAL,timeout=18000):
        raise Blocked("BROKER_TERMINAL_UNAVAILABLE")
    a=mt5.account_info();t=mt5.terminal_info()
    if (a is None or t is None or not t.connected
        or a.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO
        or "deriv" not in str(a.company).lower()
        or "demo" not in str(a.server).lower()
        or str(a.currency).upper()!="USD"):
        raise Blocked("NOT_AUTHENTICATED_DERIV_USD_DEMO")
    if require_trading and (not a.trade_allowed or not t.trade_allowed or t.tradeapi_disabled):
        raise Blocked("MT5_TRADING_NOT_PERMITTED")
    return a

def current_loss(a):
    positions=mt5.positions_get()
    orders=mt5.orders_get()
    if positions is None or orders is None:
        raise Blocked("BROKER_POSITIONS_OR_ORDERS_NOT_RECONCILED")
    if positions or orders:
        raise Blocked("BROKER_EXPOSURE_ALREADY_PRESENT")
    now=datetime.now(timezone.utc)
    start=datetime(now.year,now.month,now.day,tzinfo=timezone.utc)
    deals=mt5.history_deals_get(start,now)
    if deals is None:raise Blocked("BROKER_DEAL_HISTORY_UNAVAILABLE")
    # Sum negative net cashflow of every trade deal; do not offset losses
    # against wins, and include entry/exit commission, fees and swap.
    negative=0.0
    for x in deals:
        if int(x.type) in (mt5.DEAL_TYPE_BUY,mt5.DEAL_TYPE_SELL):
            cash=float(x.profit)+float(x.commission)+float(x.swap)+float(x.fee)
            if not math.isfinite(cash):raise Blocked("BROKER_CASHFLOW_INVALID")
            negative+=max(0.0,-cash)
    floating=max(0.0,-float(a.profit))
    return negative+floating

def atr(rows,length=14):
    bars=rows[-(length+1):]
    if len(bars)!=length+1:raise Blocked("ATR_CANDLES_MISSING")
    tr=[]
    for before,after in zip(bars[:-1],bars[1:]):
        last=float(before["close"])
        tr.append(max(float(after["high"])-float(after["low"]),
                      abs(float(after["high"])-last),abs(float(after["low"])-last)))
    return sum(tr)/length

def plan_request(a,candidate,market_rows,trade_pct,daily_pct):
    name=candidate["symbol"];side=candidate["side"]
    spec=mt5.symbol_info(name)
    tick=mt5.symbol_info_tick(name)
    if spec is None or tick is None:raise Blocked("BROKER_SYMBOL_OR_QUOTE_UNAVAILABLE")
    if int(spec.trade_mode)!=mt5.SYMBOL_TRADE_MODE_FULL:
        raise Blocked("SYMBOL_NOT_FULLY_TRADABLE")
    tick_age=datetime.now(timezone.utc).timestamp()-int(tick.time)
    if not 0<=tick_age<=15:raise Blocked("STALE_LIVE_TICK")
    point=float(spec.point);volume=float(spec.volume_min)
    if volume<=0 or point<=0 or volume>float(spec.volume_max) or float(spec.volume_step)<=0:
        raise Blocked("INVALID_CONTRACT")
    price=float(tick.ask if side=="BUY" else tick.bid)
    spread=float(tick.ask)-float(tick.bid)
    volatility=atr(market_rows["M5"])
    if volatility<=0 or spread<0 or spread>volatility*.20:
        raise Blocked("SPREAD_EXCEEDS_VOLATILITY_LIMIT")
    distance=max(volatility*.75,point*(int(spec.trade_stops_level)+5),point*20)
    digits=int(spec.digits)
    sl=round(price-distance if side=="BUY" else price+distance,digits)
    tp=round(price+1.5*distance if side=="BUY" else price-1.5*distance,digits)
    if sl<=0 or tp<=0:raise Blocked("INVALID_PROTECTION")
    order_type=mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL
    loss=mt5.order_calc_profit(order_type,name,volume,price,sl)
    margin=mt5.order_calc_margin(order_type,name,volume,price)
    if loss is None or margin is None or not math.isfinite(float(loss)) or not math.isfinite(float(margin)):
        raise Blocked("BROKER_RISK_CALCULATOR_UNAVAILABLE")
    expected=max(0.,-float(loss))
    if expected<=0:raise Blocked("BROKER_STOP_LOSS_NOT_NEGATIVE")
    buffered=expected*BUFFER
    used=current_loss(a)
    per_cap=float(a.equity)*trade_pct/100
    day_cap=float(a.equity)*daily_pct/100
    if buffered>min(per_cap,day_cap-used):
        raise Blocked("ACCOUNT_PERCENTAGE_RISK_EXCEEDED")
    if float(margin)>float(a.margin_free)*.10:
        raise Blocked("ACCOUNT_MARGIN_RESERVE_EXCEEDED")
    filling=[]
    if int(spec.filling_mode)&1:filling.append(mt5.ORDER_FILLING_FOK)
    if int(spec.filling_mode)&2:filling.append(mt5.ORDER_FILLING_IOC)
    if not filling:filling.append(mt5.ORDER_FILLING_RETURN)
    for fill in filling:
        req={"action":mt5.TRADE_ACTION_DEAL,
             "symbol":name,"volume":volume,"type":order_type,
             "price":round(price,digits),"sl":sl,"tp":tp,
             "deviation":10,"magic":MAGIC,
             "comment":"APEX DEMO M5","type_time":mt5.ORDER_TIME_GTC,
             "type_filling":fill}
        check=mt5.order_check(req)
        if check is not None and int(check.retcode)==0:
            return req,{"risk_buffered_estimate_usd":round(buffered,2),
                        "account_loss_used_usd":round(used,2),
                        "single_trade_allowance_usd":round(per_cap,2),
                        "daily_loss_allowance_usd":round(day_cap,2),
                        "broker_retcode":0}
    raise Blocked("BROKER_PROTECTED_ORDER_CHECK_FAILED")

def run(allow_submit=False):
    policy=read(POLICY)
    route=read(ROUTE)
    scan=read(SCANNER)
    market=read(MARKET)
    governor=read(GOVERNOR)
    candidate,frames,per,daily=authorize(policy,route,scan,market,governor)
    if not allow_submit:
        return {"status":"POLICY_VALIDATED_NO_ORDER","symbol":candidate["symbol"],"orders_sent":0}
    # This is an explicitly separate --execute-once mode, never called by
    # research/scanner/dashboard services. The root-owned release lock and
    # risk approval are checked again immediately before the MT5 call.
    account=verified_demo()
    try:
        req,meta=plan_request(account,candidate,frames,per,daily)
        conn=init_ledger()
        try:
            reserve(conn,candidate,req)
            key=candidate["signal_key"]
            try:
                result=mt5.order_send(req)
            except Exception:
                mark(conn,key,"UNKNOWN",error="SEND_EXCEPTION")
                raise Blocked("BROKER_SEND_AMBIGUOUS")
            if result is None:
                mark(conn,key,"UNKNOWN",error="NO_BROKER_RESULT")
                raise Blocked("BROKER_SEND_AMBIGUOUS")
            ret=int(result.retcode)
            if ret not in (mt5.TRADE_RETCODE_DONE,mt5.TRADE_RETCODE_DONE_PARTIAL):
                mark(conn,key,"UNKNOWN",order=int(result.order),deal=int(result.deal),
                     error="BROKER_RETCODE_"+str(ret))
                raise Blocked("BROKER_SEND_NOT_CONFIRMED")
            positions=mt5.positions_get(symbol=candidate["symbol"])
            if positions is None:
                mark(conn,key,"UNKNOWN",order=int(result.order),deal=int(result.deal),
                     error="NO_POSITIONS_RESPONSE")
                raise Blocked("BROKER_CONFIRMATION_UNAVAILABLE")
            matches=[p for p in positions if int(p.magic)==MAGIC]
            if len(matches)!=1 or float(matches[0].sl)<=0 or float(matches[0].tp)<=0:
                mark(conn,key,"UNPROTECTED",order=int(result.order),deal=int(result.deal),
                     error="SERVER_STOPS_UNCONFIRMED")
                raise Blocked("BROKER_STOPS_NOT_CONFIRMED_URGENT_ATTENTION")
            mark(conn,key,"OPEN_PROTECTED",order=int(result.order),deal=int(result.deal))
            return {"status":"OPEN_PROTECTED","orders_sent":1,
                "symbol":candidate["symbol"],"side":candidate["side"],
                "broker_order":int(result.order),"broker_deal":int(result.deal),
                "stop_confirmed":True,"risk":meta}
        finally:
            conn.close()
    finally:
        mt5.shutdown()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute-once",action="store_true")
    parser.add_argument("--inspect-account",action="store_true")
    args=parser.parse_args()
    try:
        if args.inspect_account:
            account=verified_demo(require_trading=False)
            try:
                terminal=mt5.terminal_info()
                out={"status":"LINKED_DEMO","broker":"Deriv","currency":"USD",
                     "balance_usd":round(float(account.balance),2),
                     "equity_usd":round(float(account.equity),2),
                     "account_trade_allowed":bool(account.trade_allowed),
                     "terminal_trade_allowed":bool(terminal.trade_allowed),
                     "python_api_trade_allowed":not bool(terminal.tradeapi_disabled),
                     "orders_sent":0}
            finally:mt5.shutdown()
        else:
            out=run(allow_submit=args.execute_once)
        print(json.dumps(out,allow_nan=False),flush=True)
    except (Blocked,OSError,ValueError,KeyError,TypeError,sqlite3.DatabaseError) as exc:
        # No raw broker account IDs, login, password, comment or token is logged.
        print(json.dumps({"status":"BLOCKED","reason":str(exc)[:95],"orders_sent":0,
                          "live_enabled":False}),flush=True)
        raise SystemExit(1)

if __name__=="__main__":main()
