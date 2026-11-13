#!/usr/bin/python3
"""Read-only per-minute native equity observations for the six ABUTRON CRM links.

Observed-minute equity highs are NOT true intraminute peaks or certified
broker day-start balances. No trading, credentials, or CRM mutations.
"""
from __future__ import annotations
import datetime as dt
from decimal import Decimal,InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207")
RISK=ROOT/"customer-wide-risk-evidence.json"
LEDGER=ROOT/"six-broker-native-history-reconciliation.json"
STORE=ROOT/"six-account-observed-equity.sqlite3"
REPORT=ROOT/"six-account-observed-equity.json"

def amount(x):
    try:
        d=Decimal(str(x))
        if not d.is_finite() or d<0:raise ValueError("INVALID_NONNEGATIVE_EQUITY")
        return d
    except (TypeError,InvalidOperation,ValueError):
        raise ValueError("INVALID_NONNEGATIVE_EQUITY")

def trusted_json(path, age_max=185):
    if path.is_symlink() or not path.is_file():
        raise ValueError("SOURCE_SYMLINK_OR_MISSING")
    st=path.stat()
    if (not -3<=time.time()-st.st_mtime<=age_max or
        st.st_size>150000 or st.st_size<5 or st.st_mode&0o022):
        raise ValueError("SOURCE_STALE_OR_UNTRUSTED")
    raw=path.read_bytes()
    d=json.loads(raw)
    if type(d)!=dict:raise ValueError("SOURCE_NOT_OBJECT")
    return d,hashlib.sha256(raw).hexdigest()

def source_samples():
    risk,digest=trusted_json(RISK,155)
    ledger,_=trusted_json(LEDGER,205)
    if (risk.get("schema")!="abutron.customer_wide.native_exposure.fail_closed.v1"
        or risk.get("linked_accounts")!=6 or risk.get("connected_accounts")!=6
        or risk.get("native_flat_accounts_verified")!=6
        or risk.get("native_current_open_exposure_reconciled") is not True
        or risk.get("native_current_open_stop_risk_usd")!=0
        or risk.get("customer_wide_risk_certified") is not False
        or risk.get("authenticated_broker_execution_ack_certified") is not False
        or ledger.get("schema")!="abutron.six_account.native_selected_window_financial_ledger.ro.v1"
        or ledger.get("five_demo_native_trade_windows_reconciled") is not True
        or ledger.get("all_six_all_time_history_certified") is not False
        or ledger.get("trading_authorized_by_audit") is not False):
        raise ValueError("SIX_ACCOUNT_NATIVE_EQUITY_SOURCE_CONTRACT_INVALID")
    owners=risk.get("owners")
    if not isinstance(owners,dict) or len(owners)!=3:
        raise ValueError("OWNER_GROUP_COUNT_CHANGED")
    rows=[]
    seen=set()
    for owner,info in owners.items():
        if (not isinstance(owner,str) or len(owner)!=12 or
            not all(c in "0123456789abcdef" for c in owner)):
            raise ValueError("OWNER_HASH_INVALID")
        accs=info.get("connections",[])
        for a in accs:
            snap=a.get("snapshot",{})
            if (a.get("connection_status")!="CONNECTED"
                or a.get("effective_on") is not False
                or a.get("current_open_exposure_reconciled") is not True
                or a.get("current_open_stop_risk_usd")!=0.0
                or snap.get("positions_count")!=0 or snap.get("pending_orders_count")!=0):
                raise ValueError("ACCOUNT_NO_LONGER_BROKER_VERIFIED_AND_FLAT")
            label=a.get("account_masked")
            if not isinstance(label,str) or not label.startswith("••••") or len(label)!=8:
                raise ValueError("UNMASKED_OR_INVALID_ACCOUNT_REFERENCE")
            suffix=label[-4:]
            broker=a.get("broker")
            environment=a.get("environment")
            if (broker,environment) not in [
                ("Deriv","DEMO"),("Deriv","LIVE"),("FP Markets","DEMO")]:
                raise ValueError("UNKNOWN_BROKER_OR_ENVIRONMENT")
            key=(owner,suffix,broker,environment)
            if key in seen:raise ValueError("DUPLICATE_NATIVE_ACCOUNT")
            seen.add(key)
            balance=amount(snap.get("balance_usd"))
            equity=amount(snap.get("equity_usd"))
            if environment=="DEMO" and (balance<=0 or equity<=0):
                raise ValueError("UNFUNDED_DEMO_EQUITY_PROOF")
            if environment=="LIVE" and snap.get("broker_trade_allowed") is not False:
                raise ValueError("LIVE_TRADING_PERMISSION_NOT_FENCED")
            rows.append((owner,suffix,broker,environment,str(balance),str(equity),digest))
    if len(rows)!=6 or sorted(x[1] for x in rows)!=sorted(
        ["6207","7593","9244","0512","1636","0178"]):
        raise ValueError("NATIVE_ACCOUNT_ROSTER_CHANGED")
    return rows

def day_summary(db,day):
    day_start=int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())
    today_end=day_start+86400
    records=db.execute("""SELECT minute_utc,owner_hash,account_suffix,equity_usd
                          FROM equity_samples
                          WHERE minute_utc>=? AND minute_utc<?
                          ORDER BY minute_utc,owner_hash,account_suffix""",
                       (day_start,today_end)).fetchall()
    minute_owner={}
    owner_keys={}
    for minute,owner,acct,equity in records:
        minute_owner.setdefault((minute,owner),[]).append(amount(equity))
        owner_keys.setdefault(owner,set()).add(acct)
    totals={}
    for (minute,owner),equity_list in minute_owner.items():
        if len(equity_list)!=len(owner_keys[owner]):continue
        totals.setdefault(owner,[]).append((minute,sum(equity_list,Decimal("0"))))
    out={}
    for owner,series in totals.items():
        series.sort()
        first=series[0][1];latest=series[-1][1]
        high=max(x for _,x in series)
        gaps=[(b[0]-a[0])//60 for a,b in zip(series,series[1:])]
        loss=(high-latest)/high*100 if high>0 else Decimal("0")
        out[owner]={
            "owner_hash":owner,
            "sampled_minutes_complete_for_owner":len(series),
            "earliest_native_equity_sample_utc":dt.datetime.fromtimestamp(
                series[0][0],dt.timezone.utc).isoformat(),
            "latest_native_equity_sample_utc":dt.datetime.fromtimestamp(
                series[-1][0],dt.timezone.utc).isoformat(),
            "earliest_observed_equity_usd":float(first),
            "latest_observed_equity_usd":float(latest),
            "observed_sample_high_water_usd":float(high),
            "observed_sample_peak_to_current_drawdown_pct":float(loss),
            "largest_missing_sample_gap_minutes":max(gaps,default=0),
            "true_broker_daystart_or_peak_certified":False}
    return out

def main():
    rows=source_samples()
    if ROOT.is_symlink() or not ROOT.is_dir() or ROOT.stat().st_uid!=0:
        raise ValueError("ROOT_PRIVATE_STATE_DIRECTORY_INVALID")
    minute=int(time.time()//60)*60
    day=dt.datetime.fromtimestamp(minute,dt.timezone.utc).date().isoformat()
    with sqlite3.connect(str(STORE),timeout=8,isolation_level=None) as c:
        c.execute("PRAGMA busy_timeout=8000")
        c.execute("PRAGMA synchronous=FULL")
        c.execute("""CREATE TABLE IF NOT EXISTS equity_samples(
            minute_utc INTEGER NOT NULL,
            owner_hash TEXT NOT NULL, account_suffix TEXT NOT NULL,
            broker TEXT NOT NULL, environment TEXT NOT NULL,
            balance_usd TEXT NOT NULL, equity_usd TEXT NOT NULL,
            risk_report_sha256 TEXT NOT NULL,
            PRIMARY KEY(minute_utc,owner_hash,account_suffix,broker))""")
        c.execute("BEGIN IMMEDIATE")
        try:
            before=c.total_changes
            for row in rows:
                c.execute("""INSERT OR IGNORE INTO equity_samples
                             VALUES(?,?,?,?,?,?,?,?)""",(minute,*row))
            inserted=c.total_changes-before
            if inserted not in (0,6):
                raise ValueError("PARTIAL_OR_CONFLICTING_MINUTE_EQUITY_SAMPLE")
            if c.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                raise ValueError("EQUITY_SAMPLE_DB_INTEGRITY_FAIL")
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK");raise
        stats=day_summary(c,day)
    report={
        "schema":"abutron.six_account.native_equity.observed_minutes.ro.v1",
        "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "utc_observation_day":day,
        "sample_minute_utc":dt.datetime.fromtimestamp(
            minute,dt.timezone.utc).isoformat(),
        "native_accounts_sampled":6,"owner_groups_sampled":3,
        "newly_written_native_account_samples":inserted,
        "current_open_usd_stop_risk_verified":0.0,
        "current_open_exposure_reconciled":True,
        "customer_owner_sampled_equity":stats,
        "native_actual_daystart_equity_certified":False,
        "native_true_intraminute_equity_peak_certified":False,
        "sampled_observation_only_not_execution_authority":True,
        "new_broker_order_ack_certified":False,
        "risk_switches_changed":False,"orders_submitted":0}
    temp=REPORT.parent/(".native-equity-"+str(os.getpid())+".tmp")
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(report,f,sort_keys=True,indent=2)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(temp,REPORT)
    finally:temp.unlink(missing_ok=True)
    print(json.dumps({
        "sampled":report["native_accounts_sampled"],
        "owner_groups":report["owner_groups_sampled"],
        "samples_added":inserted,
        "true_historical_daystart_certified":False,
        "orders":0},sort_keys=True))
    return 0

if __name__=="__main__":
    sys.exit(main())
