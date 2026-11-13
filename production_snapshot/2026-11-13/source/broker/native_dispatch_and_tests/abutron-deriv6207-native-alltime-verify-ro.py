#!/usr/bin/python3
"""Independent Deriv DEMO 6207 full-range native history/balance validator.
Reads live read-only MT5 exporter (HistorySelect(0)) and independent V2 deal
sidecar; DOES NOT authorize orders or infer unavailable broker history.
"""
from __future__ import annotations
from collections import defaultdict,Counter
from decimal import Decimal, InvalidOperation
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import stat
import sys
import time

CID="d6fc2524ec373b8d1bc278a8be3ec635"
ROOT=Path("/var/lib/private/abutron-native-readonly-mt5-6207")
RISK=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/customer-wide-risk-evidence.json")
DERIV=Path("/var/lib/abutron-deriv-multi-native-reconciliation/latest.json")
OUT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/deriv-6207-native-fullrange-history.json")
BINARY=Path("/opt/abutron-research/native-evidence/read-only-sidecar/AbutronDerivReadOnlySidecarV1.ex5")
EXPECTED_HASH="680e5de8976c50d382d05f07b6eaf3c0e2f26e184302c68a11a850845c1d32f2"
HEAD=["ticket","position_id","order_id","time_utc","type","entry","reason","magic",
      "symbol","volume","price","profit","commission","fee","swap"]

def secure(path,ttl=160,limit=6000000):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_mode&0o022
            or st.st_size<5 or st.st_size>limit or not -4<=time.time()-st.st_mtime<=ttl):
            raise ValueError("SOURCE_UNTRUSTED_STALE_OR_OVERSIZED")
        raw=os.read(fd,limit+1)
        e=os.fstat(fd)
        if (len(raw)!=st.st_size or
            (st.st_dev,st.st_ino,st.st_mtime_ns,st.st_size)!=(e.st_dev,e.st_ino,e.st_mtime_ns,e.st_size)):
            raise ValueError("SOURCE_CHANGED_DURING_READ")
        return raw
    finally:os.close(fd)

def load(path,ttl=160):
    o=json.loads(secure(path,ttl))
    if type(o)!=dict:raise ValueError("SOURCE_JSON_NOT_OBJECT")
    return o

def money(x):
    try:
        d=Decimal(str(x))
        if not d.is_finite():raise ValueError("INVALID_NONFINITE_BROKER_CASH")
        return d
    except (TypeError,ValueError,InvalidOperation):
        raise ValueError("INVALID_BROKER_CASH_VALUE")

def parse(raw,nonce,login,full):
    lines=raw.decode("utf-8-sig").splitlines()
    header=(["ABUTRON_DERIV_NATIVE_ALLTIME_V1",nonce,login,"Deriv-Demo","DEMO","USD"]
            if full else ["ABUTRON_APEX_DEAL_HISTORY_V2",nonce,login,"Deriv-Demo"])
    offset=10 if full else 7
    if lines[:len(header)]!=header or len(lines)<=offset:
        raise ValueError("HISTORY_SCHEMA_OR_OWNER_MISMATCH")
    if full:
        if lines[7]!="0" or int(lines[8])<1 or lines[9].split("\t")!=HEAD:
            raise ValueError("HISTORYSELECT_ZERO_FULL_RANGE_NOT_PROVEN")
        if not 0<=time.time()-int(lines[6])<=160:
            raise ValueError("FULLRANGE_NATIVE_EXPORT_CLOCK_STALE")
        end=lines[-1].split("\t")
        if len(end)!=3 or end[0]!="END" or any(not y.isdecimal() for y in end[1:]):
            raise ValueError("FULLRANGE_FOOTER_INVALID")
        rows=lines[offset:-1]
        if int(end[1])!=int(end[2]) or len(rows)!=int(end[1]) or len(rows)!=int(lines[8]):
            raise ValueError("FULLRANGE_BROKER_DEAL_TOTAL_MISMATCH")
    else:
        if lines[5]!="DEMO" or lines[6].split("\t")!=HEAD:
            raise ValueError("V2_WINDOW_HEADER_INVALID")
        rows=lines[offset:]
    out=[]
    for r in rows:
        vals=r.split("\t")
        if len(vals)!=15 or not vals[0].isdecimal():
            raise ValueError("NATIVE_HISTORY_FIELD_COUNT_INVALID")
        x=dict(zip(HEAD,vals))
        for col in ("position_id","order_id","time_utc","type","entry","reason","magic"):
            int(x[col])
        for col in ("volume","price","profit","commission","fee","swap"):
            money(x[col])
        out.append(x)
    if len(set(r["ticket"] for r in out))!=len(out):
        raise ValueError("DUPLICATE_NATIVE_BROKER_DEAL")
    return out

def inspect():
    h=load(ROOT/"worker-health.json",30)
    nonce=h.get("nonce")
    if (h.get("account_suffix")!="6207" or h.get("broker")!="Deriv"
        or h.get("environment")!="DEMO" or h.get("status")!="CONNECTED"
        or h.get("native_history_source_authenticated") is not True
        or h.get("execution_authority") is not False or h.get("orders_submitted")!=0
        or h.get("native_binary_sha256")!=EXPECTED_HASH
        or type(nonce)!=str or len(nonce)!=32):
        raise ValueError("DERIV_FULLRANGE_WORKER_IDENTITY_INVALID")
    rawbin=secure(BINARY,ttl=86400)
    if hashlib.sha256(rawbin).hexdigest()!=EXPECTED_HASH:
        raise ValueError("BINARY_RELEASE_HASH_CHANGED")
    if not BINARY.is_file():
        raise ValueError("NO_NATIVE_EX5")
    with sqlite3.connect("file:/var/lib/apex-signup/accounts.sqlite3?mode=ro",uri=True) as c:
        c.execute("PRAGMA query_only=ON")
        x=c.execute("""SELECT x.account_reference,x.broker,x.environment,x.status,
                       coalesce(t.effective_enabled,0) FROM apex_mt5_connections x
                       LEFT JOIN apex_trade_controls t ON x.id=t.connection_id
                       WHERE x.id=?""",(CID,)).fetchone()
    if x!=("32456207","Deriv","DEMO","CONNECTED",0):
        raise ValueError("DERIV_CRM_6207_NOT_SAME_ACCOUNT_OFF")
    risk=load(RISK,160)
    prior=load(DERIV,160)
    accounts=prior.get("accounts",[])
    matches=[a for a in accounts if a.get("account_suffix")=="6207"]
    if (len(matches)!=1 or not prior.get("all_verified") or
        matches[0].get("state")!="VERIFIED_READONLY" or
        matches[0].get("positions")!=0 or matches[0].get("pending_orders")!=0 or
        not risk.get("native_current_open_exposure_reconciled")):
        raise ValueError("INDEPENDENT_CURRENT_NATIVE_POSITION_PROOF_FAILED")
    f=ROOT/"terminal/MQL5/Files"
    fullraw=secure(f/("ABUTRON_NATIVE_ALLTIME_V1_"+nonce+".tsv"),ttl=170)
    winraw=secure(f/("ABUTRON_APEX_DEAL_HISTORY_V2_"+nonce+".tsv"),ttl=170)
    full=parse(fullraw,nonce,"32456207",True)
    selected=parse(winraw,nonce,"32456207",False)
    fdict={r["ticket"]:r for r in full}
    if (len(selected)!=h.get("native_deal_export_count")
        or len(selected)!=matches[0]["native_deals_in_export_window"]
        or any(fdict.get(r["ticket"])!=r for r in selected)):
        raise ValueError("FULL_NATIVE_HISTORY_DOES_NOT_INCLUDE_PRIOR_45DAY_EXPORT")
    types=Counter(int(r["type"]) for r in full)
    if any(t not in (0,1,2,3,4,5,6,7,8) for t in types):
        raise ValueError("UNRECOGNIZED_BROKER_DEAL_CASHFLOW_TYPE")
    transactions=[r for r in full if int(r["type"]) not in (0,1)]
    fundings=[r for r in transactions if int(r["type"])==2 and money(r["profit"])>0]
    if len(fundings)<1:
        raise ValueError("INITIAL_NATIVE_DEPOSIT_NOT_EXPORTED")
    entries=defaultdict(Decimal);exits=defaultdict(Decimal)
    for r in full:
        typ=int(r["type"])
        if typ>=2:continue
        pid=r["position_id"]
        if not pid.isdecimal() or int(pid)<=0:
            raise ValueError("NATIVE_TRADE_POSITION_ID_INVALID")
        vol=money(r["volume"])
        if vol<=0:raise ValueError("NATIVE_TRADE_VOLUME_INVALID")
        entry=int(r["entry"])
        if entry==0:entries[pid]+=vol
        elif entry in (1,3):exits[pid]+=vol
        else:raise ValueError("UNKNOWN_NATIVE_POSITION_ENTRY_TYPE")
    pos=set(entries)|set(exits)
    if any(abs(entries[k]-exits[k])>Decimal("0.00001") for k in pos):
        raise ValueError("UNMATCHED_POSITION_IN_FULLRANGE_NATIVE_HISTORY")
    if len(pos)!=matches[0]["matched_position_ids"]:
        raise ValueError("NATIVE_LIFETIME_POSITION_COUNT_CONFLICT")
    total=sum((sum((money(r[x]) for x in ("profit","commission","fee","swap")),Decimal(0))
               for r in full),Decimal(0))
    current=money(matches[0]["balance_usd"])
    if abs(total-current)>Decimal(".01"):
        raise ValueError("NATIVE_FULLRANGE_DEALS_NOT_EQUAL_CURRENT_BROKER_BALANCE")
    deposits=sum((sum((money(r[x]) for x in ("profit","commission","fee","swap")),Decimal(0))
                  for r in transactions),Decimal(0))
    tradecash=total-deposits
    times=[int(r["time_utc"]) for r in full]
    midnight=int(datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
    since=sum((sum((money(r[x]) for x in ("profit","commission","fee","swap")),Decimal(0))
                for r in full if int(r["time_utc"])>=midnight),Decimal(0))
    balance_daystart=current-since
    if balance_daystart<0:
        raise ValueError("NATIVE_DAYSTART_BALANCE_NEGATIVE")
    return {
        "schema":"abutron.deriv6207.full_range_native_history_funding.readonly.v1",
        "verified_utc":datetime.now(timezone.utc).isoformat(),
        "account_suffix":"6207",
        "crm_connection_id":CID,
        "worker_nonce":nonce,"native_binary_sha256":EXPECTED_HASH,
        "full_range_broker_native_history_select_from_utc":0,
        "first_native_deal_utc":datetime.fromtimestamp(min(times),timezone.utc).isoformat(),
        "last_native_deal_utc":datetime.fromtimestamp(max(times),timezone.utc).isoformat(),
        "native_full_range_deals":len(full),
        "native_trade_deals":sum(v for k,v in types.items() if k<2),
        "native_funding_and_other_deals":len(transactions),
        "native_positive_deposits":len(fundings),
        "native_matched_closed_positions":len(pos),
        "full_range_contains_prior_45day_export":True,
        "native_funding_cashflow_usd":float(deposits),
        "native_trade_net_cashflow_usd":float(tradecash),
        "native_total_deal_cashflow_usd":float(total),
        "current_native_broker_balance_usd":float(current),
        "full_range_cashflow_to_broker_balance_reconciled":True,
        "today_utc_daystart_native_cash_balance_usd":float(balance_daystart),
        "today_utc_daystart_cash_reconstructed":True,
        "true_broker_intraday_equity_peak_verified":False,
        "broker_history_older_than_native_server_return_verifiable":False,
        "new_order_broker_ack_certified":False,
        "orders_submitted":0,
        "automatic_trading_enabled":False}

def main():
    d=inspect()
    p=OUT.parent/(".deriv-6207-alltime-"+str(os.getpid())+".tmp")
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(d,f,indent=2,sort_keys=True)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(p,OUT)
    finally:p.unlink(missing_ok=True)
    print(json.dumps({k:d[k] for k in ("native_full_range_deals",
      "native_funding_cashflow_usd","native_trade_net_cashflow_usd",
      "current_native_broker_balance_usd","full_range_cashflow_to_broker_balance_reconciled",
      "today_utc_daystart_native_cash_balance_usd","orders_submitted")}))
if __name__=="__main__":sys.exit(main())
