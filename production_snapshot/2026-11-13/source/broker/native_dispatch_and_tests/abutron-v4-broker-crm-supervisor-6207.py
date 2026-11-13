#!/usr/bin/python3
"""ABUTRON V4: production read-only Deriv 6207 broker/CRM admission inspector.

It never enables trading, creates activation leases, queues or sends orders.
A successful audit process exit is NOT trading authorization.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time

CID="d6fc2524ec373b8d1bc278a8be3ec635"
LOGIN="32456207"
EXPECTED_SHA="a32754fad743cb61385bde94f1a190c7b39b1a123eaac00a351d7f44ea8abcf0"
WORKER=Path("/var/lib/private/abutron-client-mt5-"+CID)
SIDE=Path("/var/lib/private/abutron-native-readonly-mt5-6207")
CRM=Path("/var/lib/apex-signup/accounts.sqlite3")
FP=Path("/var/lib/private")
ROUTER=Path("/var/lib/apex-client-feed/execution-router/summary.json")
OUTPUT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/evidence.json")
EA=WORKER/"terminal/MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_6207.ex5"
HEX32=re.compile(r"^[0-9a-f]{32}$")

def stable_file(path,limit=32768):
    if path.is_symlink():
        raise ValueError("SYMLINK")
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|getattr(os,"O_NOFOLLOW",0))
    try:
        x=os.fstat(fd)
        if not stat.S_ISREG(x.st_mode) or x.st_nlink!=1 or x.st_mode&0o022 or not 0<x.st_size<=limit:
            raise ValueError("UNTRUSTED_MODE_SIZE")
        data=os.read(fd,limit+1)
        y=os.fstat(fd)
        if (x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns)!=(y.st_dev,y.st_ino,y.st_size,y.st_mtime_ns) or len(data)!=x.st_size:
            raise ValueError("RACE_OR_TRUNCATION")
        return data,x
    finally:
        os.close(fd)

def fresh_json(path,now,ttl):
    data,st=stable_file(path)
    if not -2<=now-st.st_mtime<=ttl:
        raise ValueError("STALE")
    obj=json.loads(data)
    if type(obj)!=dict:
        raise ValueError("INVALID_JSON")
    return obj

def positive(v):
    try:
        d=Decimal(v)
        if not d.is_finite() or d<=0: raise ValueError
        return str(d)
    except (ValueError,TypeError,InvalidOperation):
        raise ValueError("INVALID_AMOUNT") from None

def _active(unit):
    try:
        r=subprocess.run(["/usr/bin/systemctl","is-active",unit],capture_output=True,text=True,timeout=6)
        return r.stdout.strip()
    except (OSError,subprocess.TimeoutExpired):
        return "UNKNOWN"

def inspect(now=None):
    now=time.time() if now is None else float(now)
    checks={}; denied={}; metrics={}
    def gate(name,ok,reason):
        checks[name]=ok is True
        if ok is not True: denied[name]=reason

    gate("root_inspector",os.geteuid()==0,"ROOT_ATTESTOR_REQUIRED")
    account=None; owner_email=""; nonce=None; accounts=[]
    try:
        con=sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=6)
        con.execute("PRAGMA query_only=ON")
        rows=con.execute("""SELECT x.account_id,a.email,a.status,x.broker,x.environment,
           x.account_reference,x.broker_server,x.status,x.broker_verified_at,
           x.worker_binding,r.role,r.email_verified_at,
           coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
           FROM apex_mt5_connections x JOIN accounts a ON a.id=x.account_id
           LEFT JOIN apex_admin_roles r ON r.account_id=a.id
           LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
           WHERE x.id=? AND x.account_reference=?""",(CID,LOGIN)).fetchall()
        if len(rows)!=1: raise ValueError("APEX_ACCOUNT_NOT_UNIQUE")
        (account,owner_email,cust_state,broker,env,login,server,status,
         verified,binding,role,mfa,desired,effective)=rows[0]
        good=(cust_state=="approved" and broker=="Deriv" and env=="DEMO" and
              login==LOGIN and server=="Deriv-Demo" and status=="CONNECTED" and
              bool(verified) and binding=="abutron-client-mt5-"+CID and
              role=="SUPERADMIN" and bool(mfa))
        gate("apex_crm_owner_mfa_account_binding",good,"APEX_OWNER_OR_BROKER_BINDING_INVALID")
        license_rows=con.execute("SELECT plan,status,seats FROM apex_crm_licenses WHERE account_id=?",(account,)).fetchall()
        gate("apex_enterprise_license",len(license_rows)==1 and
             license_rows[0]==("Enterprise","active",3),"APEX_ENTERPRISE_LICENSE_NOT_ATTESTED")
        gate("client_requested_on",desired==1,"CLIENT_REQUESTED_OFF")
        gate("client_effective_on",effective==1,"CLIENT_EFFECTIVE_EXECUTION_OFF")
        live=con.execute("""SELECT count(*) FROM apex_mt5_connections x JOIN apex_trade_controls t
                      ON t.connection_id=x.id WHERE x.environment='LIVE'
                      AND t.effective_enabled=1""").fetchone()[0]
        gate("live_orders_disabled",live==0,"LIVE_EFFECTIVE_FLAG_FOUND")
        revision_cols={x[1] for x in con.execute("PRAGMA table_info(apex_trade_controls)")}
        gate("crm_revision_fenced_and_broker_ack",False,
             "CRM_HAS_NO_CERTIFIED_MONOTONIC_REVISION_AND_BROKER_ACK"
             if "revision" not in revision_cols else "REVISION_CAS_ACK_NOT_CERTIFIED")
        accounts=con.execute("""SELECT id,broker,environment,status
                                FROM apex_mt5_connections WHERE account_id=?""",(account,)).fetchall()
        metrics["connected_demo_account_count"]=sum(e=="DEMO" and s=="CONNECTED" for _,_,e,s in accounts)
        metrics["connected_fp_demo_account_count"]=sum(b=="FP Markets" and e=="DEMO" and s=="CONNECTED" for _,b,e,s in accounts)
        con.close()
        sql=("SELECT lower(trim(c.email)),a.status,a.bot_tier,a.route_reason "
             "FROM trading_accounts a JOIN customers c ON c.id=a.customer_id "
             "WHERE a.broker_login='32456207' AND a.server_name='Deriv-Demo' LIMIT 2")
        r=subprocess.run(["/usr/sbin/runuser","-u","postgres","--",
            "/usr/bin/psql","-X","-qAt","-F","|","-d","abutron_v7_release_store","-c",sql],
            capture_output=True,text=True,timeout=8,check=True)
        v=[x.split("|",3) for x in r.stdout.splitlines() if x]
        if len(v)!=1 or len(v[0])!=4: raise ValueError("V7_OWNER_NOT_UNIQUE")
        e,state,tier,reason=v[0]
        gate("apex_v7_same_owner",bool(owner_email) and
             hmac.compare_digest(str(owner_email).strip().casefold(),e),
             "APEX_V7_OWNER_MISMATCH")
        gate("v7_remains_readonly",state=="PAUSED" and tier=="INELIGIBLE" and
             reason=="verified_existing_owner_deriv_demo_readonly_no_orders",
             "V7_READONLY_CLAIM_CHANGED")
    except (OSError,ValueError,TypeError,sqlite3.Error,subprocess.SubprocessError) as exc:
        for key in ("apex_crm_owner_mfa_account_binding","apex_enterprise_license",
                    "client_requested_on","client_effective_on","live_orders_disabled",
                    "crm_revision_fenced_and_broker_ack","apex_v7_same_owner","v7_remains_readonly"):
            if key not in checks:gate(key,False,"CRM_ATTESTATION_UNAVAILABLE_"+type(exc).__name__)

    try:
        h=fresh_json(WORKER/"worker-health.json",now,20)
        nonce=h.get("nonce")
        valid=(h.get("id")==CID and h.get("broker")=="Deriv" and h.get("mode")=="DEMO"
               and h.get("server")=="Deriv-Demo" and h.get("status")=="CONNECTED" and
               h.get("heartbeat_fresh") is True and type(nonce)==str and HEX32.fullmatch(nonce) is not None)
        gate("deriv_worker_fresh_identity",valid,"DERIV_WORKER_NOT_ATTESTED")
        if not valid:nonce=None
    except (OSError,ValueError,TypeError,UnicodeError):
        gate("deriv_worker_fresh_identity",False,"DERIV_WORKER_PROOF_UNAVAILABLE")
    try:
        j=fresh_json(SIDE/"worker-health.json",now,35)
        valid=(j.get("broker")=="Deriv" and j.get("environment")=="DEMO" and
               j.get("status")=="CONNECTED" and j.get("broker_session_identity_verified") is True and
               j.get("native_history_source_authenticated") is True and
               j.get("execution_authority") is False and j.get("orders_submitted")==0 and
               -2<=now-float(j.get("broker_checked_utc",0))<=35)
        gate("deriv_independent_readonly_broker_session",valid,
             "DERIV_INDEPENDENT_BROKER_SESSION_UNVERIFIED")
    except (OSError,ValueError,TypeError,UnicodeError):
        gate("deriv_independent_readonly_broker_session",False,
             "DERIV_INDEPENDENT_BROKER_EVIDENCE_UNAVAILABLE")
    try:
        if nonce is None:raise ValueError("NO_NONCE")
        raw,st=stable_file(WORKER/"terminal/MQL5/Files"/("ABUTRON_NATIVE_ACCOUNT_V2_"+nonce+".txt"),1024)
        x=raw.decode("utf-8-sig").splitlines()
        valid=(len(x)==7 and x[:3]==["ABUTRON_NATIVE_ACCOUNT_V2",nonce,LOGIN]
               and x[5]=="USD" and -2<=now-st.st_mtime<=20)
        if valid:
            metrics["deriv_balance_usd"]=positive(x[3])
            metrics["deriv_equity_usd"]=positive(x[4])
        gate("deriv_native_account_snapshot",valid,"DERIV_NATIVE_EQUITY_NOT_CURRENT")
    except (OSError,ValueError,TypeError,UnicodeError):
        gate("deriv_native_account_snapshot",False,"DERIV_NATIVE_ACCOUNT_UNAVAILABLE")

    try:
        raw,st=stable_file(EA,1024000)
        gate("v4_sha256_binary_installed",st.st_size>=20000 and
             hmac.compare_digest(hashlib.sha256(raw).hexdigest(),EXPECTED_SHA),
             "V4_INSTALLED_EA_HASH_MISMATCH")
    except (OSError,ValueError):
        gate("v4_sha256_binary_installed",False,"V4_RELEASE_BINARY_NOT_INSTALLED")
    try:
        if nonce is None:raise ValueError("NO_NONCE")
        path=WORKER/"terminal/MQL5/Files"/("ABUTRON_APEX_NATIVE_V4_CAPABILITY_"+nonce+".txt")
        raw,st=stable_file(path,2048);x=raw.decode("utf-8-sig").splitlines()
        valid=(len(x)==10 and x[:5]==["APEX_NATIVE_REVISION_FENCED_CAPABILITY_V4",
                nonce,LOGIN,"Deriv-Demo","DEMO"] and -2<=now-st.st_mtime<=12)
        gate("v4_capability_file_fresh",valid,"V4_CAPABILITY_IDENTITY_OR_FRESHNESS_INVALID")
    except (OSError,ValueError,TypeError,UnicodeError):
        gate("v4_capability_file_fresh",False,"V4_CAPABILITY_NOT_PRESENT")
    gate("v4_chart_independently_attached",False,"ACTIVE_EA_CHART_AND_WEBREQUEST_NOT_CERTIFIED")

    fp_proofs=[]
    for conn,broker,env,status in accounts:
        if not (broker=="FP Markets" and env=="DEMO" and status=="CONNECTED"):continue
        proof={"account_suffix":conn[-6:],"positions":None,"protected":False,"clock_fresh":False}
        try:
            home=FP/("abutron-client-mt5-"+conn)
            h=fresh_json(home/"worker-health.json",now,30)
            n=h.get("nonce")
            if (h.get("id")!=conn or h.get("broker")!="FP Markets" or
                h.get("mode")!="DEMO" or h.get("status")!="CONNECTED" or
                h.get("heartbeat_fresh") is not True or not isinstance(n,str) or
                HEX32.fullmatch(n) is None):raise ValueError("FP_WORKER_UNVERIFIED")
            path=home/"terminal/MQL5/Files"/("ABUTRON_FP_ACCOUNT_HISTORY_V1_"+n+".txt")
            raw,st=stable_file(path,4000000);x=raw.decode("utf-8-sig").splitlines()
            if (len(x)<21 or x[0]!="ABUTRON_FP_ACCOUNT_HISTORY_V1" or x[1]!=n or
                x[5]!="DEMO" or x[19]!="BROKER_NATIVE_NO_ORDER_FUNCTIONS"):
                raise ValueError("FP_HISTORY_INVALID")
            pos=int(x[14]);pending=int(x[15]);deals=int(x[16])
            rows=[z.split("\t") for z in x[20:-1] if z.startswith("P\t")]
            if pos<0 or pending<0 or deals<0 or pos+pending+deals!=len(x)-21:
                raise ValueError("FP_HISTORY_COUNT_MISMATCH")
            proof["positions"]=pos
            proof["protected"]=len(rows)==pos and all(len(z)==13 and
                         float(z[7])>0 and float(z[8])>0 for z in rows)
            end_utc=int(x[18])-int(x[7])
            proof["history_age_seconds"]=round(now-end_utc)
            proof["clock_fresh"]=int(x[7])==7200 and -5<=now-end_utc<=86400
        except (OSError,ValueError,TypeError,UnicodeError,IndexError):
            proof["source_invalid_or_unavailable"]=True
        fp_proofs.append(proof)
    metrics["fp_demo_broker_proofs"]=fp_proofs
    gate("fp_current_broker_history",bool(fp_proofs) and all(p["clock_fresh"] for p in fp_proofs),
         "FP_BROKER_HISTORY_STALE_OR_UNAVAILABLE")
    gate("customer_cashflow_adjusted_portfolio_risk",False,
         "COMPLETE_NATIVE_POSITION_STOP_EQUITY_DAYSTART_AND_PEAK_RECONCILIATION_MISSING")
    metrics["risk_caps"]={"per_trade":"0.001","open":"0.02","daily":"0.03","drawdown":"0.20"}

    try:
        st=Path("/var/lib/apex-client-feed/execution-router/execution-writer.lock").lstat()
        safe=(stat.S_ISREG(st.st_mode) and st.st_uid==0 and
              st.st_nlink==1 and not st.st_mode&0o077)
        gate("root_native_writer_lock_file",safe,"WRITER_LOCK_PERMISSIONS_UNTRUSTED")
    except OSError:
        gate("root_native_writer_lock_file",False,"WRITER_LOCK_NOT_FOUND")
    gate("exclusive_writer_and_unknown_orders_reconciled",False,
         "V2_V4_EXCLUSIVE_WRITER_AND_UNKNOWN_ORDER_RECONCILIATION_NOT_CERTIFIED")
    try:
        r=fresh_json(Path("/var/lib/apex-client-feed/execution-router/summary.json"),now,90)
        metrics["legacy_router_fresh_candidates"]=int(r.get("fresh_research_candidates",0))
    except (OSError,ValueError,TypeError,UnicodeError):
        metrics["legacy_router_fresh_candidates"]=None
    gate("fresh_account_bound_apex11_m5_signal",False,
         "NATIVE_APEX11_M5_CLOSED_BAR_BROKER_PROPOSAL_UNVERIFIED")
    gate("broker_receipts_stops_and_exit_history_reconciled",False,
         "FULL_BROKER_ORDER_POSITION_SL_TP_AND_EXIT_PROOF_UNAVAILABLE")
    state=_active("abutron-apex-native-orders.timer")
    metrics["native_order_timer"]=state
    gate("unapproved_dispatch_inactive",state=="inactive","NATIVE_ORDER_TIMER_NOT_INACTIVE")
    return {"schema":"abutron.v4.broker_crm.readonly.admission.v1",
        "checked_utc":dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
        "account_suffix":"6207","broker":"Deriv","environment":"DEMO",
        "checks":checks,"blockers":[v for v in denied.values()],
        "reasons":denied,"metrics":metrics,"state":"BLOCKED",
        "production_release_certified":False,"order_authorized":False,
        "orders_submitted":0,"client_switches_modified":False,
        "read_only_evidence_only":True}

def main():
    doc=inspect()
    parent=OUTPUT.parent
    if not parent.is_dir() or parent.is_symlink():
        raise SystemExit("TRUSTED_SUPERVISOR_DIRECTORY_MISSING")
    st=parent.stat()
    if st.st_uid!=0 or st.st_mode&0o077:
        raise SystemExit("TRUSTED_SUPERVISOR_DIRECTORY_PERMISSIONS_INVALID")
    temp=parent/(".evidence-%d.tmp"%os.getpid())
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(doc,f,sort_keys=True,separators=(",",":"))
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(temp,OUTPUT)
    finally:
        try:temp.unlink()
        except FileNotFoundError:pass
    print(json.dumps({"schema":doc["schema"],"checked_utc":doc["checked_utc"],
         "state":doc["state"],"passes":sum(doc["checks"].values()),
         "blocks":doc["blockers"],"orders_submitted":0,
         "order_authorized":False},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
