#!/usr/bin/python3
"""ABUTRON independent two-broker native ACK continuity audit (READ-ONLY).
A broker execution ACK requires current, account-bound immutable native
receipt, corresponding native send audit, and a separately authenticated
broker deal plus protective position proof. Pre-existing FP receipts do NOT
authorize a new trade or substitute for fresh Deriv 6207 revision ACK.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time

CRM=Path("/var/lib/apex-signup/accounts.sqlite3")
BASE=Path("/var/lib/private")
SUP=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207")
DERIV_FULL=SUP/"deriv-6207-native-fullrange-history.json"
FP_DUAL=Path("/var/lib/abutron-fp-execution/dual-account-reconciliation/latest.json")
FP_HISTORY=Path("/var/lib/apex-signup/fp-native-history/35b81a287b6a030f2f46ff426b135e6c.json")
STATE=SUP/"two-broker-ack-observation-origin.json"
DEST=SUP/"two-broker-native-order-ack-audit.json"
DID="d6fc2524ec373b8d1bc278a8be3ec635"
FID="35b81a287b6a030f2f46ff426b135e6c"
HEX64=re.compile(r"^[0-9a-f]{64}$")
HEX32=re.compile(r"^[0-9a-f]{32}$")

def read(path:Path,max_bytes=250000,ttl=250):
    if path.is_symlink():raise ValueError("SYMLINK_INPUT_DENIED")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        a=os.fstat(fd)
        if (not stat.S_ISREG(a.st_mode) or a.st_nlink!=1
            or a.st_mode&0o022 or not 1<a.st_size<=max_bytes or
            not -3<=time.time()-a.st_mtime<=ttl):
            raise ValueError("UNTRUSTED_STALE_OR_OVERSIZED_SOURCE")
        blob=os.read(fd,max_bytes+1)
        b=os.fstat(fd)
        if (len(blob)!=a.st_size or
            (a.st_dev,a.st_ino,a.st_mtime_ns,a.st_size)!=(b.st_dev,b.st_ino,b.st_mtime_ns,b.st_size)):
            raise ValueError("NATIVE_SOURCE_CHANGED_DURING_READ")
        return blob
    finally:os.close(fd)

def js(path,ttl=250):
    v=json.loads(read(path,ttl=ttl))
    if type(v)!=dict:raise ValueError("INVALID_JSON_EVIDENCE")
    return v

def crm():
    with sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=7) as c:
        c.execute("PRAGMA query_only=ON")
        rows=c.execute("""SELECT x.id,x.account_id,x.account_reference,x.broker,
                          x.environment,x.broker_server,x.status,
                          coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
                          FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t
                          ON t.connection_id=x.id WHERE x.id IN (?,?)""",(DID,FID)).fetchall()
        fence=c.execute("""SELECT revision,desired_enabled,effective_enabled,ack_revision
                           FROM abutron_v4_6207_activation_revision
                           WHERE connection_id=?""",(DID,)).fetchone()
    found={r[0]:r for r in rows}
    if (set(found)!={DID,FID} or fence is None or
        found[DID][2:7]!=("32456207","Deriv","DEMO","Deriv-Demo","CONNECTED") or
        found[FID][2:7]!=("7410512","FP Markets","DEMO","FPMarketsSC-Demo","CONNECTED") or
        found[DID][1]!=found[FID][1] or found[DID][8]!=0 or found[FID][8]!=0 or
        fence[2]!=0 or fence[3] is not None):
        raise ValueError("CRM_NATIVE_ACCOUNT_OR_EXECUTION_FENCE_UNVERIFIED")
    return fence

def worker(cid,broker,login,server):
    home=BASE/("abutron-client-mt5-"+cid)
    h=js(home/"worker-health.json",35)
    n=h.get("nonce")
    if (h.get("id")!=cid or h.get("broker")!=broker or
        h.get("server")!=server or h.get("mode")!="DEMO" or
        h.get("status")!="CONNECTED" or h.get("heartbeat_fresh") is not True or
        type(n)!=str or HEX32.fullmatch(n) is None):
        raise ValueError("BROKER_MT5_WORKER_NOT_ACCOUNT_BOUND")
    return h,home/"terminal/MQL5/Files"

def receipt_lines(path,nonce,login,server,version):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>2048:
        raise ValueError("NATIVE_RECEIPT_NOT_TRUSTED")
    lines=path.read_text(encoding="utf-8-sig").splitlines()
    if (len(lines)!=10 or lines[0]!=version or lines[1]!=path.stem
        or HEX64.fullmatch(path.stem) is None or
        lines[2] not in ("ACK","BLOCKED","UNKNOWN") or
        lines[7:]!=[nonce,login,server]):
        raise ValueError("NATIVE_RECEIPT_NONCE_IDENTITY_OR_SCHEMA_INVALID")
    if not all(x.isdecimal() for x in lines[4:7]):
        raise ValueError("NATIVE_RECEIPT_BROKER_IDS_INVALID")
    if (lines[2]=="ACK" and (int(lines[4])<=0 or int(lines[5])<=0)):
        raise ValueError("NATIVE_ACK_WITHOUT_BROKER_ORDER_OR_DEAL")
    return {"signal_key":lines[1],"status":lines[2],"reason":lines[3],
            "native_broker_order":int(lines[4]),"native_broker_deal":int(lines[5]),
            "issued_broker_utc":int(lines[6])}

def inventory(folder,nonce,login,server,version):
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("RECEIPT_DIRECTORY_NOT_TRUSTED")
    files=sorted(folder.glob("*.txt"))
    if len(files)>250:raise ValueError("RECEIPT_COUNT_ABOVE_LIMIT")
    return [receipt_lines(p,nonce,login,server,version) for p in files]

def fp_proof(history,receipt):
    if receipt["status"]!="ACK":return False
    trades=history.get("trade_deals",[])
    hits=[r for r in trades if isinstance(r,dict) and
          str(r.get("ticket"))==str(receipt["native_broker_deal"]) and
          str(r.get("order_id"))==str(receipt["native_broker_order"]) and
          r.get("entry")=="IN"]
    return len(hits)==1

def deriv_proof(files,nonce,receipt):
    """Never infer broker ACK from an EA status alone."""
    if receipt["status"]!="ACK":return False
    key=receipt["signal_key"]
    folder=files/"ABUTRON/execution-audit"
    required=[folder/(key+suf) for suf in
              (".request.txt",".result.txt",".protected.txt")]
    if not all(p.is_file() and not p.is_symlink() for p in required):
        return False
    req=required[0].read_text(encoding="utf-8-sig").splitlines()
    res=required[1].read_text(encoding="utf-8-sig").splitlines()
    protected=required[2].read_text(encoding="utf-8-sig").splitlines()
    if (len(req)!=18 or len(res)!=17 or len(protected)!=23 or
        req[:5]!=["ABUTRON_NATIVE_REQUEST_AUDIT_V1",key,nonce,"32456207","Deriv-Demo"] or
        res[:5]!=["ABUTRON_NATIVE_RESULT_AUDIT_V1",key,nonce,"32456207","Deriv-Demo"] or
        protected[:5]!=["ABUTRON_NATIVE_PROTECTED_AUDIT_V1",key,nonce,"32456207","Deriv-Demo"] or
        protected[-1]!="OPEN_PROTECTED"):
        return False
    if (not all(x.isdecimal() for x in [res[9],res[10],res[12],res[13]]) or
        int(res[9])!=1 or int(res[10]) not in (10009,10010) or
        int(res[12])!=receipt["native_broker_order"] or
        int(res[13])!=receipt["native_broker_deal"] or
        protected[7]!=str(receipt["native_broker_order"]) or
        protected[8]!=str(receipt["native_broker_deal"])):
        return False
    return True # Only an account-bound MQL protected audit; second broker history required below.

def inspect():
    now=int(time.time())
    fence=crm()
    start=js(STATE,ttl=3650*86400)
    origin=start.get("origin_unix")
    if (start.get("schema")!="abutron.two_broker.native_ack_observation_start.v1"
        or type(origin)!=int or origin>now or origin<1794000000):
        raise ValueError("ACK_MONITOR_BASELINE_UNTRUSTED")
    dh,dfiles=worker(DID,"Deriv","32456207","Deriv-Demo")
    fh,ffiles=worker(FID,"FP Markets","7410512","FPMarketsSC-Demo")
    fp=js(FP_HISTORY,160)
    native=js(FP_DUAL,160)
    d_history=js(DERIV_FULL,205)
    if (fp.get("account_masked")!="••••0512" or
        fp.get("history_verified_from_mt5") is not True or
        native.get("state")!="RECONCILED_READONLY" or
        d_history.get("account_suffix")!="6207" or
        d_history.get("full_range_cashflow_to_broker_balance_reconciled") is not True):
        raise ValueError("INDEPENDENT_BROKER_RECEIPTS_HISTORY_NOT_CURRENT")
    fp_row=[r for r in native.get("accounts",[]) if r.get("account_suffix")=="0512"]
    if (len(fp_row)!=1 or fp_row[0].get("state")!="RECONCILED_READONLY"
        or fp_row[0].get("unresolved_receipts")!=0):
        raise ValueError("FP_NATIVE_INDEPENDENT_RECEIPT_LEDGER_BLOCKED")
    dr=inventory(dfiles/"ABUTRON/receipts",dh["nonce"],"32456207","Deriv-Demo","APEX_NATIVE_V2")
    fr=inventory(ffiles/"ABUTRON_FP/receipts",fh["nonce"],"7410512","FPMarketsSC-Demo","APEX_FP_NATIVE_V1")
    dnew=[r for r in dr if r["issued_broker_utc"]>=origin]
    fnew=[r for r in fr if r["issued_broker_utc"]>=origin]
    hfp=[r for r in fr if r["status"]=="ACK"]
    fp_hist_verified=sum(fp_proof(fp,r) for r in hfp)
    if fp_hist_verified!=fp_row[0]["historical_broker_ack"]:
        raise ValueError("FP_INDEPENDENT_HISTORICAL_BROKER_ACK_COUNT_MISMATCH")
    if any(r["status"]=="UNKNOWN" for r in dr+fr):
        raise ValueError("UNRESOLVED_NATIVE_RECEIPT_UNKNOWN")
    verified_new_deriv=0
    for receipt in dnew:
        if receipt["status"]=="ACK" and deriv_proof(dfiles,dh["nonce"],receipt):
            # Need a second independent native record at the same order/deal/position.
            # Current Deriv fullrange summary has no per-deal history in this function;
            # do not claim a broker ACK from a native EA's own report alone.
            pass
    new_fp_verified=sum(fp_proof(fp,r) for r in fnew if r["status"]=="ACK")
    # No permission for any new order with CRM effective OFF. A real newly
    # observed order while OFF should be an incident, not a green cutover.
    # Any new native ACK while effective OFF is abnormal even before
    # independent broker deal confirmation. Distinguish an alert from proof.
    unexpected_new_acks=any(r["status"]=="ACK" for r in dnew+fnew)
    status=("UNEXPECTED_NATIVE_ACK_WHILE_CRM_OFF"
            if unexpected_new_acks else "NO_NEW_BROKER_EXECUTION_ACK")
    return {"schema":"abutron.two_broker.native_order_ack.independent_monitor.ro.v1",
       "checked_utc":datetime.now(timezone.utc).isoformat(),
       "observation_started_utc":datetime.fromtimestamp(origin,timezone.utc).isoformat(),
       "state":status,
       "crm_6207_revision":fence[0],
       "crm_6207_revision_execution_ack":False,
       "broker_execution_ack_for_new_6207_order":False,
       "broker_execution_ack_for_new_fp0512_order":False,
       "deriv_6207":{"account_suffix":"6207","native_receipts_total":len(dr),
           "native_receipts_since_monitor_start":len(dnew),
           "new_independent_protected_broker_orders":verified_new_deriv,
           "native_status_nonce":dh["nonce"]},
       "fp_0512":{"account_suffix":"0512","native_receipts_total":len(fr),
           "historical_native_ack_count":len(hfp),
           "historical_broker_deal_ack_matches":fp_hist_verified,
           "native_receipts_since_monitor_start":len(fnew),
           "new_independent_broker_deal_matches":new_fp_verified,
           "native_status_nonce":fh["nonce"]},
       "all_existing_broker_native_order_receipts_reconciled":True,
       "reused_historical_fp_receipt_as_new_ack":False,
       "new_order_submission_authorized":False,
       "any_new_broker_order_unexpected_with_crm_off":unexpected_new_acks,
       "orders_submitted_by_monitor":0,"client_switches_modified":False,
       "live_authorized":False}

def main():
    d=inspect()
    f=DEST.parent/(".two-broker-ack-"+str(os.getpid())+".tmp")
    fd=os.open(f,os.O_EXCL|os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as x:
            json.dump(d,x,sort_keys=True,indent=2,allow_nan=False)
            x.write("\n");x.flush();os.fsync(x.fileno())
        os.replace(f,DEST)
    finally:f.unlink(missing_ok=True)
    print(json.dumps({"state":d["state"],
        "deriv_new":d["deriv_6207"]["native_receipts_since_monitor_start"],
        "fp_historical_broker_acks":d["fp_0512"]["historical_broker_deal_ack_matches"],
        "fp_new":d["fp_0512"]["native_receipts_since_monitor_start"],
        "execution_ack":False,"orders":0}))
if __name__=="__main__":sys.exit(main())
