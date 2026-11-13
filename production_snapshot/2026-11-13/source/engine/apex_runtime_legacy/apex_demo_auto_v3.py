"""APEX Deriv DEMO multi-symbol execution v3.

One protected position per symbol, maximum 13 open across the broker account.
Each symbol uses its independent USD gross SL/TP and requested volume.
No account-wide USD admission budget. No LIVE account, no Kronos.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sqlite3, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,"/opt/apex/runtime")
import MetaTrader5 as mt5
from apex_demo_mt5_executor import (
    read,verified_demo,init_ledger,mark,Blocked,MAGIC
)
from apex_multi_gate_v3 import evaluate as evaluate_gate
from apex_multi_core_v3 import (
    reconcile_all,reserve_symbol,install_symbol_unique_index,ReconcileError
)
from apex_multi_usd_planner_v3 import validate_profile,plan_usd_request
from apex_fast_scanner import evaluate as scanner_evaluate,EXPECTED

def wp(unix):
    return Path("Z:"+unix.replace("/","\\") if os.name=="nt" else unix)
FEED=wp("/opt/apex/runtime/demo-feed")
POLICY=FEED/"policy.json";ACCOUNT=FEED/"account.json"
SCANNER=FEED/"scanner.json";MARKET=FEED/"market.json"
PROFILE=FEED/"usd_profile.json"
DB=wp("/var/lib/apex/demo-execution/attempts.sqlite")
STATE=wp("/var/lib/apex/demo-execution/latest.json")

def status(code,reason=None,**kw):
    doc={"schema":"apex.demo.execution.v1","controller_version":"multi_v3",
         "checked_at_utc":datetime.now(timezone.utc).isoformat(),
         "mode":"DERIV_DEMO_ONLY","status":code,
         "account_loss_cap_usd":None,"risk_cap_usd":None,
         "max_concurrent_positions":13,"max_positions_per_symbol":1,
         "orders_sent_in_cycle":0,"newly_opened":[]}
    if reason: doc["reason"]=str(reason)[:250]
    doc.update(kw)
    try:
        with sqlite3.connect(str(DB),timeout=3) as conn:
            doc["broker_confirmed_orders"]=conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE state IN ('OPEN_PROTECTED','CLOSED')").fetchone()[0]
            doc["unreconciled_attempts"]=conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE state IN ('PENDING','UNKNOWN','UNPROTECTED')").fetchone()[0]
            doc["open_apex_positions"]=conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE state='OPEN_PROTECTED'").fetchone()[0]
    except sqlite3.Error:
        doc["broker_confirmed_orders"]=None
        doc["unreconciled_attempts"]=None
        doc["open_apex_positions"]=None
    STATE.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".multi-v3-",dir=str(STATE.parent))
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(doc,f,allow_nan=False,sort_keys=True,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,STATE)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print(json.dumps(doc,sort_keys=True),flush=True)
    return doc

def cycle(submit):
    p=read(POLICY);a=read(ACCOUNT);s=read(SCANNER);m=read(MARKET);profile=read(PROFILE)
    validate_profile(profile)
    admission=evaluate_gate(p,a,s,m)
    # authenticate the real broker, regardless of cached snapshot claims
    broker=verified_demo(require_trading=submit)
    try:
        conn=init_ledger(path=DB)
        try:
            # Called before each trade and after restart. No unresolved order
            # may be re-submitted on another symbol.
            install_symbol_unique_index(conn)
            state=reconcile_all(conn,mt5,MAGIC,mark)
            open_symbols=set(state["open_symbols"])
            if not admission["orders_allowed"]:
                return status("BLOCKED",",".join(admission["blockers"]),
                    open_symbols=sorted(open_symbols),ledger_reconciliation="PASS")
            if len(state["broker_positions"])>=13:
                return status("FULL","All 13 symbol slots occupied",
                    open_symbols=sorted(open_symbols),ledger_reconciliation="PASS")
            sent=[];skipped=[]
            for cand in admission["candidates"]:
                sym=cand["symbol"];side=cand["side"];bar=cand["m5_bar_time"]
                if sym in open_symbols:
                    skipped.append({"symbol":sym,"reason":"SYMBOL_POSITION_ALREADY_OPEN"})
                    continue
                key=hashlib.sha256(
                    ("apex_ema_rsi_mtf_research_v1|"+sym+"|M5|"+str(bar)+"|"+side).encode()
                ).hexdigest()
                if conn.execute("SELECT 1 FROM attempts WHERE signal_key=?",(key,)).fetchone():
                    skipped.append({"symbol":sym,"reason":"CANDLE_ALREADY_ATTEMPTED"})
                    continue
                if sym not in EXPECTED:
                    raise Blocked("CANDIDATE_SYMBOL_OUTSIDE_13")
                now=datetime.now(timezone.utc)
                if not 0<=now.timestamp()-(bar+300)<=180:
                    skipped.append({"symbol":sym,"reason":"CANDIDATE_EXPIRED"});continue
                # Recompute exact M5+HTF signal on the same six closed candles.
                live_signal=scanner_evaluate(sym,m["data"][sym])
                if (live_signal["proposal"]!=side or live_signal["m5_signal"]!=side
                    or live_signal["last_closed_m5"]!=bar):
                    skipped.append({"symbol":sym,"reason":"STRATEGY_CHANGED"});continue
                positions=mt5.positions_get();pending_orders=mt5.orders_get()
                if positions is None or pending_orders is None:
                    raise Blocked("POSITION_OR_ORDER_BROKER_API_FAILED")
                if len(positions)>=13:break
                if any(x.symbol==sym for x in positions):
                    skipped.append({"symbol":sym,"reason":"BROKER_SYMBOL_ALREADY_OCCUPIED"});continue
                # Don't bypass another pending order for this symbol.
                if any(o.symbol==sym for o in pending_orders):
                    skipped.append({"symbol":sym,"reason":"BROKER_SYMBOL_PENDING_ORDER"});continue
                account_now=mt5.account_info()
                term=mt5.terminal_info()
                if (account_now is None or term is None or not term.connected or
                    account_now.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO or
                    "deriv" not in str(account_now.company).lower() or
                    "demo" not in str(account_now.server).lower() or
                    str(account_now.currency).upper()!="USD"):
                    raise Blocked("DEMO_BROKER_IDENTITY_CHANGED")
                try:
                    req,model=plan_usd_request(
                        account_now,{**cand,"signal_key":key},m["data"][sym],profile,None)
                except Blocked as e:
                    skipped.append({"symbol":sym,"reason":str(e)[:100]})
                    continue
                if read(POLICY)!=p or read(PROFILE)!=profile:
                    raise Blocked("OWNER_POLICY_OR_PROFILE_CHANGED_DURING_EXECUTION")
                if not submit:
                    return status("PREFLIGHT_PASS","BROKER_ORDER_CHECK_ACCEPTED_NO_SEND",
                        candidate=cand,configured_lot=model["configured_volume"],
                        configured_stop_usd=model["configured_stop_usd"],
                        configured_target_usd=model["configured_target_usd"],
                        model_risk_usd=model["risk_buffered_estimate_usd"],
                        open_symbols=sorted(open_symbols),skipped=skipped)
                # Make a durable one-attempt reservation BEFORE touching the broker.
                reserve_symbol(conn,{**cand,"signal_key":key},req)
                try: result=mt5.order_send(req)
                except BaseException:
                    mark(conn,key,"UNKNOWN",error="EXCEPTION_BROKER_SUBMISSION")
                    raise Blocked("UNKNOWN_BROKER_SEND_RESULT")
                if result is None or int(result.retcode) not in (
                    mt5.TRADE_RETCODE_DONE,mt5.TRADE_RETCODE_DONE_PARTIAL):
                    mark(conn,key,"UNKNOWN",
                        order=int(result.order) if result is not None else None,
                        deal=int(result.deal) if result is not None else None,
                        error="EMPTY_OR_REJECTED_BROKER_RESULT")
                    raise Blocked("BROKER_RESULT_UNCERTAIN_REVIEW_REQUIRED")
                fresh=mt5.positions_get()
                if fresh is None: 
                    mark(conn,key,"UNKNOWN",order=int(result.order),deal=int(result.deal),
                         error="POST_SEND_POSITION_UNAVAILABLE")
                    raise Blocked("POST_SEND_RECONCILIATION_FAILED")
                matched=[x for x in fresh if x.symbol==sym and int(x.magic)==MAGIC]
                if len(matched)!=1:
                    mark(conn,key,"UNKNOWN",order=int(result.order),deal=int(result.deal),
                         error="POST_SEND_POSITION_MISMATCH")
                    raise Blocked("POST_SEND_POSITION_MISMATCH")
                position=matched[0]
                spec=mt5.symbol_info(sym)
                eps=(float(spec.point)/2+0.000001) if spec else 0.000001
                if (int(position.type)!=(mt5.POSITION_TYPE_BUY if side=="BUY" else mt5.POSITION_TYPE_SELL)
                    or abs(float(position.volume)-float(req["volume"]))>1e-7
                    or float(position.sl)<=0 or float(position.tp)<=0
                    or abs(float(position.sl)-float(req["sl"]))>eps
                    or abs(float(position.tp)-float(req["tp"]))>eps):
                    mark(conn,key,"UNPROTECTED",order=int(position.ticket),
                         deal=int(result.deal),error="PROTECTIVE_TERMS_NOT_CONFIRMED")
                    raise Blocked("POSITION_PROTECTION_UNCERTAIN_MANUAL_REVIEW")
                ticket=int(position.ticket)
                mark(conn,key,"OPEN_PROTECTED",order=ticket,deal=int(result.deal))
                open_symbols.add(sym)
                sent.append({"symbol":sym,"side":side,"ticket":ticket,"broker_deal":int(result.deal),
                             "lot":model["configured_volume"],"sl":req["sl"],"tp":req["tp"],
                             "stop_usd":model["configured_stop_usd"],
                             "target_usd":model["configured_target_usd"]})
            return status("OPEN_PROTECTED" if sent else "SCANNING",
                "Protected per-symbol DEMO orders submitted" if sent
                else "No fresh unattempted eligible signal",
                orders_sent_in_cycle=len(sent),newly_opened=sent,
                open_symbols=sorted(open_symbols),skipped=skipped,
                ledger_reconciliation="PASS")
        finally: conn.close()
    finally: mt5.shutdown()

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight",action="store_true")
    group.add_argument("--cycle",action="store_true")
    args=parser.parse_args()
    try:
        d=cycle(submit=args.cycle)
        print(json.dumps({"complete":True,"status":d["status"],
                          "orders_sent":d["orders_sent_in_cycle"]}),flush=True)
    except (Blocked,ReconcileError,sqlite3.Error,ValueError,TypeError,KeyError,OSError) as e:
        status("BLOCKED",str(e),orders_sent_in_cycle=0)
        raise SystemExit(1)

if __name__=="__main__":main()
