#!/usr/bin/env python3
"""Superadmin Deriv DEMO historical APEX deal reconciliation. Read-only broker evidence."""
import csv,hashlib,json,sqlite3,math,sys,datetime,time,os,tempfile
from pathlib import Path

DB=Path("/var/lib/apex-signup/accounts.sqlite3")
ROOT=Path("/var/lib/apex-client-feed")
PROOF=ROOT/"evidence/owner-flat-reconciliation.json"
OUT=ROOT/"evidence/superadmin-apex-deal-history-v1.json"
CID="d6fc2524ec373b8d1bc278a8be3ec635"
def parse_utc(value):
    return datetime.datetime.fromisoformat(str(value).replace("Z","+00:00")).timestamp()
def verify():
    result={"schema":"abutron.apex.owner.deal_history.v1","verified_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "broker":"Deriv","environment":"DEMO","login_suffix":"6207",
            "historical_close_deals_verified":False,"orders_submitted":0,"positions":[],"reasons":[]}
    def fail(message):
        result["reasons"].append(message)
        return result
    with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=5) as c:
        row=c.execute("""SELECT x.id,x.account_id,x.account_reference,x.broker_server,x.status,
            x.environment,x.broker,x.worker_binding
            FROM apex_mt5_connections x JOIN accounts a ON x.account_id=a.id
            WHERE lower(a.email)=?""",("abutroncloud@gmail.com",)).fetchone()
    if not row or row[0]!=CID or row[3]!="Deriv-Demo" or row[5:7]!=("DEMO","Deriv") or row[7]!="abutron-client-mt5-"+CID or not str(row[2]).endswith("6207"):
        return fail("OWNER_DB_IDENTITY_UNVERIFIED")
    home=Path("/var/lib/private/abutron-client-mt5-"+CID)
    health=json.loads((home/"worker-health.json").read_text())
    nonce=health.get("nonce")
    if not isinstance(nonce,str) or len(nonce)!=32 or not all(c in "0123456789abcdef" for c in nonce) :
        return fail("BROKER_WORKER_UNVERIFIED")
    # Historical closure proof is immutable and independent of current connectivity.
    # The current broker session and flat-position checks remain separate mandatory
    # handover gates; never reinterpret this read-only archive as a live readiness proof.
    result["current_session_status_at_verification"]=row[4]
    result["requires_independent_current_broker_attestation"]=True
    old=json.loads(PROOF.read_text())
    source=old.get("historical_source_positions")
    if (old.get("mt5_login_suffix")!="6207" or old.get("broker")!="Deriv" or
        old.get("environment")!="DEMO" or not isinstance(source,list) or len(source)!=3):
        return fail("LEGACY_OWNER_SOURCE_SNAPSHOT_INVALID")
    file=home/"terminal/MQL5/Files"/("ABUTRON_APEX_OWNER_HISTORY_V1_"+nonce+".tsv")
    if file.is_symlink() or not file.is_file() or file.stat().st_size>2000000 or file.stat().st_size<150:
        return fail("OFFICIAL_BROKER_HISTORY_EXPORT_MISSING")
    lines=file.read_text(encoding="utf-8-sig").splitlines()
    if len(lines)<7 or lines[:4]!=["ABUTRON_APEX_OWNER_HISTORY_V1",nonce,str(row[2]),"Deriv-Demo"]:
        return fail("BROKER_HISTORY_ACCOUNT_NONCE_MISMATCH")
    if not -15<=time.time()-int(lines[4])<=86400:
        return fail("BROKER_HISTORY_EXPORT_TOO_OLD")
    deals=list(csv.DictReader(lines[5:],delimiter="\t"))
    if not 0<len(deals)<=100000 or any(not d.get("ticket") or not d.get("position_id") for d in deals):
        return fail("BROKER_DEAL_HISTORY_CORRUPT")
    result["export_sha256"]=hashlib.sha256(file.read_bytes()).hexdigest()
    result["broker_deals_returned"]=len(deals)
    for oldposition in source:
        id=str(oldposition["ticket"])
        symbol=oldposition["symbol"];side=oldposition["side"];volume=float(oldposition["volume"])
        if side not in ("BUY","SELL") or not math.isfinite(volume) or volume<=0:
            return fail("UNTRUSTED_LEGACY_POSITION")
        rr=[d for d in deals if d["position_id"]==id]
        if not rr or any(d["symbol"]!=symbol for d in rr):
            return fail("POSITION_NOT_MATCHED_"+id)
        enters=[d for d in rr if d["entry"]=="0"]
        closes=[d for d in rr if d["entry"]=="1"]
        if len(enters)!=1 or not closes or len(enters)+len(closes)!=len(rr):
            return fail("POSITION_ENTRY_EXIT_LIFECYCLE_INCOMPLETE_"+id)
        expected_entry_type=0 if side=="BUY" else 1
        expected_exit_type=1-expected_entry_type
        if int(enters[0]["type"])!=expected_entry_type or any(int(d["type"])!=expected_exit_type for d in closes):
            return fail("POSITION_DIRECTION_MISMATCH_"+id)
        entry_volume=float(enters[0]["volume"]);exit_volume=sum(float(d["volume"]) for d in closes)
        if abs(entry_volume-volume)>0.000001 or abs(exit_volume-volume)>0.000001:
            return fail("POSITION_VOLUME_NOT_FULLY_CLOSED_"+id)
        if max(int(d["time_utc"]) for d in closes)<int(enters[0]["time_utc"]):
            return fail("EXIT_BEFORE_ENTRY_"+id)
        values={k:round(sum(float(d[k]) for d in rr),2) for k in ("profit","commission","fee","swap")}
        result["positions"].append({"position_ticket":oldposition["ticket"],"symbol":symbol,"side":side,
          "volume":volume,"opening_deal":enters[0]["ticket"],
          "closing_deals":[d["ticket"] for d in closes],"closed_volume":exit_volume,
          "close_reason_codes":[d["reason"] for d in closes],
          "net_usd":round(sum(values.values()),2),**values})
    result["historical_close_deals_verified"]=len(result["positions"])==3
    result["gross_usd"]=round(sum(x["profit"] for x in result["positions"]),2)
    result["net_usd"]=round(sum(x["net_usd"] for x in result["positions"]),2)
    return result
def main():
    try:
        result=verify()
    except (ValueError,TypeError,LookupError,KeyError,OSError,sqlite3.Error,OverflowError) as e:
        result={"schema":"abutron.apex.owner.deal_history.v1",
          "historical_close_deals_verified":False,"error_type":type(e).__name__,"orders_submitted":0}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".owner-deals-",dir=OUT.parent)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(result,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,OUT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("SUPERADMIN_HISTORICAL_BROKER_DEALS", "VERIFIED" if result.get("historical_close_deals_verified") else "BLOCKED",
        "MATCHED_POSITIONS",len(result.get("positions",[])),
        "BROKER_DEALS",result.get("broker_deals_returned",0),
        "NET_USD",result.get("net_usd","unknown"),
        "ORDERS_SUBMITTED",result.get("orders_submitted",0),
        "BLOCKERS",result.get("reasons",[]))
    return 0 if result.get("historical_close_deals_verified") else 2
if __name__=="__main__":sys.exit(main())
