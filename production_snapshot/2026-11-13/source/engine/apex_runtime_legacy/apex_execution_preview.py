"""APEX durable execution-intent ledger and crash/retry-safe PREVIEW controller.

This component cannot submit orders. Every intent is blocked because the
root-owned DEMO release policy is locked and certification is incomplete.
It records enough immutable identity and broker precheck evidence to support
future idempotent order lifecycle testing.
"""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tempfile

ROOT=Path("/var/lib/apex/execution")
DB=ROOT/"intent_ledger.sqlite"
REPORT=ROOT/"latest.json"
SCAN=Path("/var/lib/apex/scanner/latest.json")
RISK=Path("/var/lib/apex/risk/latest.json")
PRECHECK=Path("/var/lib/apex/mt5-market/order_precheck_latest.json")
ACCOUNT=Path("/var/lib/apex/mt5-market/deriv_demo_account.json")
POLICY=Path("/etc/apex/trading-policy.json")


def load(p):
    try:
        result=json.loads(p.read_text(encoding="utf8"))
        return result if isinstance(result,dict) else None
    except (OSError,UnicodeError,ValueError):
        return None


def fresh(data,field,max_age=420):
    try:
        t=datetime.fromisoformat(data[field])
        age=(datetime.now(timezone.utc)-t).total_seconds()
        return t.tzinfo is not None and -30<=age<=max_age
    except (KeyError,ValueError,TypeError,AttributeError):
        return False


def init_db(path=DB):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    conn=sqlite3.connect(str(path),timeout=10,isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("""CREATE TABLE IF NOT EXISTS intents(
      signal_key TEXT PRIMARY KEY, first_seen_utc TEXT NOT NULL,
      symbol TEXT NOT NULL, side TEXT NOT NULL, m5_bar_time INTEGER NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('BLOCKED','UNCERTAIN','BROKER_CONFIRMED')),
      reason TEXT NOT NULL, estimated_loss_usd REAL,
      order_check_retcode INTEGER, evidence_sha256 TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS lifecycle_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      signal_key TEXT NOT NULL,
      timestamp_utc TEXT NOT NULL, state TEXT NOT NULL,
      reason TEXT NOT NULL)""")
    return conn


def store_preview(result,path=REPORT):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".execution-preview.")
    try:
        with os.fdopen(fd,"w",encoding="utf8") as output:
            json.dump(result,output,allow_nan=False,separators=(",",":"))
            output.flush();os.fsync(output.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def record_intents(conn,scanner,risk,precheck,account,policy):
    if not scanner or scanner.get("schema")!="apex.scanner.shadow.v1" or not fresh(scanner,"generated_at_utc",300):
        raise ValueError("Scanner missing/stale: no intents recorded")
    if not risk or risk.get("schema")!="apex.risk.governor.v1" or not fresh(risk,"generated_at_utc",300):
        raise ValueError("Risk governor missing/stale: no intents recorded")
    if not account or account.get("schema")!="apex.mt5.account.v1" or not fresh(account,"generated_at_utc",480):
        raise ValueError("Broker account missing/stale: no intents recorded")
    if not precheck or precheck.get("schema")!="apex.mt5.order_precheck.v1" or not fresh(precheck,"generated_at_utc",1200):
        raise ValueError("Broker order precheck missing/stale: no intents recorded")
    if not policy or policy.get("environment")!="DERIV_DEMO" or policy.get("automated_demo_execution") is not False or policy.get("live_trading") is not False:
        raise ValueError("Root trading policy unexpectedly permissive: stop")
    if (scanner.get("orders_enabled") is not False
            or risk.get("orders_enabled") is not False
            or account.get("execution_enabled") is not False
            or precheck.get("orders_placed")!=0):
        raise ValueError("Not in protected research mode")
    if risk.get("kill_switch")!="LOCKED" or risk.get("overall_status")!="BLOCKED":
        raise ValueError("Unexpected risk governor state")
    broker={(x.get("symbol"),x.get("side")):x for x in precheck.get("results",[]) if isinstance(x,dict)}
    assessments={x.get("symbol"):x for x in risk.get("proposals",[]) if isinstance(x,dict)}
    inserted=0
    present=[]
    conn.execute("BEGIN IMMEDIATE")
    try:
        for x in scanner.get("instruments",[]):
            if not isinstance(x,dict):continue
            side=x.get("proposal")
            if side not in ("BUY","SELL"):continue
            symbol=x.get("symbol")
            bar=x.get("last_closed_m5")
            if not isinstance(symbol,str) or not isinstance(bar,int) or bar<=0:
                raise ValueError("Strategy proposal identity invalid")
            signal=f"apex_ema_rsi_mtf_research_v1|{symbol}|M5|{bar}|{side}"
            key=hashlib.sha256(signal.encode()).hexdigest()
            checked=broker.get((symbol,side),{})
            assessment=assessments.get(symbol,{})
            reasons=["RESEARCH_ONLY","ROOT_DEMO_KILL_SWITCH_LOCKED",
                     "NO_INDEPENDENT_EXECUTION_CERTIFICATION"]
            reasons.extend(assessment.get("blockers",[])[:6])
            if checked.get("order_check_accepted") is not True:
                reasons.append("BROKER_ORDER_PRECHECK_NOT_ACCEPTED")
            evidence={"symbol":symbol,"side":side,"bar":bar,
                      "scanner_generated":scanner.get("generated_at_utc"),
                      "precheck_generated":precheck.get("generated_at_utc"),
                      "broker_check_retcode":checked.get("check_retcode"),
                      "risk_blockers":risk.get("system_blockers",[])}
            digest=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()
            reason="|".join(dict.fromkeys(reasons))
            cursor=conn.execute("""INSERT OR IGNORE INTO intents
                (signal_key,first_seen_utc,symbol,side,m5_bar_time,state,reason,
                 estimated_loss_usd,order_check_retcode,evidence_sha256)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (key,datetime.now(timezone.utc).isoformat(),symbol,side,bar,
                 "BLOCKED",reason,checked.get("model_buffered_loss_usd"),
                 checked.get("check_retcode"),digest))
            if cursor.rowcount:
                inserted+=1
                conn.execute("""INSERT INTO lifecycle_events
                    (signal_key,timestamp_utc,state,reason) VALUES (?,?,?,?)""",
                    (key,datetime.now(timezone.utc).isoformat(),"BLOCKED",reason))
            existing=conn.execute("SELECT state FROM intents WHERE signal_key=?",(key,)).fetchone()
            if existing is None or existing[0]!="BLOCKED":
                raise RuntimeError("Unresolved or unexpected signal state; fail closed")
            present.append({"signal_key":key[:16],"symbol":symbol,"side":side,
                            "state":"BLOCKED","order_check_accepted":checked.get("order_check_accepted") is True,
                            "estimated_buffered_stop_usd":checked.get("model_buffered_loss_usd"),
                            "blockers":list(dict.fromkeys(reasons))[:10]})
        pending=conn.execute("""SELECT count(*) FROM intents WHERE state IN
            ('UNCERTAIN','BROKER_CONFIRMED')""").fetchone()[0]
        if pending:raise RuntimeError("Unreconciled broker order state, freeze")
        total=conn.execute("SELECT count(*) FROM intents").fetchone()[0]
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"schema":"apex.execution.preview.v1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"DEMO_EXECUTION_LOCKED","broker_orders_submitted":0,
        "live_enabled":False,"execution_authorized":False,
        "signal_candidates":len(present),"new_intents":inserted,
        "ledger_total_intents":total,"unreconciled_orders":pending,
        "intents":present}


def main():
    conn=init_db()
    try:
        result=record_intents(conn,load(SCAN),load(RISK),
                              load(PRECHECK),load(ACCOUNT),load(POLICY))
        store_preview(result)
        print(json.dumps({"status":result["status"],
             "new_intents":result["new_intents"],
             "total_intents":result["ledger_total_intents"],
             "broker_orders_submitted":0}),flush=True)
    except (OSError,ValueError,TypeError,sqlite3.DatabaseError,RuntimeError) as error:
        blocked={"schema":"apex.execution.preview.v1",
            "generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "status":"BLOCKED","broker_orders_submitted":0,"execution_authorized":False,
            "live_enabled":False,"reason":type(error).__name__,"intents":[]}
        store_preview(blocked)
        print(json.dumps(blocked),flush=True)
        raise SystemExit(1)
    finally:
        conn.close()


if __name__=="__main__":
    main()
