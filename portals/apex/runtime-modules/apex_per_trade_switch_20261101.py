"""Switch existing APEX Deriv DEMO basket positions to individual broker-native USD exits.
One-shot; no entry orders. Requires basket timer stopped and bridge lock.
"""
import argparse, json, math, os, sqlite3, sys
from pathlib import Path
sys.path.insert(0,"Z:\\opt\\apex\\runtime" if os.name=="nt" else "/opt/apex/runtime")
import MetaTrader5 as mt5
from apex_demo_mt5_executor import verified_demo, init_ledger, MAGIC, Blocked
from apex_multi_usd_planner_v3 import validate_profile,broker_gross_price

def path(name):
    return Path("Z:"+name.replace("/","\\") if os.name=="nt" else name)

def scan(profile):
    mapping=validate_profile(profile)
    if any(x["sl_usd"]!=50.0 or x["tp_usd"]!=100.0 for x in mapping.values()):
        raise Blocked("PER_TRADE_50_100_PROFILE_REQUIRED")
    verified_demo(require_trading=True)
    positions=mt5.positions_get(); pending=mt5.orders_get()
    if positions is None or pending is None: raise Blocked("BROKER_RECONCILIATION_UNAVAILABLE")
    if len(positions)>13:raise Blocked("ACCOUNT_EXCEEDS_13_POSITIONS")
    owned=[p for p in positions if int(p.magic)==MAGIC]
    if len({p.symbol for p in owned})!=len(owned):raise Blocked("DUPLICATE_SYMBOL")
    if any(o.symbol in {p.symbol for p in owned} for o in pending):raise Blocked("PENDING_ORDER_FOR_APEX_SYMBOL")
    conn=init_ledger(path=path("/var/lib/apex/demo-execution/attempts.sqlite"))
    try:
        rows=conn.execute("""SELECT signal_key,symbol,side,state,request_json,broker_order
                    FROM attempts WHERE state IN
                    ('PENDING','UNKNOWN','UNPROTECTED','OPEN_PROTECTED','OPEN_BASKET')""").fetchall()
        if any(r[3] not in ("OPEN_BASKET","OPEN_PROTECTED") for r in rows):
            raise Blocked("UNCERTAIN_BROKER_LEDGER_STATE")
        if len(rows)!=len(owned):raise Blocked("BROKER_LEDGER_ACTIVE_COUNT_MISMATCH")
        planned=[]
        for key,symbol,side,state,raw,ticket in rows:
            matches=[p for p in owned if int(p.ticket)==int(ticket)]
            if len(matches)!=1 or matches[0].symbol!=symbol:
                raise Blocked("BROKER_TICKET_NOT_RECONCILED")
            p=matches[0]; req=json.loads(raw)
            typ="BUY" if int(p.type)==mt5.POSITION_TYPE_BUY else "SELL"
            if typ!=side or abs(float(req["volume"])-float(p.volume))>1e-7:
                raise Blocked("POSITION_DIRECTION_OR_LOT_MISMATCH")
            conf=mapping[symbol]
            if conf["volume"]!=float(p.volume):
                raise Blocked("OWNER_LOT_MISMATCH_"+symbol)
            spec=mt5.symbol_info(symbol); tick=mt5.symbol_info_tick(symbol)
            if spec is None or tick is None:raise Blocked("BROKER_SYMBOL_OR_QUOTE_MISSING")
            sl,gross_sl=broker_gross_price(symbol,side,float(p.volume),float(p.price_open),50.0,"SL",spec)
            tp,gross_tp=broker_gross_price(symbol,side,float(p.volume),float(p.price_open),100.0,"TP",spec)
            # Broker SL/TP modifications have to respect the current quote,
            # not merely the original entry price.
            min_distance=float(spec.point)*max(int(spec.trade_stops_level),int(spec.trade_freeze_level))
            bid=float(tick.bid);ask=float(tick.ask)
            if side=="BUY" and (sl>bid-min_distance or tp<bid+min_distance):
                raise Blocked("BROKER_STOP_DISTANCE_OR_FREEZE_"+symbol)
            if side=="SELL" and (sl<ask+min_distance or tp>ask-min_distance):
                raise Blocked("BROKER_STOP_DISTANCE_OR_FREEZE_"+symbol)
            if state=="OPEN_PROTECTED" and (abs(float(p.sl)-sl)>1e-6 or abs(float(p.tp)-tp)>1e-6):
                raise Blocked("PARTIAL_MIGRATION_PROTECTION_DIFFERENCE")
            planned.append((key,p,req,sl,tp,gross_sl,gross_tp))
        return conn,planned
    except BaseException:
        conn.close();raise

def run(do_apply):
    profile=json.loads(path("/opt/apex/runtime/demo-feed/usd_profile.json").read_text())
    conn,planned=scan(profile)
    try:
        if not do_apply:
            print(json.dumps({"phase":"PREFLIGHT","broker":"Deriv DEMO","positions": [
             {"symbol":p.symbol,"ticket":int(p.ticket),"side":r["type"],"lots":p.volume,
             "sl_price":sl,"tp_price":tp,"gross_sl_usd":gs,"gross_tp_usd":gt}
             for k,p,r,sl,tp,gs,gt in planned],"new_orders":0}),flush=True)
            return
        changes=[]
        for key,p,req,sl,tp,gs,gt in planned:
            current=mt5.positions_get(ticket=int(p.ticket))
            if current is None or len(current)!=1:raise Blocked("POSITION_CHANGED_PRE_MODIFICATION")
            pos=current[0]
            if pos.symbol!=p.symbol or abs(float(pos.volume)-float(p.volume))>1e-7:
                raise Blocked("POSITION_MISMATCH_PRE_MODIFICATION")
            if abs(float(pos.sl)-sl)>1e-6 or abs(float(pos.tp)-tp)>1e-6:
                result=mt5.order_send({"action":mt5.TRADE_ACTION_SLTP,
                   "position":int(p.ticket),"symbol":p.symbol,"sl":sl,"tp":tp})
                if result is None or int(result.retcode)!=mt5.TRADE_RETCODE_DONE:
                    raise Blocked("BROKER_SLTP_REJECTED_"+p.symbol+"_"+str(getattr(result,"retcode",None)))
            confirm=mt5.positions_get(ticket=int(p.ticket))
            if confirm is None or len(confirm)!=1 or abs(float(confirm[0].sl)-sl)>1e-6 or abs(float(confirm[0].tp)-tp)>1e-6:
                raise Blocked("BROKER_SLTP_VERIFICATION_FAILED_"+p.symbol)
            req.update(sl=sl,tp=tp)
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur=conn.execute("""UPDATE attempts SET state='OPEN_PROTECTED',request_json=?
                            WHERE signal_key=? AND broker_order=? AND state IN ('OPEN_BASKET','OPEN_PROTECTED')""",
                            (json.dumps(req,sort_keys=True),key,int(p.ticket)))
                if cur.rowcount!=1:raise Blocked("LEDGER_TRANSITION_FAILED_"+p.symbol)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK");raise
            changes.append({"symbol":p.symbol,"ticket":int(p.ticket),"sl":sl,"tp":tp,"gross_sl_usd":gs,"gross_tp_usd":gt})
        print(json.dumps({"phase":"MIGRATED","positions":changes,"new_orders":0,"basket_exit_disabled_by_script":False}),flush=True)
    finally:conn.close();mt5.shutdown()

if __name__=="__main__":
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--preflight",action="store_true");g.add_argument("--apply",action="store_true")
    a=p.parse_args()
    try:run(a.apply)
    except Exception as e:
        print(json.dumps({"phase":"BLOCKED","reason":str(e)[:180]}),flush=True);sys.exit(1)
