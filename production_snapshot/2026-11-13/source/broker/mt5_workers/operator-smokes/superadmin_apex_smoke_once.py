#!/usr/bin/env python3
"""Exactly one customer-consented APEX Deriv DEMO native-order smoke. NOT unattended activation.
No LIVE, no direct MT5 credentials, no position retry, never fabricates broker evidence.
Requires external confirmation original source writer is disabled and native timer stopped.
"""
from __future__ import annotations
import argparse,fcntl,json,os,sqlite3,time,sys,subprocess
from pathlib import Path
sys.path[:0]=["/opt/apex-client-mt5","/opt/apex-client-portal","/opt/apex-signup"]
import apex_native_order_runtime as native
import apex_signal_native_router_v1 as router
import customer_order_ledger as ledger
import apex_customer_worker_entitlement as entitlement
CID="d6fc2524ec373b8d1bc278a8be3ec635"
SLOT=Path("/var/lib/apex-client-feed/execution-router/superadmin-demo-ordercheck-fix-once.spent")
LOCK=Path("/var/lib/apex-client-feed/execution-router/execution-writer.lock")
class Refuse(RuntimeError):pass
def check():
    rows=[r for r in router.account_rows() if r[0]==CID]
    if len(rows)!=1:raise Refuse("SUPERADMIN_NOT_UNIQUELY_CONNECTED")
    row=rows[0]
    cid,owner,broker,env,server,status,worker,login,desired,effective=row
    if (broker,env,server,status,worker,desired,effective)!=(
        "Deriv","DEMO","Deriv-Demo","CONNECTED","abutron-client-mt5-"+CID,1,0):
        raise Refuse("OWNER_DEMO_CONSENT_OR_CONNECTION_UNVERIFIED")
    with sqlite3.connect("file:"+router.DB+"?mode=ro",uri=True) as c:
        audit=c.execute("""SELECT requested_enabled,outcome FROM apex_trade_control_audit
                   WHERE connection_id=? ORDER BY id DESC LIMIT 1""",(cid,)).fetchone()
        if audit!=(1,"CUSTOMER_REQUESTED_DEMO_ACTIVATION_PENDING_BROKER_ACK"):
            raise Refuse("LATEST_AUTHENTICATED_ON_REQUEST_MISSING")
        payload=dict(account_id=owner,connection_id=cid,broker=broker,environment=env,
                     platform="MT5",account_reference=login,broker_server=server,worker_binding=worker)
        allowed,reasons,basis=entitlement.evaluate(c,payload)
        if allowed or reasons!=["ACCOUNT_EXECUTION_NOT_ACTIVE"] or basis!="paid":
            raise Refuse("CUSTOMER_LICENSE_OR_SUBSCRIPTION_NOT_VERIFIED")
    policy,profile,hand=router.read(router.POLICY),router.read(router.PROFILE),router.read(router.HANDOVER)
    plan=router.plan(row,profile,policy,hand,"dispatch")
    expected={"CUSTOMER_AUTOMATED_EXECUTION_SWITCH_OFF","EXCLUSIVE_TRADING_HANDOVER_NOT_APPROVED"}
    if set(plan["blockers"])!=expected:raise Refuse("ROUTER_PREFLIGHT_"+",".join(plan["blockers"]))
    if not plan.get("candidate_orders"):raise Refuse("NO_FRESH_APEX_SIGNAL_TO_TEST")
    if len(plan["candidate_orders"])>4:raise Refuse("TOO_MANY_UNEXPECTED_RESEARCH_SIGNALS")
    candidate=plan["candidate_orders"][0]
    if candidate.get("gross_sl_usd")!=50.0 or candidate.get("gross_tp_usd")!=100.0:
        raise Refuse("GROSS_SL_TP_CHANGED")
    feed=router.read(router.BASE/(cid+".json"));acct=feed.get("account",{})
    equity=acct.get("equity_usd")
    if type(equity) not in (float,int) or not equity>=5000 or 50.0/equity>0.01:
        raise Refuse("DEMO_EQUITY_RISK_GUARD_FAILED")
    if acct.get("open_positions")!=0 or acct.get("positions")!=[]:
        raise Refuse("BROKER_EXPOSURE_NOT_FLAT")
    ea,err=native.ea_state_v2(cid,login,server)
    if (err or not ea or ea.get("protocol_version")!=2 or
        ea.get("native_demo_orders_enabled") is not True or
        ea.get("pending_orders")!=0 or ea.get("positions")!=0 or
        ea.get("terminal_trade_allowed") is not True or
        ea.get("account_trade_allowed") is not True):
        raise Refuse("NATIVE_V2_DEMO_ORDER_PERMISSION_OR_EXPOSURE_FAILED")
    folder=ea["files"]/"ABUTRON"
    if not folder.is_dir() or folder.is_symlink() or (folder/native.REQUEST_NAME).exists():
        raise Refuse("BROKER_ORDER_DIRECTORY_NOT_EXCLUSIVE")
    key=candidate["signal_key"]
    if (folder/"receipts"/(key+".txt")).exists():
        raise Refuse("BROKER_SIGNAL_ALREADY_HAS_RECEIPT")
    with ledger.new() as c:
        # Prior smoke was broker-denied with NO FILL; never replay that signal.
        # Any UNKNOWN/ACK/OPEN entry prevents a second controlled attempt.
        existing=c.execute("SELECT state FROM attempts").fetchall()
        if any(state!="BROKER_DENIED_NO_FILL" for (state,) in existing):
            raise Refuse("UNRESOLVED_OR_NONREJECTED_PREVIOUS_BROKER_ATTEMPT")
        if len(existing)!=1:
            raise Refuse("PREVIOUS_REJECTED_SMOKE_NOT_UNIQUE")
    if SLOT.exists():raise Refuse("CONTROLLED_DEMO_SMOKE_ALREADY_USED")
    return row,plan,candidate,ea,folder,equity
def execute():
    if subprocess.run(["systemctl","is-active","abutron-apex-native-orders.timer"],
           stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True).stdout.strip()=="active":
        raise Refuse("UNATTENDED_PRODUCTION_WRITER_TIMER_MUST_BE_STOPPED_FIRST")
    fd=os.open(LOCK,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        row,plan,cand,ea,folder,equity=check()
        cid,owner=row[0],row[1];key=cand["signal_key"]
        proof={"broker":"Deriv","environment":"DEMO","server":"Deriv-Demo",
           "current_broker_identity_verified":True,"open_positions":0,"pending_orders":0,
           "risk_governor_approved":True, # checked DEMO equity and exact gross USD risk
           "account_trade_authorized":True, # latest authenticated customer owner request
           "single_writer_approved":True} # current root lock and isolated test timer off
        # Durable one-shot slot and ledger before native command. Never retry UNKNOWN outcomes.
        with ledger.new() as c:
            ledger.reserve(c,owner,cid,cand["symbol"],cand["side"],cand["m5_bar_time"],key,proof)
            ledger.queue_native_usd_pending(c,key,cand["volume"],50.0,100.0)
        slotfd=os.open(SLOT,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(slotfd,"w") as f:
            f.write(json.dumps({"signal_key":key,"when":int(time.time()),
                  "symbol":cand["symbol"],"side":cand["side"],
                  "mode":"ONE_SHOT_SUPERVISED_DERIV_DEMO_ONLY"},separators=(",",":")))
            f.flush();os.fsync(f.fileno())
        lines=["APEX_NATIVE_ORDER_V2",ea["nonce"],key,row[7],row[4],
            cand["symbol"],cand["side"],str(cand["volume"]),"50","100",
            str(int(time.time()+12)),"SEND_DEMO_ONLY"]
        native.atomic_native_request(folder/native.REQUEST_NAME,lines)
        print("DEMO_SMOKE_NATIVE_REQUEST_QUEUED",cid[:8],
            cand["symbol"],cand["side"],"USD_SL",50,"USD_TP",100,"KEY_PREFIX",key[:12])
    finally:os.close(fd)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if os.geteuid()!=0:raise SystemExit("ROOT_REQUIRED")
    if a.dry_run==a.execute:p.error("Choose exactly one mode")
    try:
        if a.dry_run:
            row,plan,cand,ea,folder,equity=check()
            print("SUPERADMIN_SMOKE_READY",cand["symbol"],cand["side"],
                  "EQUITY",equity,"USD_SL",50,"USD_TP",100,
                  "NO_ORDERS_SUBMITTED")
        else:execute()
    except (Refuse,native.Refused,ledger.Blocked,ValueError,OSError,sqlite3.Error) as e:
        print("SUPERADMIN_SMOKE_BLOCKED",str(e)[:210]);raise SystemExit(2)
if __name__=="__main__":main()
