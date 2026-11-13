#!/usr/bin/python3
"""ABUTRON three Deriv DEMO full-range authenticated MT5 history and funding.
Independent read-only validator; the preexisting V2 window must be a byte-equal
subset of each HistorySelect(0) output, and all broker cashflow must balance.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

RECON=Path("/var/lib/abutron-deriv-multi-native-reconciliation/latest.json")
LEDGER=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/six-broker-native-history-reconciliation.json")
OUTPUT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/deriv-three-native-fullrange-financial-history.json")
P=Path("/var/lib/private")
HASHES={"6207":"680e5de8976c50d382d05f07b6eaf3c0e2f26e184302c68a11a850845c1d32f2",
        "7593":"b120612dd199b62107bec0a419a7c293f65c4ec4c23482a7c944884305251d2d",
        "9244":"b120612dd199b62107bec0a419a7c293f65c4ec4c23482a7c944884305251d2d"}
LOGINS={"6207":"32456207","7593":"6357593","9244":"202699244"}
HEAD="ticket position_id order_id time_utc type entry reason magic symbol volume price profit commission fee swap".split()

def load(p,limit=190):
    if p.is_symlink() or not p.is_file() or not -4<=time.time()-p.stat().st_mtime<=limit:
        raise ValueError("SOURCE_MISSING_OR_STALE")
    if p.stat().st_mode&0o022:raise ValueError("SOURCE_NOT_IMMUTABLE_TO_UNPRIVILEGED_USER")
    x=json.loads(p.read_text())
    if type(x)!=dict:raise ValueError("NATIVE_REPORT_NOT_OBJECT")
    return x

def num(v):
    d=Decimal(str(v))
    if not d.is_finite():raise ValueError("NONFINITE_BROKER_VALUE")
    return d

def parse(path,nonce,login,full):
    if path.is_symlink() or not path.is_file() or not 0<=time.time()-path.stat().st_mtime<=170:
        raise ValueError("UNTRUSTED_STALE_NATIVE_EXPORT")
    lines=path.read_text(encoding="utf-8-sig").splitlines()
    start=(["ABUTRON_DERIV_NATIVE_ALLTIME_V1",nonce,login,"Deriv-Demo","DEMO","USD"]
           if full else ["ABUTRON_APEX_DEAL_HISTORY_V2",nonce,login,"Deriv-Demo"])
    if lines[:len(start)]!=start:raise ValueError("NATIVE_BROKER_LOGIN_SOURCE_CONFLICT")
    if full:
        if len(lines)<12 or lines[7]!="0" or lines[9].split("\t")!=HEAD:
            raise ValueError("NOT_FULLRANGE_HISTORYSELECT_ZERO")
        rows=lines[10:-1]
        foot=lines[-1].split("\t")
        if (len(foot)!=3 or foot[0]!="END" or
            not foot[1].isdigit() or not foot[2].isdigit() or
            len(rows)!=int(lines[8]) or len(rows)!=int(foot[1]) or
            len(rows)!=int(foot[2])):
            raise ValueError("FULLRANGE_NATIVE_DEAL_COUNT_MISMATCH")
    else:
        if len(lines)<8 or lines[5]!="DEMO" or lines[6].split("\t")!=HEAD:
            raise ValueError("NATIVE_45DAY_WINDOW_HEADER_INVALID")
        rows=lines[7:]
    result={}
    for line in rows:
        cols=line.split("\t")
        if len(cols)!=15 or not cols[0].isdigit() or cols[0] in result:
            raise ValueError("NATIVE_DEAL_COLS_OR_DUPLICATE_TICKET")
        obj=dict(zip(HEAD,cols))
        for field in ["type","entry","time_utc","position_id"]:
            int(obj[field])
        for field in ["volume","profit","commission","fee","swap"]:
            num(obj[field])
        result[obj["ticket"]]=obj
    return result

def audit_one(suffix,cid,broker,financial):
    if broker.get("state")!="VERIFIED_READONLY" or broker.get("account_suffix")!=suffix:
        raise ValueError("BROKER_SIDECAR_RECONCILIATION_NOT_CURRENT")
    h=load(P/("abutron-native-readonly-mt5-"+suffix)/"worker-health.json",30)
    nonce=h.get("nonce")
    if (h.get("account_suffix")!=suffix or h.get("status")!="CONNECTED"
        or h.get("native_history_source_authenticated") is not True
        or h.get("broker_session_identity_verified") is not True
        or h.get("native_binary_sha256")!=HASHES[suffix]
        or h.get("orders_submitted")!=0 or h.get("execution_authority") is not False
        or type(nonce)!=str or len(nonce)!=32):
        raise ValueError("DERIV_NATIVE_SIDE_CAR_IDENTITY_OR_NOORDER_REJECTED")
    path=P/("abutron-native-readonly-mt5-"+suffix)/"terminal/MQL5/Files"
    full=parse(path/("ABUTRON_NATIVE_ALLTIME_V1_"+nonce+".tsv"),nonce,LOGINS[suffix],True)
    win=parse(path/("ABUTRON_APEX_DEAL_HISTORY_V2_"+nonce+".tsv"),nonce,LOGINS[suffix],False)
    if (len(win)!=broker["native_deals_in_export_window"] or
        len(win)!=financial["native_deals_in_window"] or
        any(full.get(k)!=r for k,r in win.items())):
        raise ValueError("DERIV_BROKER_45DAY_HISTORY_NOT_CONTAINED_IN_FULLRANGE")
    types=Counter(int(x["type"]) for x in full.values())
    if any(k not in (0,1,2) for k in types):
        raise ValueError("UNSUPPORTED_BROKER_DEAL_TYPE")
    entries=defaultdict(Decimal);exits=defaultdict(Decimal);cash=Decimal(0)
    deposits=Decimal(0)
    for row in full.values():
        flow=sum((num(row[k]) for k in ("profit","commission","fee","swap")),Decimal(0))
        cash+=flow
        typ=int(row["type"])
        if typ==2:
            deposits+=flow
            if int(row["position_id"])!=0:raise ValueError("FUNDING_POSITION_ID_NOT_ZERO")
            continue
        vol=num(row["volume"])
        pos=row["position_id"]
        if not pos.isdigit() or int(pos)<=0 or vol<=0:
            raise ValueError("DERIV_TRADE_BROKER_POSITION_INVALID")
        if int(row["entry"])==0:entries[pos]+=vol
        elif int(row["entry"]) in (1,3):exits[pos]+=vol
        else:raise ValueError("UNKNOWN_NATIVE_DEAL_ENTRY_TYPE")
    ids=set(entries)|set(exits)
    if any(abs(entries[k]-exits[k])>Decimal("0.00001") for k in ids):
        raise ValueError("FULLRANGE_NATIVE_POSITION_EXIT_VOLUME_MISMATCH")
    if len(ids)!=broker["matched_position_ids"]:
        raise ValueError("BROKER_POSITION_COUNT_MISMATCH")
    balance=num(broker["balance_usd"])
    if (balance<=0 or abs(cash-balance)>Decimal(".01") or
        abs(balance-num(financial["current_broker_balance_usd"]))>Decimal(".01")):
        raise ValueError("NATIVE_ACCOUNT_TOTAL_CASHFLOW_NOT_BROKER_BALANCE")
    if len(full)!=len(win)+1 or types.get(2)!=1 or deposits!=Decimal("10000"):
        raise ValueError("DERIV_INITIAL_FUNDING_OR_UNEXPECTED_FULLRANGE_COUNT")
    utc_midnight=int(datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
    today=sum((sum((num(row[k]) for k in ("profit","commission","fee","swap")),Decimal(0))
               for row in full.values() if int(row["time_utc"])>=utc_midnight),Decimal(0))
    return {"account_suffix":suffix,
            "native_broker_fullrange_deals":len(full),
            "native_broker_trade_deals":types.get(0,0)+types.get(1,0),
            "native_deposit_deals":types.get(2,0),
            "funding_cashflow_usd":float(deposits),
            "trading_net_cashflow_usd":float(cash-deposits),
            "native_broker_cash_balance_usd":float(balance),
            "native_closed_positions_matched":len(ids),
            "utc_daystart_native_cash_balance_usd":float(balance-today),
            "all_returned_deals_cashflow_to_balance_proved":True,
            "history_query_from_unix_epoch_zero":True,
            "all_returned_trade_positions_matched":True,
            "fullrange_contains_exact_prior_window":True,
            "native_broker_true_intraday_equity_peak_proved":False,
            "independently_broker_server_history_retentiveness_proved":False}

def inspect():
    b=load(RECON,130)
    f=load(LEDGER,185)
    if b.get("all_verified") is not True or f.get("five_demo_native_trade_windows_reconciled") is not True:
        raise ValueError("BROKER_PARENT_RECONCILIATION_UNVERIFIED")
    bmap={a["account_suffix"]:a for a in b["accounts"]}
    fmap={a["account_suffix"]:a for a in f["accounts"] if a["broker"]=="Deriv" and a["environment"]=="DEMO"}
    if set(bmap)!=set(HASHES) or set(fmap)!=set(HASHES):
        raise ValueError("DERIV_CRM_ROSTER_CHANGED")
    with sqlite3.connect("file:/var/lib/apex-signup/accounts.sqlite3?mode=ro",uri=True) as c:
        c.execute("PRAGMA query_only=ON")
        rows=c.execute("""SELECT id,account_reference,broker,environment,status,
                          coalesce(t.effective_enabled,0)
                          FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t
                          ON t.connection_id=x.id
                          WHERE x.broker='Deriv' AND x.environment='DEMO'""").fetchall()
    ids={}
    for cid,login,broker,env,status,effective in rows:
        suffix=str(login)[-4:]
        if status!="CONNECTED" or effective!=0 or suffix not in HASHES:
            raise ValueError("DERIV_DEMO_CRM_WRITER_STATUS_CHANGED")
        ids[suffix]=cid
    if set(ids)!=set(HASHES):raise ValueError("DERIV_3_DEMO_CONNECTIONS_NOT_UNIQUE")
    reports=[audit_one(s,ids[s],bmap[s],fmap[s]) for s in sorted(HASHES)]
    return {"schema":"abutron.three_deriv.native_allrange_funding_and_trade.ro.v1",
            "verified_utc":datetime.now(timezone.utc).isoformat(),
            "state":"ALL_THREE_BROKER_FULLRANGE_RETURNED_CASHFLOWS_RECONCILED",
            "accounts":reports,
            "three_native_select_from_zero_fullrange_proved":True,
            "three_native_funding_and_trade_cashflow_balance_reconciled":True,
            "native_deals_total":sum(x["native_broker_fullrange_deals"] for x in reports),
            "native_trade_deals_total":sum(x["native_broker_trade_deals"] for x in reports),
            "matched_closed_position_ids":sum(x["native_closed_positions_matched"] for x in reports),
            "all_native_funding_total_usd":sum(x["funding_cashflow_usd"] for x in reports),
            "live_history_certified":False,
            "full_customer_lifetime_history_certified":False,
            "native_true_peak_equity_certified":False,
            "broker_order_ack_certified":False,
            "automatic_execution_enabled":False,"orders_submitted":0}

def main():
    d=inspect()
    temp=OUTPUT.parent/(".native-deriv-allrange-"+str(os.getpid())+".tmp")
    fd=os.open(temp,os.O_EXCL|os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as file:
            json.dump(d,file,sort_keys=True,indent=2)
            file.write("\n");file.flush();os.fsync(file.fileno())
        os.replace(temp,OUTPUT)
    finally:temp.unlink(missing_ok=True)
    print(json.dumps({"state":d["state"],"deals":d["native_deals_total"],
        "matched_positions":d["matched_closed_position_ids"],
        "funding_cashflow_usd":d["all_native_funding_total_usd"],
        "execution_enabled":False,"orders":0}))
if __name__=="__main__":sys.exit(main())
