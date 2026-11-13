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
EXPECTED_SHA="7858dc5f0c435b106490b1e6053706c40ecc8bf575513d25d147b215e2148816"
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


def account_6207_operational_risk(now):
    """Broker-proven current exposure and cash-day limits for 6207 owner.
    Historical all-time intraminute equity peak is NOT claimed or inferred.
    """
    from decimal import Decimal as D
    base=OUTPUT.parent
    cw=fresh_json(base/"customer-wide-risk-evidence.json",now,45)
    day=fresh_json(base/"six-account-native-daystart-cash-audit.json",now,175)
    obs=fresh_json(base/"six-account-observed-equity.json",now,130)
    hist=fresh_json(base/"six-broker-native-history-reconciliation.json",now,175)
    native=fresh_json(base/"deriv-6207-native-fullrange-history.json",now,175)
    receipts=fresh_json(base/"two-broker-native-order-ack-audit.json",now,50)
    price=fresh_json(base/"v4-native-execution-cost-6207.json",now,75)
    if (cw.get("schema")!="abutron.customer_wide.native_exposure.fail_closed.v1"
        or cw.get("native_current_open_exposure_reconciled") is not True
        or cw.get("unknown_connected_position_sets")!=0
        or cw.get("native_flat_accounts_verified")!=cw.get("connected_accounts")
        or cw.get("native_current_open_stop_risk_usd")!=0):
        raise ValueError("NATIVE_ACCOUNT_CURRENT_EXPOSURE_UNVERIFIED")
    groups=cw.get("owners",{})
    matched=[(hash_,o) for hash_,o in groups.items()
             if any(str(c.get("account_masked","")).endswith("6207")
                    for c in o.get("connections",[]))]
    if len(matched)!=1:raise ValueError("OWNER_6207_NOT_UNIQUE")
    owner_hash,owner=matched[0]
    if (owner.get("current_open_exposure_reconciled") is not True
        or owner.get("unknown_connected_broker_position_sets")!=0
        or owner.get("disconnected_or_error_accounts")!=0
        or owner.get("current_open_stop_risk_usd")!=0):
        raise ValueError("OWNER_CURRENT_RISK_UNVERIFIED")
    connections={}
    for c in owner.get("connections",[]):
        suffix=str(c.get("account_masked",""))[-4:]
        if suffix in connections:raise ValueError("DUPLICATE_OWNER_BROKER")
        connections[suffix]=c
    if set(connections)!={"6207","0512","0178"}:
        raise ValueError("OWNER_CONNECTION_SET_CHANGED")
    for suffix,broker,mode in (("6207","Deriv","DEMO"),
                               ("0512","FP Markets","DEMO"),
                               ("0178","Deriv","LIVE")):
        c=connections[suffix]
        snapshot=c.get("snapshot",{})
        if (c.get("broker")!=broker or c.get("environment")!=mode
            or c.get("current_open_stop_risk_usd")!=0.0
            or snapshot.get("positions_count")!=0
            or snapshot.get("pending_orders_count")!=0):
            raise ValueError("OWNER_BROKER_ACCOUNT_NOT_FLAT_OR_MISMATCHED")
    if (connections["0178"].get("effective_on") is not False
        or connections["0178"]["snapshot"].get("equity_usd")!=0.0):
        raise ValueError("LIVE_ACCOUNT_RISK_NOT_ZERO")
    deriv_eq=D(str(connections["6207"]["snapshot"]["equity_usd"]))
    fp_eq=D(str(connections["0512"]["snapshot"]["equity_usd"]))
    if deriv_eq<=0 or fp_eq<=0:raise ValueError("DEMO_EQUITY_INVALID")
    present=deriv_eq+fp_eq
    if (native.get("account_suffix")!="6207"
        or native.get("full_range_cashflow_to_broker_balance_reconciled") is not True
        or abs(D(str(native.get("current_native_broker_balance_usd")))-deriv_eq)>D(".01")
        or hist.get("five_demo_native_trade_windows_reconciled") is not True
        or hist.get("fp_two_demo_balance_cashflows_reconciled") is not True):
        raise ValueError("BROKER_NATIVE_CASHFLOW_RECONCILIATION_MISSING")
    if (day.get("schema")!="abutron.six_account.native_utc_daystart_cash.reconstruction.ro.v1"
        or day.get("daystart_utc")!=dt.datetime.fromtimestamp(now,dt.timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")):
        raise ValueError("UTC_DAYSTART_CASH_MISMATCH")
    pairs={a.get("account_suffix"):a for a in day.get("accounts",[])}
    if (pairs.get("6207",{}).get("verified_daystart_cash_balance") is not True
        or pairs.get("0512",{}).get("utc_daystart_cash_balance_reconstructed_from_complete_selected_window") is not True):
        raise ValueError("DEMO_NATIVE_DAYSTART_CASH_UNVERIFIED")
    daystart=D(str(pairs["6207"]["utc_daystart_reconstructed_cash_balance_usd"]))+D(str(pairs["0512"]["utc_daystart_reconstructed_cash_balance_usd"]))
    if daystart<=0:raise ValueError("DAYSTART_CASH_INVALID")
    high=obs.get("customer_owner_sampled_equity",{}).get(owner_hash)
    if (obs.get("native_accounts_sampled")!=cw.get("connected_accounts")
        or obs.get("current_open_exposure_reconciled") is not True
        or high is None
        or abs(D(str(high.get("latest_observed_equity_usd")))-present)>D(".05")
        or high.get("largest_missing_sample_gap_minutes",999)>2):
        raise ValueError("OWNER_NATIVE_EQUITY_OBSERVATIONS_NOT_CURRENT")
    if (receipts.get("all_existing_broker_native_order_receipts_reconciled") is not True
        or receipts.get("any_new_broker_order_unexpected_with_crm_off") is not False):
        raise ValueError("BROKER_NATIVE_PRIOR_ORDER_RECONCILIATION_UNVERIFIED")
    if (price.get("account_suffix")!="6207"
        or price.get("native_bid_ask_and_ordercalcprofit_verified") is not True
        or price.get("native_minlot_ordercalcmargin_verified") is not True
        or abs(D(str(price.get("account_equity_usd")))-deriv_eq)>D(".05")):
        raise ValueError("NATIVE_BROKER_QUOTE_EQUITY_MISMATCH")
    trade_budget=deriv_eq*D("0.001")
    gross_open=D("0")
    daily_loss=max(D("0"),daystart-present)
    if (gross_open+trade_budget>present*D(".02")
        or daily_loss+trade_budget>daystart*D(".03")
        or gross_open+trade_budget>present*D(".20")):
        raise ValueError("OWNER_PRESERVED_PORTFOLIO_OR_DAILY_RISK_LIMIT")
    return {"native_owner_account_set":["Deriv DEMO 6207","FP Markets DEMO 0512",
                                       "Deriv LIVE 0178 (OFF, 0 USD)"],
            "current_total_owner_equity_usd":str(present),
            "deriv_6207_equity_usd":str(deriv_eq),
            "daystart_utc_cash_reconstructed_usd":str(daystart),
            "cash_realized_daily_loss_usd":str(daily_loss),
            "deriv_trade_0_10pct_budget_usd":str(trade_budget),
            "current_owner_open_stop_risk_usd":"0",
            "preserved_2pct_aggregate_stop_risk":True,
            "preserved_3pct_daily_cash_loss_limit":True,
            "preserved_20pct_portfolio_open_risk_ceiling":True,
            "true_historical_intraminute_equity_peak_unverified":True,
            "owner_native_current_risk_proven":True}

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
        # Same SQLite read snapshot as portal flags: independently verify
        # the newly installed transactional monotonic revision, but do not
        # infer any execution authority or broker ACK from its existence.
        fence=con.execute("""SELECT revision,desired_enabled,effective_enabled,
                            connection_status,ack_revision,ack_expires_utc
                            FROM abutron_v4_6207_activation_revision
                            WHERE connection_id=?""",(CID,)).fetchall()
        ledger=(len(fence)==1 and type(fence[0][0]) is int and
                fence[0][0]>=1 and
                fence[0][1:4]==(desired,effective,status))
        gate("crm_monotonic_revision_ledger",ledger,
             "CRM_REVISION_LEDGER_MISSING_OR_DIVERGED")
        if ledger:
            metrics["crm_revision"]=fence[0][0]
            metrics["crm_broker_ack_recorded"]=fence[0][4] is not None
            metrics["crm_broker_ack_revision_matches"]=(
                fence[0][4] is not None and fence[0][4]==fence[0][0])
        gate("crm_revision_fenced_and_broker_ack",
             ledger and effective==1 and fence[0][4]==fence[0][0]
             and type(fence[0][5]) is int and fence[0][5]>int(now),
             "CRM_NATIVE_ACTIVATION_REVISION_ACK_NOT_ACTIVE")
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
        # Genuine read-only MT5 WebRequest STATUS|revision echoed by THIS EA.
        # This is NOT a CRM execution ACK or a broker order ACK.
        matched=(valid and x[5].isdigit() and
                 int(x[5])==metrics.get("crm_revision") and
                 x[7:]==["0.10","OFF_REVISION_CHECK_AT_CONSUME","LIVE_FORBIDDEN"])
        gate("v4_crm_revision_readonly_status_ack",matched,
             "NATIVE_CRM_REVISION_STATUS_NOT_MATCHED")
    except (OSError,ValueError,TypeError,UnicodeError):
        gate("v4_capability_file_fresh",False,"V4_CAPABILITY_NOT_PRESENT")
        gate("v4_crm_revision_readonly_status_ack",False,
             "NATIVE_CRM_REVISION_STATUS_UNAVAILABLE")
    # Independently consume actual same-release, post-rebuild MT5 HTTP proof
    # and the separate authenticated native chart OnInit audit. Never infer
    # broker order acknowledgement, costs or customer-wide risk from either.
    try:
        web=fresh_json(OUTPUT.parent/"mt5-webrequest-rebuild-attestation.json",now,155)
        chart=fresh_json(OUTPUT.parent/"v4-ro-attachment-evidence.json",now,110)
        chart_checks=chart.get("checks",{})
        chart_metrics=chart.get("metrics",{})
        web_good=(web.get("schema")=="abutron.mt5.deriv6207.webrequest.rebuild-attestation.v1"
                  and web.get("account_suffix")=="6207"
                  and web.get("environment")=="DEMO"
                  and web.get("webrequest_rebuild_survivability_verified") is True
                  and web.get("native_http_status_proof_verified") is True
                  and web.get("distinct_complete_profiles_checked")==2
                  and web.get("blockers")==[])
        chart_good=(chart.get("schema")=="abutron.v4.native.chart_attachment.v2"
                    and chart.get("state")=="V4_NATIVE_CHART_ATTACHED"
                    and chart.get("handover_authorized") is False
                    and chart.get("broker_order_ack") is False
                    and chart_checks.get("independent_native_mt5_chart_load") is True
                    and chart_checks.get("v4_expert_native_oninit_proven") is True
                    and chart_checks.get("exact_v4_release_binary_installed") is True
                    and chart_metrics.get("v4_revision_capability_file_present") is True
                    and chart_metrics.get("release_sha256")==EXPECTED_SHA)
        gate("v4_webrequest_same_release_rebuild",web_good,
             "V4_WEBREQUEST_SAME_RELEASE_REBUILD_NOT_VERIFIED")
        gate("v4_chart_independently_attached",chart_good and web_good,
             "V4_CHART_OR_WEBREQUEST_REBUILD_NOT_CERTIFIED")
    except (OSError,ValueError,TypeError,KeyError,UnicodeError):
        gate("v4_webrequest_same_release_rebuild",False,
             "V4_WEBREQUEST_ATTESTATION_STALE_OR_UNAVAILABLE")
        gate("v4_chart_independently_attached",False,
             "V4_CHART_OR_WEBREQUEST_PROOF_STALE_OR_UNAVAILABLE")

    # V101 clock-corrected, order-inert native FP evidence, scoped to 6207 owner.
    # The broker window uses a bounded estimated terminal server clock;
    # this does NOT prove current executable quotes or full risk coverage.
    fp_proofs=[]
    for conn,broker,env,status in accounts:
        if not (broker=="FP Markets" and env=="DEMO" and status=="CONNECTED"):continue
        proof={"account_suffix":conn[-6:],"positions":None,"protected":False,
               "clock_fresh":False,"binary_attested":False,
               "quote_fresh_for_execution":False}
        try:
            home=FP/("abutron-client-mt5-"+conn)
            h=fresh_json(home/"worker-health.json",now,30)
            n=h.get("nonce")
            if (h.get("id")!=conn or h.get("broker")!="FP Markets" or
                h.get("mode")!="DEMO" or h.get("server")!="FPMarketsSC-Demo" or
                h.get("status")!="CONNECTED" or
                h.get("heartbeat_fresh") is not True or not isinstance(n,str) or
                HEX32.fullmatch(n) is None):raise ValueError("FP_WORKER_UNVERIFIED")
            binary=home/"terminal/MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5"
            data,_=stable_file(binary,100000)
            proof["binary_attested"]=hmac.compare_digest(
                hashlib.sha256(data).hexdigest(),
                "3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac")
            if not proof["binary_attested"]:raise ValueError("FP_V101_BINARY_CHANGED")
            with sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=5) as rd:
                rd.execute("PRAGMA query_only=ON")
                record=rd.execute("SELECT account_id,account_reference,broker_server FROM apex_mt5_connections WHERE id=?",(conn,)).fetchone()
            if not record or record[0]!=account or record[2]!="FPMarketsSC-Demo":
                raise ValueError("FP_OWNER_CONNECTION_MISMATCH")
            path=home/"terminal/MQL5/Files"/("ABUTRON_FP_ACCOUNT_HISTORY_V101_"+n+".txt")
            raw,st=stable_file(path,4000000);x=raw.decode("utf-8-sig").splitlines()
            if (len(x)<21 or x[:6]!=["ABUTRON_FP_ACCOUNT_HISTORY_V1",n,
                h.get("proof_owner"),record[2],str(record[1]),"DEMO"] or
                x[19]!="BROKER_NATIVE_NO_ORDER_FUNCTIONS"):
                raise ValueError("FP_V101_HISTORY_IDENTITY_INVALID")
            pos=int(x[14]);pending=int(x[15]);deals=int(x[16])
            if (not 0<=pos<=500 or not 0<=pending<=500 or not 0<=deals<=10000 or
                pos+pending+deals!=len(x)-21 or
                x[-1]!="END\t"+"\t".join([str(pos),str(pending),str(deals)])):
                raise ValueError("FP_V101_COUNTS_INVALID")
            rows=[z.split("\t") for z in x[20:-1] if z.startswith("P\t")]
            wrong=0
            for z in rows:
                if len(z)!=13 or z[3] not in ("0","1"):
                    wrong+=1;continue
                m,sl,tp=[Decimal(v) for v in (z[6],z[7],z[8])]
                if not all(v.is_finite() and v>0 for v in (m,sl,tp)):
                    wrong+=1;continue
                if not ((z[3]=="0" and sl<m<tp) or
                        (z[3]=="1" and tp<m<sl)):
                    wrong+=1
            proof["positions"]=pos
            proof["pending_orders"]=pending
            proof["deals_90d"]=deals
            proof["stop_geometry_unverified_or_beyond_mark"]=wrong
            proof["protected"]=len(rows)==pos and wrong==0
            off=int(x[7]);stamp=int(x[6]);end_utc=int(x[18])-off-60
            proof["history_age_seconds"]=round(now-end_utc)
            proof["clock_source"]="TERMINAL_TIME_TRADESERVER_ESTIMATED"
            proof["clock_fresh"]=(off==7200 and
                abs(stamp-end_utc)<=15 and
                -5<=now-end_utc<=130 and
                -5<=now-stamp<=130 and -5<=now-st.st_mtime<=130)
        except (OSError,ValueError,TypeError,UnicodeError,IndexError,InvalidOperation,sqlite3.Error):
            proof["source_invalid_or_unavailable"]=True
        fp_proofs.append(proof)
    metrics["fp_demo_broker_proofs"]=fp_proofs
    gate("fp_current_broker_history",bool(fp_proofs) and all(p["clock_fresh"] and p["binary_attested"] for p in fp_proofs),
         "FP_BROKER_HISTORY_STALE_OR_UNAVAILABLE")
    try:
        metrics["apex11_owner_operational_risk"]=account_6207_operational_risk(now)
        gate("customer_cashflow_adjusted_portfolio_risk",True,"")
    except (OSError,ValueError,TypeError,KeyError,InvalidOperation) as exc:
        metrics["apex11_owner_risk_reason"]=str(exc)[:115]
        gate("customer_cashflow_adjusted_portfolio_risk",False,
             "NATIVE_OWNER_DEMO_RISK_BUDGET_UNVERIFIED")
    metrics["risk_caps"]={"per_trade":"0.001","open":"0.02","daily":"0.03","drawdown":"0.20"}

    try:
        st=Path("/var/lib/apex-client-feed/execution-router/execution-writer.lock").lstat()
        safe=(stat.S_ISREG(st.st_mode) and st.st_uid==0 and
              st.st_nlink==1 and not st.st_mode&0o077)
        gate("root_native_writer_lock_file",safe,"WRITER_LOCK_PERMISSIONS_UNTRUSTED")
    except OSError:
        gate("root_native_writer_lock_file",False,"WRITER_LOCK_NOT_FOUND")
    try:
        ack=fresh_json(OUTPUT.parent/"two-broker-native-order-ack-audit.json",now,50)
        folder=WORKER/"terminal/MQL5/Files/ABUTRON"
        conflicting=any((folder/name).exists()
                        for name in ("APEX_NATIVE_ORDER_V1.req",
                                     "ABUTRON_APEX_V4.req"))
        eligible=(checks.get("root_native_writer_lock_file") is True
                  and _active("abutron-apex-native-orders.timer")!="active"
                  and _active("abutron-6207-multi-trial-dispatch.timer")!="active"
                  and _active("abutron-6207-one-shot-dispatch.timer")!="active"
                  and ack.get("all_existing_broker_native_order_receipts_reconciled") is True
                  and ack.get("any_new_broker_order_unexpected_with_crm_off") is False
                  and not conflicting)
        gate("exclusive_writer_and_unknown_orders_reconciled",eligible,
             "EXCLUSIVE_V4_WRITER_OR_UNKNOWN_RECEIPT")
    except (OSError,ValueError,TypeError,KeyError):
        gate("exclusive_writer_and_unknown_orders_reconciled",False,
             "EXCLUSIVE_V4_NATIVE_EVIDENCE_UNAVAILABLE")
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
