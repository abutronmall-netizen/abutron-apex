#!/usr/bin/python3
"""Production 6207 APEX11 -> native V4 binding audit. NEVER sends an order."""
import datetime as dt
import json
import os
import fcntl
import stat
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0,"/opt/abutron-apex11-staging/native-v4-guarded-20261108")
from abutron_replacement.exclusive_native_writer import _published,DemoNativeRequest
from abutron_replacement.native_v4_file_port import NativeV4FilePort

CID="d6fc2524ec373b8d1bc278a8be3ec635"
STATE=Path("/var/lib/abutron-apex11-6207")
BASE=Path("/var/lib/private/abutron-client-mt5-"+CID)
SUP=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207")
JOURNAL=STATE/"account-bound-m5-journal.sqlite3"

def readjson(p):
    if p.is_symlink() or not p.is_file(): raise ValueError("INVALID_EVIDENCE_FILE")
    return json.loads(p.read_bytes())

@contextmanager
def monitor_lock():
    p=Path("/var/lib/apex-client-feed/execution-router/execution-writer.lock")
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o077 or st.st_nlink!=1:
            raise ValueError("WRITER_LOCK_INODE_UNTRUSTED")
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:fcntl.flock(fd,fcntl.LOCK_UN)
    finally:os.close(fd)

class JournalReader:
    def read(self,pub):
        with sqlite3.connect("file:"+str(JOURNAL)+"?mode=ro",uri=True) as c:
            c.execute("pragma query_only=on")
            r=c.execute("select payload from decisions where publication_id=?",(pub,)).fetchone()
            return json.loads(r[0]) if r else None

def inspect():
    now=time.time()
    with sqlite3.connect("file:/var/lib/apex-signup/accounts.sqlite3?mode=ro",uri=True) as c:
        c.execute("pragma query_only=on")
        r=c.execute("""select x.account_id,x.account_reference,x.broker,x.environment,
        x.broker_server,x.status,t.desired_enabled,t.effective_enabled,
        f.revision,f.ack_revision,f.ack_expires_utc
        from apex_mt5_connections x join apex_trade_controls t on t.connection_id=x.id
        join abutron_v4_6207_activation_revision f on f.connection_id=x.id
        where x.id=?""",(CID,)).fetchone()
    if r is None: raise RuntimeError("CRM_CONNECTION_UNAVAILABLE")
    owner,login,broker,env,server,status,desired,effective,rev,ack,until=r
    checks={}
    def check(k,v): checks[k]=v is True
    check("account_deriv_demo_6207",len(owner)==32 and
          str(login)=="32456207" and broker=="Deriv" and env=="DEMO" and
          server=="Deriv-Demo" and status=="CONNECTED")
    check("client_desired_on",desired==1)
    check("crm_revision_matched_active_ack",
          effective==1 and rev==ack and type(until) is int and until>now)
    health=readjson(BASE/"worker-health.json")
    nonce=health.get("nonce")
    check("native_mt5_identity",health.get("id")==CID and
          health.get("broker")=="Deriv" and health.get("mode")=="DEMO" and
          health.get("status")=="CONNECTED" and health.get("heartbeat_fresh") is True and
          isinstance(nonce,str) and len(nonce)==32 and
          0<=now-(BASE/"worker-health.json").stat().st_mtime<25)
    rows=[]
    with sqlite3.connect("file:"+str(JOURNAL)+"?mode=ro",uri=True) as c:
        c.execute("pragma query_only=on")
        rows=c.execute("select publication_id,symbol,closed_ts from decisions where closed_ts>=? order by closed_ts desc limit 25",(int(now)-600,)).fetchall()
    candidates=[]
    for pub,sym,closed in rows:
        try:
            d=_published(JournalReader(),pub,owner,CID)
            if d["status"] in ("BUY","SELL") and 0<=now-closed<=600:
                candidates.append(dict(symbol=sym,side=d["status"],age_s=round(now-closed)))
        except Exception: continue
    check("validated_apex11_directional_publications",bool(candidates))
    files=BASE/"terminal/MQL5/Files"
    port=NativeV4FilePort(account_id=CID,account_login=str(login),
                files_dir=files,worker_uid=files.stat().st_uid)
    with monitor_lock():
        folder,receipts=port._dirs()
        check("v4_file_port_bound",folder.is_dir() and receipts.is_dir())
        check("no_legacy_or_v4_request_pending",not (folder/"APEX_NATIVE_ORDER_V1.req").exists()
              and not (folder/"ABUTRON_APEX_V4.req").exists())
        try:
            probe=DemoNativeRequest(owner,CID,"deriv","Deriv-Demo",str(login),
                nonce or "",candidates[0]["symbol"] if candidates else "",
                candidates[0]["side"] if candidates else "",
                "0"*64,rev,"","","",int(now)+10)
            port._capability(probe)
            cap=True
        except Exception:cap=False
        check("ea_produced_v4_revision_capability",cap)
    chart=readjson(SUP/"v4-ro-attachment-evidence.json")
    check("v4_attached",chart.get("state")=="V4_NATIVE_CHART_ATTACHED")
    check("v4_ea_automatic_inputs_on",
          chart.get("metrics",{}).get("automatic_order_input_enabled_at_last_init") is True)
    # First-order readiness uses current owner proof, not a non-existent new fill ACK.
    # Never pretend historical full peak equity or a new order receipt is verified.
    supervisor=readjson(SUP/"evidence.json")
    checks_super=supervisor.get("checks",{})
    check("owner_6207_current_risk_verified",
          checks_super.get("customer_cashflow_adjusted_portfolio_risk") is True
          and supervisor.get("metrics",{}).get("apex11_owner_operational_risk",{}).get(
              "owner_native_current_risk_proven") is True)
    risk=readjson(SUP/"two-broker-native-order-ack-audit.json")
    check("previous_native_broker_receipts_reconciled",
          risk.get("all_existing_broker_native_order_receipts_reconciled") is True
          and risk.get("any_new_broker_order_unexpected_with_crm_off") is False)
    joined=readjson(Path("/var/lib/abutron-customer-native-evidence-join/latest.json"))
    remaining=joined.get("remaining_unverified_connected_sets")
    check("all_connected_broker_accounts_reconciled",remaining==0)
    cost=readjson(SUP/"v4-native-execution-cost-6207.json")
    check("broker_native_quotes_profit_and_margin_verified",
          cost.get("account_suffix")=="6207"
          and cost.get("native_bid_ask_and_ordercalcprofit_verified") is True
          and cost.get("native_minlot_ordercalcmargin_verified") is True)
    # Native OrderCheck is a final *per-proposal* step, not a universal
    # certification just because earlier preflight orders were checked.
    return dict(schema="abutron.apex11.v4.6207.binding_readonly.v1",
        checked_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        state=("APEX11_V4_SESSION_BOUND_NO_BROKER_ORDER_ACK" if all(checks.values())
               else "BLOCKED_NO_V4_ORDER_AUTHORITY"),
        account_suffix="6207",crm_revision=rev,desired_on=desired==1,
        effective_on=effective==1,
        directional_publications=len(candidates),recent_candidates=candidates[:5],
        deriv_native_zero_position_sets=joined.get("native_deriv_zero_exposure_sets_verified"),
        remaining_unverified_connected_sets=remaining,checks=checks,
        blockers=[k for k,v in checks.items() if not v],
        read_only=True,broker_orders_submitted=0,requests_queued=0,
        crm_modified=False,live_authorized=False,
        new_broker_execution_ack_verified=False,
        exact_new_ordercheck_by_this_binding_verified=False,
        historical_true_intraminute_peak_certified=False)

def main():
    if os.geteuid()!=0 or not STATE.is_dir() or STATE.is_symlink():
        raise RuntimeError("PRIVATE_ROOT_STATE_REQUIRED")
    x=inspect()
    path=STATE/"v4-writer-binding-admission-ro.json"
    tmp=STATE/(".binding-"+str(os.getpid())+".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(x,f,sort_keys=True,separators=(",",":"))
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
    print(json.dumps({k:x[k] for k in ("state","directional_publications","remaining_unverified_connected_sets","blockers","broker_orders_submitted")}))

if __name__=="__main__":main()
