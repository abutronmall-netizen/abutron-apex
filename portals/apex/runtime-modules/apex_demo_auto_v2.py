"""APEX continuous controlled DEMO driver. Never executes LIVE orders.

Uses the existing APEX broker-native SL/TP request planner and MT5 order_check.
Each cycle independently validates the owner USD cap, broker identity, M5
strategy, account loss and persisted order ledger. No Kronos dependency.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,"/opt/apex/runtime")
import MetaTrader5 as mt5
from apex_demo_gate_v2 import evaluate
from apex_fast_scanner import evaluate as scanner_evaluate
from apex_demo_mt5_executor import (
    read,verified_demo,current_loss,init_ledger,reserve,mark,Blocked,MAGIC
)
from apex_demo_usd_profile_v1 import validate_profile,plan_usd_request
# Wine Windows Python cannot access Unix files by Linux slash paths.
# Verified, root-owned, whitelist-only snapshots are staged before each cycle.
def wine_path(linux_path):
    return Path("Z:"+str(linux_path).replace("/","\\\\") ) if os.name=="nt" else Path(linux_path)

FEED=wine_path("/opt/apex/runtime/demo-feed")
POLICY=FEED/"policy.json"
ACCOUNT=FEED/"account.json"
SCANNER=FEED/"scanner.json"
MARKET=FEED/"market.json"
PROFILE=FEED/"usd_profile.json"
LEDGER=wine_path("/var/lib/apex/demo-execution/attempts.sqlite")
STATE=wine_path("/var/lib/apex/demo-execution/latest.json")
CAP_MAX=140.0

def save(data):
    STATE.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".demo-status-",dir=str(STATE.parent))
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(data,f,sort_keys=True,separators=(",",":"),allow_nan=False)
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,STATE)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def status(stage,reason=None,**kwargs):
    d={"schema":"apex.demo.execution.v1","checked_at_utc":datetime.now(timezone.utc).isoformat(),
       "mode":"DERIV_DEMO_ONLY","status":stage,"orders_sent_in_cycle":0}
    if reason:d["reason"]=str(reason)[:150]
    d.update(kwargs)
    # Count only orders with broker-confirmed protected positions, not shadow intents.
    try:
        if LEDGER.exists():
            c=sqlite3.connect(str(LEDGER),timeout=2)
            try:
                d["broker_confirmed_orders"]=c.execute(
                    "SELECT COUNT(*) FROM attempts WHERE state IN ('OPEN_PROTECTED','CLOSED')").fetchone()[0]
                d["unreconciled_attempts"]=c.execute(
                    "SELECT COUNT(*) FROM attempts WHERE state IN ('PENDING','UNKNOWN','UNPROTECTED')").fetchone()[0]
            finally:c.close()
        else:
            d["broker_confirmed_orders"]=0;d["unreconciled_attempts"]=0
    except sqlite3.DatabaseError:
        d["broker_confirmed_orders"]=None;d["unreconciled_attempts"]=None
    save(d)
    print(json.dumps(d,sort_keys=True),flush=True)
    return d

def reconcile(conn):
    pending=conn.execute("""SELECT signal_key,created_utc,symbol,side,state,broker_order,broker_deal
       FROM attempts WHERE state IN ('PENDING','UNKNOWN','UNPROTECTED','OPEN_PROTECTED')""").fetchall()
    if not pending:return "NO_PENDING"
    if len(pending)!=1: raise Blocked("MULTIPLE_UNRECONCILED_ATTEMPTS")
    key,created,symbol,side,state,ticket,deal=pending[0]
    if state!="OPEN_PROTECTED":raise Blocked("ATTEMPT_"+state+"_REQUIRES_MANUAL_REVIEW")
    positions=mt5.positions_get()
    if positions is None:raise Blocked("BROKER_POSITION_RECONCILIATION_FAILED")
    if any(int(p.ticket)==int(ticket) and int(p.magic)==MAGIC for p in positions):
        matched=[p for p in positions if int(p.ticket)==int(ticket) and int(p.magic)==MAGIC]
        if len(matched)!=1 or float(matched[0].sl)<=0 or float(matched[0].tp)<=0:
            mark(conn,key,"UNPROTECTED",order=ticket,deal=deal,error="MISSING_PROTECTIVE_STOPS")
            raise Blocked("UNPROTECTED_APEX_POSITION_REQUIRES_MANUAL_REVIEW")
        return "OPEN_PROTECTED"
    created_dt=datetime.fromisoformat(created)
    if created_dt.tzinfo is None:raise Blocked("LEDGER_TIME_UNKNOWN")
    history=mt5.history_deals_get(created_dt-timedelta(minutes=5),datetime.now(timezone.utc))
    if history is None:raise Blocked("CLOSE_HISTORY_NOT_RECONCILED")
    closed=any(int(h.position_id)==int(ticket) and int(h.entry) in
               (mt5.DEAL_ENTRY_OUT,mt5.DEAL_ENTRY_INOUT,mt5.DEAL_ENTRY_OUT_BY)
               for h in history)
    if not closed:
        mark(conn,key,"UNKNOWN",order=ticket,deal=deal,error="POSITION_MISSING_NO_CONFIRMED_CLOSE")
        raise Blocked("MISSING_POSITION_WITHOUT_CONFIRMED_CLOSE")
    mark(conn,key,"CLOSED",order=ticket,deal=deal)
    return "CLOSED_CONFIRMED"

def gate():
    policy=read(POLICY);account=read(ACCOUNT);scanner=read(SCANNER);market=read(MARKET)
    decision=evaluate(policy,account,scanner,market)
    return policy,account,scanner,market,decision

def run(submit):
    policy,account,scanner,market,decision=gate()
    usd_profile=read(PROFILE)
    validate_profile(usd_profile)
    # Broker independently checked even when snapshots claim to be DEMO.
    a=verified_demo(require_trading=submit)
    try:
        conn=init_ledger(path=LEDGER)
        try:
            ledger_state=reconcile(conn)
            # An existing broker-confirmed APEX position is not an entry failure.
            # Continue reconciliation, but block further entries while it is open.
            if ledger_state=="OPEN_PROTECTED":
                return status("POSITION_OPEN",risk_cap_usd=decision["max_demo_loss_usd"],
                              remaining_budget_usd=decision["remaining_budget_usd"],
                              ledger_reconciliation=ledger_state,
                              reason="Existing protected APEX position; additional entries held")
            if not decision["orders_allowed"]:
                return status("BLOCKED",",".join(decision["blockers"])[:150],
                              risk_cap_usd=decision["max_demo_loss_usd"],
                              remaining_budget_usd=decision["remaining_budget_usd"],
                              ledger_reconciliation=ledger_state)
            # Verify true broker loss in USD; includes entry commissions and
            # every other trading deal in the DEMO account, not just APEX.
            spent=current_loss(a)
            cap=float(decision["max_demo_loss_usd"])
            if cap>CAP_MAX or cap<=0 or spent>=cap:
                raise Blocked("USD_140_LOSS_CAP_EXHAUSTED")
            candidates=decision["candidates"]
            skipped_symbol_entries=[]
            for candidate in candidates:
                bar=candidate["m5_bar_time"];symbol=candidate["symbol"];side=candidate["side"]
                digest=hashlib.sha256(
                    ("apex_ema_rsi_mtf_research_v1|"+symbol+"|M5|"+str(bar)+"|"+side).encode()
                ).hexdigest()
                if conn.execute("SELECT 1 FROM attempts WHERE signal_key=?",(digest,)).fetchone():
                    continue
                frames=market["data"][symbol]
                s=scanner_evaluate(symbol,frames)
                if (s["proposal"]!=side or s["m5_signal"]!=side or
                    s["last_closed_m5"]!=bar or
                    not 0<=datetime.now(timezone.utc).timestamp()-(bar+300)<=180):
                    continue
                try:
                    req,model=plan_usd_request(
                        a,{**candidate,"signal_key":digest},frames,usd_profile,cap)
                except Blocked as problem:
                    # Symbol-specific USD-price/lot/cap mismatch is NOT
                    # permission to override account risk or send an order.
                    # Continue scanning another independently qualified symbol.
                    reason=str(problem)
                    symbol_rejections={
                        "PROFILE_USD_STOP_EXCEEDS_REMAINING_CAP",
                        "USD_STOPS_TOO_CLOSE_FOR_BROKER_MINIMUM",
                        "BROKER_USD_PROTECTED_ORDER_CHECK_REJECTED",
                        "BROKER_PROFILE_MARGIN_RESERVE_EXCEEDED",
                        "PROFILE_LOT_REJECTED_BY_BROKER",
                        "USD_TARGET_UNREACHABLE_VALID_PRICE",
                        "USD_TARGET_OUTSIDE_BROKER_RANGE",
                        "USD_TARGET_BROKER_CALC_FAILED",
                        "INVALID_QUANTIZED_USD_TARGET",
                        "USD_TARGET_QUOTE_VALIDATION_FAILED",
                        "USD_TARGET_NOT_PRECISE_AT_BROKER_TICK",
                        "USD_STOP_LOSS_OVERSHOOTS_REQUEST"
                    }
                    if reason not in symbol_rejections:
                        raise
                    skipped_symbol_entries.append({"symbol":symbol,"reason":reason})
                    continue
                # Fail closed if source policy changed since reading the broker.
                newpolicy=read(POLICY)
                if (newpolicy!=policy or newpolicy.get("automated_demo_execution") is not True or
                    newpolicy.get("live_trading") is not False):
                    raise Blocked("OWNER_POLICY_CHANGED_DURING_ORDER")
                if not submit:
                    return status("PREFLIGHT_PASS","MT5_ORDER_CHECK_ACCEPTED_NO_ORDER",
                                  risk_cap_usd=cap,loss_today_usd=round(spent,2),
                                  candidate={"symbol":symbol,"side":side,"bar_utc":bar},
                                  model_risk_usd=model["risk_buffered_estimate_usd"],
                                  configured_lot=model["configured_volume"],
                                  configured_stop_usd=model["configured_stop_usd"],
                                  configured_target_usd=model["configured_target_usd"])
                reserve(conn,{**candidate,"signal_key":digest},req)
                try:
                    result=mt5.order_send(req)
                except BaseException:
                    mark(conn,digest,"UNKNOWN",error="BROKER_SEND_EXCEPTION")
                    raise Blocked("BROKER_SEND_EXCEPTION_UNCERTAIN")
                if result is None:
                    mark(conn,digest,"UNKNOWN",error="EMPTY_MT5_RESULT")
                    raise Blocked("BROKER_RESULT_UNKNOWN")
                if int(result.retcode) not in (mt5.TRADE_RETCODE_DONE,mt5.TRADE_RETCODE_DONE_PARTIAL):
                    mark(conn,digest,"UNKNOWN",order=int(result.order),deal=int(result.deal),
                         error="BROKER_RETCODE_"+str(result.retcode))
                    raise Blocked("BROKER_REJECTED_OR_UNKNOWN_"+str(result.retcode))
                positions=mt5.positions_get()
                if positions is None:
                    mark(conn,digest,"UNKNOWN",error="NO_BROKER_POSITION_RESPONSE")
                    raise Blocked("BROKER_POSITION_CONFIRMATION_FAILED")
                matches=[p for p in positions if p.symbol==symbol and int(p.magic)==MAGIC]
                if len(matches)!=1 or float(matches[0].sl)<=0 or float(matches[0].tp)<=0:
                    mark(conn,digest,"UNPROTECTED",order=int(result.order),deal=int(result.deal),
                         error="PROTECTIVE_STOPS_NOT_CONFIRMED")
                    raise Blocked("UNPROTECTED_POSITION_REQUIRES_MANUAL_ATTENTION")
                ticket=int(matches[0].ticket)
                mark(conn,digest,"OPEN_PROTECTED",order=ticket,deal=int(result.deal))
                return status("OPEN_PROTECTED",risk_cap_usd=cap,loss_today_usd=round(spent,2),
                         candidate={"symbol":symbol,"side":side,"bar_utc":bar},
                         broker_position_ticket=ticket,broker_deal=int(result.deal),
                         stop_confirmed=True,model_risk_usd=model["risk_buffered_estimate_usd"],
                         configured_lot=model["configured_volume"],
                         configured_stop_usd=model["configured_stop_usd"],
                         configured_target_usd=model["configured_target_usd"],
                         usd_profile_source_sha=usd_profile["source_sha256"],
                         ledger_reconciliation="OPEN_PROTECTED",orders_sent_in_cycle=1)
            return status("NO_NEW_SIGNAL",
                          "Qualified USD-profile entries rejected by per-symbol safeguards"
                          if skipped_symbol_entries
                          else "No unattempted fresh qualified M5 entry",
                          risk_cap_usd=cap,loss_today_usd=round(spent,2),
                          skipped_profile_entries=skipped_symbol_entries,
                          ledger_reconciliation=ledger_state)
        finally:conn.close()
    finally:mt5.shutdown()

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--preflight",action="store_true")
    cli.add_argument("--cycle",action="store_true")
    args=cli.parse_args()
    if not args.preflight and not args.cycle:cli.error("choose --preflight or --cycle")
    try:
        result=run(submit=args.cycle)
        print(json.dumps({"cycle_complete":True,"result":result["status"],
                          "orders_sent":result["orders_sent_in_cycle"]}),flush=True)
    except (Blocked,OSError,ValueError,KeyError,TypeError,sqlite3.DatabaseError) as exc:
        status("BLOCKED",str(exc),risk_cap_usd=CAP_MAX)
        raise SystemExit(1)

if __name__=="__main__":main()
