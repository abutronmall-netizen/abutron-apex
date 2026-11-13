#!/usr/bin/python3
"""Read-only cross-account native broker receipt audit.

Never submits orders, edits customer controls, or declares a broker fill from an
EA acknowledgement alone. All trade outcomes require separate broker proof.
"""
from __future__ import annotations
import json,os,re,sqlite3,sys,time,datetime,tempfile
from pathlib import Path
sys.path.insert(0,"/opt/apex-client-mt5")
import customer_order_ledger as ledger
ROOT=Path("/var/lib/private")
OUT=Path("/var/lib/apex-client-feed/execution-router/native-receipts.json")
KEY=re.compile(r"^[a-f0-9]{64}$")
CID=re.compile(r"^[a-f0-9]{32}$")
STATES=("SUBMISSION_UNKNOWN","BROKER_ACK_UNRECONCILED","OPEN_PROTECTED","UNPROTECTED","RESERVED")
def parse_receipt(path,cid,key):
    if not CID.fullmatch(cid) or not KEY.fullmatch(key):
        return "INVALID_LEDGER_IDENTITY"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>2000:
            return "NO_TRUSTWORTHY_NATIVE_RECEIPT"
        rows=path.read_text(encoding="utf-8-sig").splitlines()
        if len(rows)!=7 or rows[0]!="APEX_NATIVE_V1" or rows[1]!=key:
            return "RECEIPT_MISMATCH_OR_SCHEMA_INVALID"
        kind=rows[2]
        if kind=="BLOCKED":
            return "EA_BLOCKED_NOT_A_BROKER_FILL"
        if kind=="UNKNOWN":
            return "BROKER_OUTCOME_UNKNOWN_RECONCILE_ONLY"
        if kind!="BROKER_ACK":
            return "UNKNOWN_RECEIPT_STATUS"
        order=int(rows[4]);deal=int(rows[5]);issued=int(rows[6])
        if order<=0 or deal<=0 or issued<=0 or abs(time.time()-issued)>86400:
            return "BROKER_RECEIPT_IDENTIFIER_OR_AGE_INVALID"
        return "BROKER_ACK_EXISTS_NOT_A_POSITION_FILL_PROOF"
    except (OSError,UnicodeError,ValueError,IndexError):
        return "RECEIPT_UNREADABLE"
def audit(db_path=ledger.DB,root=ROOT):
    con=sqlite3.connect("file:"+str(db_path)+"?mode=ro",uri=True)
    try:
        attempts=con.execute("""SELECT connection_id,signal_key,symbol,state FROM attempts
          WHERE state IN ('SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED',
            'OPEN_PROTECTED','UNPROTECTED','RESERVED') ORDER BY created_at_utc""").fetchall()
    finally:con.close()
    items=[]
    for cid,key,symbol,state in attempts:
        if not CID.fullmatch(cid):
            items.append(dict(connection_id_prefix="INVALID",state=state,classification="INVALID_LEDGER_IDENTITY"))
            continue
        p=root/("abutron-client-mt5-"+cid)/"terminal/MQL5/Files/ABUTRON/APEX_NATIVE_ORDER_V1.receipt"
        result=parse_receipt(p,cid,key)
        items.append({"connection_id_prefix":cid[:8],"symbol":symbol,"ledger_state":state,
                      "classification":result,"broker_position_reconciled":False})
    return {"schema":"abutron.apex.native.receipt.audit.v1",
       "checked_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "unresolved_attempts":len(attempts),"receipt_audit":items,
       "orders_submitted_by_audit":0,"broker_fills_certified_by_audit":0}
def main():
    result=audit()
    OUT.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".receipt-audit-",dir=OUT.parent)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(result,f,allow_nan=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,OUT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("APEX_NATIVE_RECEIPT_AUDIT",result["unresolved_attempts"],"UNRESOLVED",
          result["broker_fills_certified_by_audit"],"FILL_PROOFS")
if __name__=="__main__":main()
