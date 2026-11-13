"""Crash/retry and safety tests for APEX execution-intent lifecycle ledger."""
import copy
import json
from datetime import datetime,timezone
from pathlib import Path
import tempfile
from apex_execution_preview import init_db,record_intents,load,SCAN,RISK,ACCOUNT,PRECHECK,POLICY

s=load(SCAN);r=load(RISK);a=load(ACCOUNT);p=load(PRECHECK);policy=load(POLICY)
now=datetime.now(timezone.utc).isoformat()
assert all(isinstance(x,dict) for x in (s,r,a,p,policy))
for doc in (s,r,a,p):
    doc["generated_at_utc"]=now
s["instruments"][0]["proposal"]="BUY"
s["instruments"][0]["last_closed_m5"]=s["instruments"][0]["indicators"]["M5"]["bar_time"]
with tempfile.TemporaryDirectory(prefix="apex-execution-tests-") as tmp:
    conn=init_db(Path(tmp)/"intent_ledger.sqlite")
    one=record_intents(conn,s,r,p,a,policy) if False else record_intents(conn,s,r,p,a,policy)
    assert one["broker_orders_submitted"]==0
    assert one["execution_authorized"] is False
    assert one["new_intents"]>=1
    assert all(x["state"]=="BLOCKED" for x in one["intents"])
    initial=one["ledger_total_intents"]
    print("PASS broker intent recorded and blocked",initial)
    two=record_intents(conn,s,r,p,a,policy)
    assert two["new_intents"]==0 and two["ledger_total_intents"]==initial
    print("PASS repeated scheduling never creates duplicate attempts")
    conn.close()
    conn=init_db(Path(tmp)/"intent_ledger.sqlite")
    three=record_intents(conn,s,r,p,a,policy)
    assert three["new_intents"]==0 and three["ledger_total_intents"]==initial
    print("PASS restart preserves idempotency")
    key=conn.execute("SELECT signal_key FROM intents LIMIT 1").fetchone()[0]
    conn.execute("UPDATE intents SET state='UNCERTAIN' WHERE signal_key=?",(key,))
    try:record_intents(conn,s,r,p,a,policy)
    except RuntimeError:pass
    else:raise AssertionError("Unreconciled state was not rejected")
    print("PASS uncertain order state freezes controller")
    conn.execute("UPDATE intents SET state='BLOCKED' WHERE signal_key=?",(key,))
    bad=copy.deepcopy(policy);bad["automated_demo_execution"]=True
    try:record_intents(conn,s,r,p,a,bad)
    except ValueError:pass
    else:raise AssertionError("Unauthorized execution release accepted")
    print("PASS unexpected root policy unlock rejected")
    bad=copy.deepcopy(a);bad["execution_enabled"]=True
    try:record_intents(conn,s,r,p,bad,policy)
    except ValueError:pass
    else:raise AssertionError("Unexpected broker execution flag accepted")
    print("PASS execution-enabled broker telemetry rejected")
    bad=copy.deepcopy(p);bad["orders_placed"]=1
    try:record_intents(conn,s,r,bad,a,policy)
    except ValueError:pass
    else:raise AssertionError("Unexpected prior order accepted")
    print("PASS broker precheck must report exactly zero orders")
    assert conn.execute("SELECT count(*) FROM intents").fetchone()[0]==initial
    conn.close()
print("RESULT: 7/7 categories PASS")
