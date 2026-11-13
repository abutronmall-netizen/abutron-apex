#!/usr/bin/python3
"""ABUTRON customer-wide broker exposure inventory (READ-ONLY, FAIL-CLOSED).

Does not authenticate for trading, set effective ON, send any order, or claim
market-closed estimated broker clock equals a fresh tradable quote. Missing
broker position/USD stop risk/day-start/peak snapshots are blockers.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import time

CRM=Path("/var/lib/apex-signup/accounts.sqlite3")
PRIVATE=Path("/var/lib/private")
FP_PUBLISHED=Path("/var/lib/apex-signup/fp-native-history")
REPORT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/customer-wide-risk-evidence.json")
APPROVED_FP_V101_SHA="3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac"
CAPS={"per_trade_pct":0.10,"aggregate_open_pct":2.0,
      "daily_loss_pct":3.0,"max_drawdown_pct":20.0}

def readfile(p:Path, maxbytes=2000000):
    if p.is_symlink(): raise ValueError("SYMLINK_DENIED")
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or
            before.st_mode&0o022 or before.st_size<2 or before.st_size>maxbytes):
            raise ValueError("FILE_NOT_TRUSTED")
        blob=os.read(fd,maxbytes+1)
        after=os.fstat(fd)
        if (len(blob)!=before.st_size or
            (before.st_ino,before.st_dev,before.st_mtime_ns,before.st_size)!=
            (after.st_ino,after.st_dev,after.st_mtime_ns,after.st_size)):
            raise ValueError("READ_RACE")
        return blob,before
    finally:os.close(fd)

def utc_age(iso,now):
    a=dt.datetime.fromisoformat(iso)
    if a.utcoffset() is None:raise ValueError("NAIVE_CLOCK")
    return now-a.timestamp()

def stop_geometry(pos):
    side=pos["side"]
    s=pos.get("stop_loss")
    t=pos.get("take_profit")
    mark=pos.get("current_price")
    entry=pos.get("open_price")
    lots=pos.get("volume")
    if (side not in ("BUY","SELL") or
        not all(type(v) in (float,int) and math.isfinite(v) and v>0
                for v in (s,t,mark,entry,lots))):
        return "MISSING_OR_INVALID_NATIVE_STOP_TP"
    if side=="BUY" and not (s<mark<t):
        return "STOP_GEOMETRY_BEYOND_LAST_BROKER_MARK"
    if side=="SELL" and not (t<mark<s):
        return "STOP_GEOMETRY_BEYOND_LAST_BROKER_MARK"
    return "LAST_MARK_GEOMETRY_PLAUSIBLE_NOT_USD_RISK_CERTIFIED"

def fp_snapshot(cid,login,worker,now):
    home=PRIVATE/("abutron-client-mt5-"+cid)
    binary=home/"terminal/MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5"
    data,_=readfile(binary,100000)
    if hashlib.sha256(data).hexdigest()!=APPROVED_FP_V101_SHA:
        raise ValueError("FP_V101_EX5_HASH_CHANGED")
    nonce=worker.get("nonce")
    if type(nonce) is not str or len(nonce)!=32 or any(c not in "0123456789abcdef" for c in nonce):
        raise ValueError("FP_NONCE_INVALID")
    raw,mtime=readfile(home/"terminal/MQL5/Files"/("ABUTRON_FP_ACCOUNT_HISTORY_V101_"+nonce+".txt"),4000000)
    if not -3<=now-mtime.st_mtime<=135:
        raise ValueError("FP_NATIVE_V101_NOT_FRESH")
    doc,st=readfile(FP_PUBLISHED/(cid+".json"),3000000)
    if not -3<=now-st.st_mtime<=150:
        raise ValueError("FP_PUBLISHER_STALE")
    snap=json.loads(doc)
    # Reader and publisher have independent 60-second schedules. Retain the
    # root-validated published snapshot if the native source has *advanced*
    # since publication; do not pretend the new bytes were part of that proof.
    published_digest=snap.get("native_file_sha256")
    native_digest=hashlib.sha256(raw).hexdigest()
    valid_published_digest=(type(published_digest) is str and
          len(published_digest)==64 and
          all(x in "0123456789abcdef" for x in published_digest))
    advanced_after_publish=(valid_published_digest and
          0<=mtime.st_mtime-st.st_mtime<=130)
    if not (valid_published_digest and
            (published_digest==native_digest or advanced_after_publish)):
        raise ValueError("FP_NATIVE_PUBLISHED_SHA_OR_ROLLOVER_UNVERIFIED")
    if (snap.get("schema")!="abutron.fpmarkets.native.account_history.readonly.v1" or
        snap.get("producer_build")!="FP_HISTORY_V101_READONLY_TIMETRADESERVER_ESTIMATED" or
        snap.get("account_masked")!="••••"+login[-4:] or
        snap.get("environment")!="DEMO" or snap.get("account_currency")!="USD" or
        snap.get("history_verified_from_mt5") is not True or
        snap.get("history_complete_within_selected_window") is not True or
        snap.get("execution_enabled") is not False or
        snap.get("broker_execution_ack_certified") is not False or
        snap.get("customer_portfolio_risk_certified") is not False or
        snap.get("market_quote_fresh_for_execution") is not False or
        snap.get("broker_clock_offset_seconds")!=7200 or
        not -3<=utc_age(snap["generated_at_utc"],now)<=150 or
        not -3<=utc_age(snap["broker_export_at_utc"],now)<=150):
        raise ValueError("FP_VERIFIED_PUBLISHER_IDENTITY_OR_TIME_INVALID")
    p=snap.get("positions")
    o=snap.get("pending_orders")
    if (not isinstance(p,list) or not isinstance(o,list) or
        snap["open_positions_count"]!=len(p) or
        snap["pending_orders_count"]!=len(o)):
        raise ValueError("FP_POSITION_COUNTS_INCONSISTENT")
    positions=[]
    for pos in p:
        geometry=stop_geometry(pos)
        positions.append({"symbol":pos["symbol"],"side":pos["side"],
                         "lots":pos["volume"],"floating_usd":pos["floating_profit_usd"],
                         "stop_geometry":geometry,
                         "broker_native_ordercalcprofit_usd_verified":False})
    receipt=independently_verify_fp_native_receipts(
        cid,login,len(p),len(o),snap["equity_usd"],now)
    return {"broker":"FP Markets","account":"••••"+login[-4:],
            "positions_count":len(p),"pending_orders_count":len(o),
            "deals_90d":snap.get("broker_deals_count"),
            "balance_usd":snap["balance_usd"],"equity_usd":snap["equity_usd"],
            "free_margin_usd":snap["free_margin_usd"],
            "floating_usd":snap["account_floating_profit_usd"],
            "positions":positions,"source":"AUTHENTICATED_V101_READONLY",
            "source_broker_server_clock_estimated":True,
            "source_advanced_since_publisher_read":published_digest!=native_digest,
            "all_position_usd_stop_risk_proved":len(p)==0 and len(o)==0,
            "historical_broker_receipt_reconciliation":receipt,
            "native_receipt_reconciliation_verified":True,
            "market_quote_fresh_for_trading":False}

FP_DUAL_RECONCILIATION=Path("/var/lib/abutron-fp-execution/dual-account-reconciliation/latest.json")

def independently_verify_fp_native_receipts(cid,login,positions,pending,equity,now):
    """A second reader verifies broker-native FP 90d history and ACK ledger.

    Historical broker receipt ACK does not authorize a new execution ACK.
    """
    blob,st=readfile(FP_DUAL_RECONCILIATION,300000)
    if not -3<=now-st.st_mtime<=145:
        raise ValueError("FP_DUAL_ACCOUNT_RECEIPT_REPORT_STALE")
    d=json.loads(blob)
    if (d.get("schema")!="abutron.fpmarkets.dual_demo_native_reconciliation.readonly.v1"
        or d.get("state")!="RECONCILED_READONLY"
        or d.get("broker_order_authorized") is not False
        or d.get("orders_submitted_by_job")!=0
        or d.get("client_switches_modified") is not False
        or not -3<=utc_age(d.get("at_utc",""),now)<=145):
        raise ValueError("FP_DUAL_BROKER_RECEIPT_CONTRACT_INVALID")
    accounts=d.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=2:
        raise ValueError("FP_DUAL_ACCOUNT_COUNT_INVALID")
    matches=[x for x in accounts if x.get("connection_suffix")==cid[-6:]
             and x.get("account_suffix")==str(login)[-4:]]
    if len(matches)!=1:
        raise ValueError("FP_INDEPENDENT_ACCOUNT_LINK_NOT_UNIQUE")
    account=matches[0]
    if (account.get("state")!="RECONCILED_READONLY"
        or account.get("connected") is not True
        or account.get("effective_on") is not False
        or account.get("unresolved_receipts")!=0
        or type(account.get("historical_broker_ack")) is not int
        or account["historical_broker_ack"]<0
        or account.get("positions")!=positions or account.get("pending")!=pending
        or type(account.get("equity_usd")) not in (int,float)
        or abs(account["equity_usd"]-equity)>0.01):
        raise ValueError("FP_NATIVE_HISTORY_POSITION_EQUITY_OR_RECEIPT_DIVERGENCE")
    return {"historical_broker_ack_count":account["historical_broker_ack"],
            "90day_broker_trade_deals":account["historical_trade_deals"],
            "unresolved_historical_receipts":0,
            "current_execution_ack_granted":False}

def verified_current_flat_exposure(rec):
    """Only account-bound fresh native proof with zero positions and zero pending."""
    snap=rec.get("snapshot",{})
    if type(snap)!=dict or rec.get("connection_status")!="CONNECTED":
        return False
    if snap.get("positions_count")!=0 or snap.get("pending_orders_count")!=0:
        return False
    if rec.get("broker")=="Deriv" and rec.get("environment")=="DEMO":
        return (rec.get("broker_position_reconciliation_status")=="ZERO_EXPOSURE_DUAL_NATIVE_VERIFIED"
                and snap.get("all_current_position_counts_verified") is True
                and snap.get("all_current_positions_sl_tp_usd_risk_verified") is True
                and snap.get("open_position_usd_stop_risk")==0.0)
    if rec.get("broker")=="FP Markets" and rec.get("environment")=="DEMO":
        return (rec.get("broker_position_reconciliation_status")=="POSITIONS_COUNT_VERIFIED_READONLY"
                and snap.get("native_receipt_reconciliation_verified") is True
                and snap.get("all_position_usd_stop_risk_proved") is True)
    if rec.get("broker")=="Deriv" and rec.get("environment")=="LIVE":
        return (rec.get("broker_position_reconciliation_status")=="SIGNED_LIVE_NO_ORDER_POSITION_COUNTS_VERIFIED"
                and snap.get("positions_count_verified_from_live_broker") is True
                and snap.get("account_execution_authorized") is False
                and snap.get("broker_trade_allowed") is False)
    return False

DERIV_NATIVE_RECONCILIATION=Path("/var/lib/abutron-deriv-multi-native-reconciliation/latest.json")

def deriv_demo_snapshot(cid,login,worker,now):
    """Independent triple-DEMO sidecars; inventory only, never order authority."""
    if (worker.get("id")!=cid or worker.get("broker")!="Deriv" or
        worker.get("mode")!="DEMO" or worker.get("server")!="Deriv-Demo" or
        worker.get("status")!="CONNECTED" or worker.get("heartbeat_fresh") is not True):
        raise ValueError("DERIV_DEMO_WORKER_IDENTITY_INVALID")
    raw,st=readfile(DERIV_NATIVE_RECONCILIATION,500000)
    if not -3<=now-st.st_mtime<=120:
        raise ValueError("DERIV_NATIVE_RECONCILIATION_STALE")
    d=json.loads(raw)
    if (d.get("schema")!="abutron.deriv.three_demo.native_dualproof.readonly.v1" or
        d.get("all_verified") is not True or d.get("execution_authorized") is not False or
        d.get("customer_wide_risk_certified") is not False or
        d.get("complete_historical_reconciliation") is not False or
        d.get("orders_submitted")!=0 or
        not -3<=utc_age(d.get("generated_utc",""),now)<=120):
        raise ValueError("DERIV_NATIVE_ROOT_SOURCE_CONTRACT_INVALID")
    accounts=d.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=3:
        raise ValueError("DERIV_NATIVE_DEMO_ACCOUNT_COUNT_INVALID")
    suffixes=[a.get("account_suffix") for a in accounts]
    if sorted(suffixes)!=["6207","7593","9244"]:
        raise ValueError("DERIV_NATIVE_DEMO_ACCOUNT_IDENTITIES_INVALID")
    for a in accounts:
        if (a.get("state")!="VERIFIED_READONLY" or
            a.get("current_exposure")!="ZERO_DUAL_NATIVE_PROOF" or
            a.get("broker_execution_authorized") is not False or
            a.get("positions")!=0 or a.get("pending_orders")!=0 or
            a.get("window_complete") is not False or
            type(a.get("matched_position_ids")) is not int or
            a["matched_position_ids"]<=0 or
            not all(type(a.get(k)) in (int,float) and
                    math.isfinite(a[k]) and a[k]>=0
                    for k in ("balance_usd","equity_usd"))):
            raise ValueError("DERIV_NATIVE_DEMO_PROOF_INCOMPLETE")
    suffix=str(login)[-4:]
    hits=[a for a in accounts if a["account_suffix"]==suffix]
    if len(hits)!=1 or not str(login).isdigit():
        raise ValueError("DERIV_NATIVE_ACCOUNT_SUFFIX_MISMATCH")
    a=hits[0]
    return {
        "broker":"Deriv","account":"••••"+suffix,"environment":"DEMO",
        "positions_count":0,"pending_orders_count":0,
        "balance_usd":a["balance_usd"],"equity_usd":a["equity_usd"],
        "open_position_usd_stop_risk":0.0,
        "source":"AUTHENTICATED_INDEPENDENT_DUAL_NATIVE_DEMO_PROOF",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "matched_position_ids":a["matched_position_ids"],
        "native_deals_exported":a["native_deals_in_export_window"],
        "all_current_position_counts_verified":True,
        "all_current_positions_sl_tp_usd_risk_verified":True,
        "full_historical_exit_ledger_certified":False,
        "account_equity_daystart_and_peak_certified":False,
        "broker_execution_ack_certified":False,
        "market_quote_fresh_for_execution":False,
        "execution_authorized":False}

def inspect(now=None):
    now=time.time() if now is None else float(now)
    with sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=6) as db:
        db.execute("PRAGMA query_only=ON")
        rows=db.execute("""
            SELECT x.id,x.account_id,x.account_reference,x.broker,x.environment,
                   x.status,coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
            FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t
              ON t.connection_id=x.id ORDER BY x.account_id,x.broker,x.id
        """).fetchall()
    owners={}
    total_known_positions=0
    unknown_connected_exposure=0
    stop_geometry_bad=0
    connected_count=0
    for cid,owner,login,broker,environment,status,desired,effective in rows:
        owner_label=hashlib.sha256(str(owner).encode()).hexdigest()[:12]
        cust=owners.setdefault(owner_label,{"connections":[],"known_fp_positions":0,
                   "unknown_connected_broker_position_sets":0,
                   "disconnected_or_error_accounts":0,
                   "all_broker_equity_daystart_peak_reconciled":False,
                   "risk_certified":False})
        rec={"id_suffix":cid[-6:],"broker":broker,"environment":environment,
             "account_masked":"••••"+str(login)[-4:],
             "connection_status":status,"requested_on":desired==1,
             "effective_on":effective==1,
             "broker_position_reconciliation_status":"UNKNOWN",
             "risk_verified":False}
        if status!="CONNECTED":
            rec["blockers"]=["DISCONNECTED_OR_ERROR_ACCOUNT_EXPOSURE_UNKNOWN"]
            cust["disconnected_or_error_accounts"]+=1
        else:
            connected_count+=1
            try:
                worker,st=readfile(PRIVATE/("abutron-client-mt5-"+cid)/"worker-health.json")
                w=json.loads(worker)
                if (w.get("id")!=cid or w.get("status")!="CONNECTED" or
                    w.get("heartbeat_fresh") is not True or
                    not -3<=now-st.st_mtime<=30):
                    raise ValueError("BROKER_WORKER_NOT_CURRENT")
                if broker=="FP Markets" and environment=="DEMO":
                    snap=fp_snapshot(cid,str(login),w,now)
                    rec.update({"broker_position_reconciliation_status":"POSITIONS_COUNT_VERIFIED_READONLY",
                                "snapshot":snap})
                    cust["known_fp_positions"]+=snap["positions_count"]
                    total_known_positions+=snap["positions_count"]
                    stop_geometry_bad+=sum(p["stop_geometry"]!="LAST_MARK_GEOMETRY_PLAUSIBLE_NOT_USD_RISK_CERTIFIED"
                                          for p in snap["positions"])
                    rec["blockers"]=["ACCOUNT_EQUITY_DAYSTART_PEAK_UNVERIFIED",
                                    "NATIVE_BROKER_ACK_ORDER_RECONCILIATION_PENDING"]
                    rec["entry_blockers"]=["FP_QUOTE_CLOCK_OR_EXECUTABLE_COST_UNCERTIFIED"]
                    if snap["positions_count"] or snap["pending_orders_count"]:
                        rec["blockers"] += ["NATIVE_ORDER_CALC_PROFIT_PER_POSITION_MISSING"]
                    # Zero currently open positions need no hypothetical USD stop
                    # calculation. Entry quote freshness is a separate guard.
                    if any(p["stop_geometry"]!="LAST_MARK_GEOMETRY_PLAUSIBLE_NOT_USD_RISK_CERTIFIED"
                           for p in snap["positions"]):
                        rec["blockers"].append("FP_STOP_BEYOND_LAST_BROKER_MARK")
                elif broker=="Deriv" and environment=="DEMO":
                    snap=deriv_demo_snapshot(cid,str(login),w,now)
                    rec.update({"broker_position_reconciliation_status":
                                "ZERO_EXPOSURE_DUAL_NATIVE_VERIFIED",
                                "snapshot":snap})
                    cust["known_deriv_demo_positions"]=cust.get("known_deriv_demo_positions",0)
                    rec["blockers"]=["ACCOUNT_EQUITY_DAYSTART_PEAK_UNVERIFIED",
                                    "COMPLETE_BROKER_HISTORY_EXIT_LEDGER_UNVERIFIED",
                                    "NATIVE_BROKER_ACK_ORDER_RECONCILIATION_PENDING"]
                elif broker=="Deriv" and environment=="LIVE":
                    # Signed no-order LIVE MT5 proof. Inventory ONLY: never authorizes
                    # LIVE trading, day-start/peak loss, or customer-wide risk.
                    from abutron_deriv_live_snapshot_ro import native_live_snapshot
                    snap=native_live_snapshot(cid,str(login),w,now,readfile)
                    rec.update({"broker_position_reconciliation_status":
                                "SIGNED_LIVE_NO_ORDER_POSITION_COUNTS_VERIFIED",
                                "snapshot":snap})
                    cust["known_live_positions"]=cust.get("known_live_positions",0)+snap["positions_count"]
                    rec["blockers"]=["ACCOUNT_EQUITY_DAYSTART_PEAK_UNVERIFIED",
                                    "NATIVE_BROKER_ACK_ORDER_RECONCILIATION_PENDING"]
                    rec["entry_blockers"]=["LIVE_BROKER_TRADE_PERMISSION_OFF",
                                            "LIVE_EQUITY_ZERO"]
                    if snap["positions_count"] or snap["pending_orders_count"]:
                        rec["blockers"].append("LIVE_NATIVE_POSITION_USD_STOP_RISK_UNCERTIFIED")
                else:
                    unknown_connected_exposure+=1
                    cust["unknown_connected_broker_position_sets"]+=1
                    rec["blockers"]=["COMPLETE_BROKER_OPEN_POSITIONS_AND_PENDING_ORDERS_MISSING",
                                    "ACCOUNT_EQUITY_DAYSTART_PEAK_UNVERIFIED",
                                    "NATIVE_BROKER_ACK_ORDER_RECONCILIATION_PENDING"]
            except (OSError,ValueError,TypeError,KeyError,IndexError,UnicodeError):
                unknown_connected_exposure+=1
                cust["unknown_connected_broker_position_sets"]+=1
                rec["blockers"]=["AUTHENTICATED_BROKER_POSITION_SNAPSHOT_MISSING"]
        if effective==1: rec.setdefault("blockers",[]).append("UNEXPECTED_EFFECTIVE_ON")
        certified_flat=verified_current_flat_exposure(rec)
        rec["current_open_exposure_reconciled"]=certified_flat
        rec["current_open_stop_risk_usd"]=0.0 if certified_flat else None
        cust["connections"].append(rec)
    # This is CURRENT observable open-position risk only; never represent
    # it as complete day-start/peak equity, historic trades or execution ACK.
    for owner in owners.values():
        flags=[a["current_open_exposure_reconciled"] for a in owner["connections"]]
        owner["current_open_exposure_reconciled"]=bool(flags) and all(flags)
        owner["current_open_stop_risk_usd"]=(
            0.0 if owner["current_open_exposure_reconciled"] else None)
    all_flat=(bool(rows) and len(rows)==6 and connected_count==6
              and unknown_connected_exposure==0 and
              all(a["current_open_exposure_reconciled"]
                  for owner in owners.values() for a in owner["connections"]))
    blocked=sorted(set(b for cust in owners.values() for rec in cust["connections"]
                       for b in rec.get("blockers",[])))
    if not rows:blocked.append("NO_CUSTOMER_CONNECTIONS")
    return {"schema":"abutron.customer_wide.native_exposure.fail_closed.v1",
           "checked_utc":dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
           "status":"BLOCKED_INCOMPLETE_EXPOSURE",
           "customer_owner_groups":len(owners),"linked_accounts":len(rows),
           "connected_accounts":connected_count,
           "connected_fp_position_sets_verified":sum(
              r["broker_position_reconciliation_status"]=="POSITIONS_COUNT_VERIFIED_READONLY"
              for c in owners.values() for r in c["connections"]),
           "confirmed_fp_open_positions":total_known_positions,
           "open_positions_stop_beyond_last_mark":stop_geometry_bad,
           "unknown_connected_position_sets":unknown_connected_exposure,
           "native_current_open_exposure_reconciled":all_flat,
           "native_current_open_stop_risk_usd":0.0 if all_flat else None,
           "native_flat_accounts_verified":sum(a["current_open_exposure_reconciled"]
                                                for c in owners.values()
                                                for a in c["connections"]),
           "current_open_exposure_vs_full_drawdown_risk_distinguished":True,
           "blockers":blocked,"owners":owners,"risk_caps_policy":CAPS,
           "portfolio_cash_usd_stop_risk_fully_quantified":False,
           "day_start_peak_drawdown_from_native_broker_certified":False,
           "customer_wide_risk_certified":False,
           "authenticated_broker_execution_ack_certified":False,
           "v4_handover_authorized":False,"live_authorized":False,
           "orders_submitted_by_audit":0,"client_switches_modified":False}

def main():
    doc=inspect()
    parent=REPORT.parent
    if not parent.is_dir() or parent.is_symlink() or parent.stat().st_uid!=0 or parent.stat().st_mode&0o077:
        raise SystemExit("UNTRUSTED_PRIVATE_EVIDENCE_DIRECTORY")
    temp=parent/(".customer-exposure-evidence.%d.tmp"%os.getpid())
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(doc,f,sort_keys=True,separators=(",",":"),allow_nan=False)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(temp,REPORT)
    finally:
        try:temp.unlink()
        except FileNotFoundError:pass
    print(json.dumps({"status":doc["status"],"owners":doc["customer_owner_groups"],
                      "linked":doc["linked_accounts"],"connected":doc["connected_accounts"],
                      "fp_native_positions":doc["confirmed_fp_open_positions"],
                      "stop_geometry_alerts":doc["open_positions_stop_beyond_last_mark"],
                      "unknown_connected_position_sets":doc["unknown_connected_position_sets"],
                      "broker_execution_ack_certified":False,"trading_authorized":False}))
if __name__=="__main__":main()
