#!/usr/bin/python3
"""Account-bound read-only ABUTRON six-account native deal/cashflow audit.

This proves broker-native *selected-window* deal pairing, not every historical
trade or intraday high-water equity. It never submits orders or changes CRM.
"""
from __future__ import annotations
import collections
from decimal import Decimal, InvalidOperation
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

CRM=Path("/var/lib/apex-signup/accounts.sqlite3")
OUT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/six-broker-native-history-reconciliation.json")
PRIVATE=Path("/var/lib/private")
DERIV_REPORT=Path("/var/lib/abutron-deriv-multi-native-reconciliation/latest.json")
FP_REPORT=Path("/var/lib/abutron-fp-execution/dual-account-reconciliation/latest.json")
RISK_REPORT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/customer-wide-risk-evidence.json")
FP_V101_SHA="3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac"

def secure_bytes(p:Path, max_bytes=6000000, max_age=200):
    if p.is_symlink():
        raise ValueError("SYMLINK_SOURCE")
    fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or
            st.st_mode&0o022 or st.st_size<2 or st.st_size>max_bytes or
            not -5<=time.time()-st.st_mtime<=max_age):
            raise ValueError("UNTRUSTED_NATIVE_SOURCE_OR_AGE")
        data=os.read(fd,max_bytes+1)
        end=os.fstat(fd)
        if (len(data)!=st.st_size or
            (st.st_ino,st.st_dev,st.st_mtime_ns,st.st_size)!=
            (end.st_ino,end.st_dev,end.st_mtime_ns,end.st_size)):
            raise ValueError("NATIVE_READ_CHANGED")
        return data,st
    finally:os.close(fd)

def load_report(p:Path,ttl=200):
    data,_=secure_bytes(p,3000000,ttl)
    obj=json.loads(data)
    if type(obj)!=dict:raise ValueError("INVALID_NATIVE_REPORT")
    return obj

def decimal(v):
    try:
        x=Decimal(str(v))
        if not x.is_finite():raise ValueError("NONFINITE_BROKER_VALUE")
        return x
    except (ValueError,TypeError,InvalidOperation):
        raise ValueError("INVALID_NATIVE_CURRENCY")

def trade_pairs(rows, *, position_key, type_key, entry_key, volume_key):
    seen,opened,closed=set(),collections.defaultdict(Decimal),collections.defaultdict(Decimal)
    trade_deals=0
    for row in rows:
        tid=row["ticket"]
        if not tid.isdecimal() or tid in seen:
            raise ValueError("DUPLICATE_OR_MALFORMED_BROKER_DEAL_TICKET")
        seen.add(tid)
        kind=int(row[type_key])
        if kind>=2:
            continue
        position=row[position_key]
        entry=int(row[entry_key])
        vol=decimal(row[volume_key])
        if not position.isdecimal() or int(position)<=0 or vol<=0:
            raise ValueError("INVALID_POSITION_VOLUME_OR_ID")
        trade_deals+=1
        if entry==0:opened[position]+=vol
        elif entry in (1,3):closed[position]+=vol
        else:raise ValueError("UNSUPPORTED_NATIVE_ENTRY_ENUM")
    pids=set(opened)|set(closed)
    if any(abs(opened[p]-closed[p])>Decimal("0.00001") for p in pids):
        raise ValueError("BROKER_NATIVE_ENTRY_EXIT_VOLUME_MISMATCH")
    return trade_deals,len(pids)

def deriv_one(cid,login,deriv_by_suffix):
    suffix=str(login)[-4:]
    root=PRIVATE/("abutron-native-readonly-mt5-"+suffix)
    health=load_report(root/"worker-health.json",100)
    nonce=health.get("nonce")
    if (health.get("account_suffix")!=suffix or
        health.get("broker")!="Deriv" or health.get("environment")!="DEMO" or
        health.get("status")!="CONNECTED" or
        health.get("broker_session_identity_verified") is not True or
        health.get("native_history_source_authenticated") is not True or
        health.get("execution_authority") is not False or
        health.get("orders_submitted")!=0 or
        type(nonce)!=str or len(nonce)!=32 or
        any(t not in "0123456789abcdef" for t in nonce)):
        raise ValueError("DERIV_NOORDER_SIDECAR_BROKER_IDENTITY_UNVERIFIED")
    p=root/"terminal/MQL5/Files"/("ABUTRON_APEX_DEAL_HISTORY_V2_"+nonce+".tsv")
    raw,_=secure_bytes(p,max_age=190)
    lines=raw.decode("utf-8-sig").splitlines()
    expected=['ticket','position_id','order_id','time_utc','type','entry',
              'reason','magic','symbol','volume','price','profit',
              'commission','fee','swap']
    if (len(lines)<7 or lines[:4]!=["ABUTRON_APEX_DEAL_HISTORY_V2",nonce,str(login),"Deriv-Demo"]
        or lines[5]!="DEMO" or lines[6].split("\t")!=expected):
        raise ValueError("DERIV_NATIVE_DEAL_SOURCE_HEADER_UNVERIFIED")
    rows=[]
    for x in lines[7:]:
        cols=x.split("\t")
        if len(cols)!=15:raise ValueError("DERIV_DEAL_COLUMNS_INVALID")
        rows.append(dict(zip(expected,cols)))
    d=deriv_by_suffix[suffix]
    if (d.get("state")!="VERIFIED_READONLY" or d.get("positions")!=0
        or d.get("pending_orders")!=0 or d.get("current_exposure")!="ZERO_DUAL_NATIVE_PROOF"
        or d.get("window_complete") is not False
        or d.get("native_deals_in_export_window")!=len(rows)
        or health.get("native_deal_export_count")!=len(rows)):
        raise ValueError("DERIV_RECONCILIATION_NOT_SAME_SELECTED_WINDOW")
    trade_count,matched=trade_pairs(rows,position_key="position_id",type_key="type",
                                    entry_key="entry",volume_key="volume")
    if matched!=d.get("matched_position_ids"):
        raise ValueError("DERIV_PAIR_COUNT_CONFLICT")
    cash={k:sum((decimal(r[k]) for r in rows),Decimal("0"))
          for k in ("profit","commission","fee","swap")}
    net=sum(cash.values(),Decimal("0"))
    baseline=decimal(d["balance_usd"])-net
    return {"account_suffix":suffix,"broker":"Deriv","environment":"DEMO",
            "state":"WINDOW_TRADE_DEALS_PAIRED","native_deals_in_window":len(rows),
            "trade_deals_in_window":trade_count,
            "matched_closed_position_ids":matched,
            "broker_net_trade_cashflow_usd":float(net),
            "broker_trade_commission_usd":float(cash["commission"]),
            "current_broker_balance_usd":float(decimal(d["balance_usd"])),
            "implied_pre_window_balance_usd_not_native_deposit_proof":float(baseline),
            "broker_deposit_cashflow_exported":False,
            "cashflow_to_current_balance_certified":False,
            "selected_window_entry_exit_reconciled":True,
            "all_time_history_complete":False,"current_execution_ack":False}

def fp_one(cid,login,fp_by_suffix):
    suffix=str(login)[-4:]
    root=PRIVATE/("abutron-client-mt5-"+cid)
    h=load_report(root/"worker-health.json",50)
    nonce=h.get("nonce")
    if (h.get("id")!=cid or h.get("broker")!="FP Markets" or
        h.get("mode")!="DEMO" or h.get("server")!="FPMarketsSC-Demo" or
        h.get("status")!="CONNECTED" or
        h.get("heartbeat_fresh") is not True or
        type(nonce)!=str or len(nonce)!=32):
        raise ValueError("FP_NATIVE_CONNECTED_IDENTITY_INVALID")
    binary=root/"terminal/MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5"
    blob,_=secure_bytes(binary,100000,999999999)
    if hashlib.sha256(blob).hexdigest()!=FP_V101_SHA:
        raise ValueError("FP_NATIVE_HISTORY_RELEASE_INVALID")
    p=root/"terminal/MQL5/Files"/("ABUTRON_FP_ACCOUNT_HISTORY_V101_"+nonce+".txt")
    raw,_=secure_bytes(p,max_age=190)
    lines=raw.decode("utf-8-sig").splitlines()
    if (len(lines)<22 or lines[:6]!=["ABUTRON_FP_ACCOUNT_HISTORY_V1",
           nonce,h.get("proof_owner"),"FPMarketsSC-Demo",str(login),"DEMO"]
        or lines[8]!="USD" or lines[19]!="BROKER_NATIVE_NO_ORDER_FUNCTIONS"
        or lines[-1]!="END\t0\t0\t"+lines[16]):
        raise ValueError("FP_NATIVE_HEADER_OR_ZERO_INVENTORY_INVALID")
    pos,pending,total=[int(lines[i]) for i in (14,15,16)]
    if pos!=0 or pending!=0 or total!=len(lines)-21:
        raise ValueError("FP_NATIVE_ACCOUNT_NONZERO_OR_INCOMPLETE")
    col=['ticket','order','position_id','time_broker','type','entry',
         'reason','symbol','volume','price','profit','commission','fee','swap']
    deals=[]
    for line in lines[20:-1]:
        cols=line.split("\t")
        if len(cols)!=15 or cols[0]!="D":
            raise ValueError("FP_NATIVE_DEAL_FORMAT_INVALID")
        deals.append(dict(zip(col,cols[1:])))
    trade_count,matched=trade_pairs(deals,position_key="position_id",type_key="type",
                                    entry_key="entry",volume_key="volume")
    d=fp_by_suffix[suffix]
    if (d.get("state")!="RECONCILED_READONLY" or
        d.get("connection_suffix")!=cid[-6:] or
        d.get("positions")!=0 or d.get("pending")!=0 or
        d.get("unresolved_receipts")!=0 or
        d.get("historical_trade_deals")!=trade_count):
        raise ValueError("FP_INDEPENDENT_NATIVE_RECEIPT_LEDGER_DIVERGED")
    components={k:sum((decimal(r[k]) for r in deals),Decimal("0"))
                for k in ("profit","commission","fee","swap")}
    totalcash=sum(components.values(),Decimal("0"))
    deposits=sum((decimal(r["profit"]) for r in deals if int(r["type"])>=2),Decimal("0"))
    trade_net=sum((sum(decimal(r[k]) for k in components) for r in deals
                   if int(r["type"])<2),Decimal("0"))
    native_balance=decimal(lines[9])
    if (abs(totalcash-native_balance)>Decimal("0.01") or
        abs(native_balance-decimal(d["equity_usd"]))>Decimal("0.01") or
        abs(deposits+trade_net-totalcash)>Decimal("0.01")):
        raise ValueError("FP_NATIVE_CASHFLOW_DOES_NOT_EQUAL_CURRENT_BROKER_BALANCE")
    return {"account_suffix":suffix,"broker":"FP Markets","environment":"DEMO",
            "state":"WINDOW_CASHFLOW_BALANCE_RECONCILED",
            "native_deals_in_window":len(deals),
            "trade_deals_in_window":trade_count,
            "matched_closed_position_ids":matched,
            "broker_deposit_and_balance_cashflow_usd":float(deposits),
            "broker_net_trade_cashflow_usd":float(trade_net),
            "broker_trade_commission_usd":float(sum(
               (decimal(r["commission"]) for r in deals if int(r["type"])<2),Decimal("0"))),
            "current_broker_balance_usd":float(native_balance),
            "unresolved_historical_receipts":0,
            "cashflow_to_current_balance_certified":True,
            "selected_window_entry_exit_reconciled":True,
            "all_time_history_complete":False,"current_execution_ack":False}

def inspect():
    risk=load_report(RISK_REPORT,185)
    deriv=load_report(DERIV_REPORT,190)
    fp=load_report(FP_REPORT,190)
    if (risk.get("native_current_open_exposure_reconciled") is not True
        or risk.get("native_flat_accounts_verified")!=6 or
        risk.get("customer_wide_risk_certified") is not False or
        deriv.get("schema")!="abutron.deriv.three_demo.native_dualproof.readonly.v1" or
        deriv.get("all_verified") is not True or
        fp.get("schema")!="abutron.fpmarkets.dual_demo_native_reconciliation.readonly.v1" or
        fp.get("state")!="RECONCILED_READONLY" or
        fp.get("broker_order_authorized") is not False):
        raise ValueError("INDEPENDENT_SIX_ACCOUNT_PARENT_PROOFS_UNVERIFIED")
    derivmap={x["account_suffix"]:x for x in deriv["accounts"]}
    fpmap={x["account_suffix"]:x for x in fp["accounts"]}
    if sorted(derivmap)!=["6207","7593","9244"] or sorted(fpmap)!=["0512","1636"]:
        raise ValueError("BROKER_ACCOUNT_SCOPE_CHANGED")
    with sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=8) as db:
        db.execute("PRAGMA query_only=ON")
        rows=db.execute("""SELECT x.id,x.account_id,x.account_reference,
                          x.broker,x.environment,x.status,
                          coalesce(t.effective_enabled,0)
                          FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t
                          ON t.connection_id=x.id ORDER BY x.account_reference""").fetchall()
    if len(rows)!=6 or any(x[5]!="CONNECTED" or x[6]!=0 for x in rows):
        raise ValueError("CUSTOMER_ACCOUNT_ROSTER_OR_OFF_FENCE_CHANGED")
    result=[]
    for cid,owner,login,broker,mode,status,eff in rows:
        suffix=str(login)[-4:]
        if broker=="FP Markets" and mode=="DEMO":
            x=fp_one(cid,login,fpmap)
        elif broker=="Deriv" and mode=="DEMO":
            x=deriv_one(cid,login,derivmap)
        elif broker=="Deriv" and mode=="LIVE":
            x={"account_suffix":suffix,"broker":"Deriv","environment":"LIVE",
               "state":"CURRENT_FLAT_ONLY_NO_HISTORICAL_LEDGER",
               "cashflow_to_current_balance_certified":False,
               "selected_window_entry_exit_reconciled":False,
               "all_time_history_complete":False,"current_execution_ack":False}
        else:
            raise ValueError("UNEXPECTED_ACCOUNT_IN_ROSTER")
        x["owner_hash_prefix"]=hashlib.sha256(str(owner).encode()).hexdigest()[:12]
        result.append(x)
    demo=[x for x in result if x["environment"]=="DEMO"]
    passed=(len(demo)==5 and all(x["selected_window_entry_exit_reconciled"] for x in demo))
    return {"schema":"abutron.six_account.native_selected_window_financial_ledger.ro.v1",
            "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "state":"FIVE_DEMO_NATIVE_WINDOW_RECONCILED_LIVE_HISTORY_UNVERIFIED" if passed else "BLOCKED",
            "accounts":result,
            "five_demo_native_trade_windows_reconciled":passed,
            "fp_two_demo_balance_cashflows_reconciled":all(
                x["cashflow_to_current_balance_certified"] for x in result if x["broker"]=="FP Markets"),
            "historical_broker_entry_exit_pairs_verified":sum(x.get("matched_closed_position_ids",0) for x in result),
            "all_six_all_time_history_certified":False,
            "customer_wide_daystart_peak_certified":False,
            "new_broker_execution_ack_certified":False,
            "orders_submitted_by_audit":0,
            "trading_authorized_by_audit":False}

def main():
    result=inspect()
    if OUT.parent.is_symlink() or not OUT.parent.is_dir() or OUT.parent.stat().st_uid!=0:
        raise RuntimeError("ROOT_OUTPUT_DIRECTORY_REQUIRED")
    temp=OUT.parent/(".six-broker-ledger-"+str(os.getpid())+".tmp")
    fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(result,f,sort_keys=True,indent=2,allow_nan=False)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(temp,OUT)
    finally:temp.unlink(missing_ok=True)
    print(json.dumps({
        "state":result["state"],
        "demo_window_pairs_verified":result["five_demo_native_trade_windows_reconciled"],
        "fp_balance_cashflows_verified":result["fp_two_demo_balance_cashflows_reconciled"],
        "matched_position_ids":result["historical_broker_entry_exit_pairs_verified"],
        "orders":0,"execution_authorized":False},sort_keys=True))
    return 0 if result["five_demo_native_trade_windows_reconciled"] else 2

if __name__=="__main__":
    sys.exit(main())
